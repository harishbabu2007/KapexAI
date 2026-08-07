import asyncio
import json
import time
from datetime import UTC, datetime, timedelta

import pytest
from db_service import connect_db, db, disconnect_db
from redis_service import connect_redis, disconnect_redis, redis

from worker.agent import build_graph, load_state, process_job
from worker.agents.chat_agent import ChatAgent
from worker.agents.router_agent import RouterAgent
from worker.helpers.messages import business_context, questionnaire_pending
from worker.helpers.persistence import add_message, build_state_from_db
from worker.tools.questionnaire_tool import QuestionnaireTool
from worker.tools.web_search_tool import WebSearchTool

TEST_EMAIL = "chat-tools-test@example.com"
TEST_IDEA = (
    "I want to open a specialty coffee shop in Pune, aiming for 5 stores in "
    "5 years, targeting young professionals."
)

_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_loop)


def _run(coro):
    return _loop.run_until_complete(coro)


@pytest.fixture(scope="session", autouse=True)
def _services():
    _run(connect_db())
    _run(connect_redis())
    yield
    _run(disconnect_redis())
    _run(disconnect_db())
    _run(_loop.shutdown_asyncgens())
    _loop.close()


async def _cleanup(session_id=None):
    if session_id:
        await redis.delete(f"langgraph_state:{session_id}")
        await db.message.delete_many(where={"sessionId": session_id})
        await db.session.delete_many(where={"id": session_id})
    await db.user.delete_many(where={"email": TEST_EMAIL})


async def _subscribe(session_id):
    ps = redis.pubsub()
    await ps.subscribe(f"stream:{session_id}")
    await ps.get_message(timeout=1)
    return ps


async def _collect(ps, count: int, timeout: float = 10.0) -> list[dict]:
    events = []
    deadline = time.time() + timeout
    while len(events) < count and time.time() < deadline:
        msg = await ps.get_message(timeout=1)
        if msg and msg.get("type") == "message":
            events.append(json.loads(msg["data"]))
    return events


async def _make_session():
    await _cleanup()
    user = await db.user.create(data={"email": TEST_EMAIL, "name": "Test User"})
    session = await db.session.create(
        data={"userId": user.id, "business_idea": TEST_IDEA}
    )
    return session


def test_redis_queue_and_pubsub():
    async def scenario():
        await redis.delete("test_queue", "test_channel")

        await redis.rpush("test_queue", "hello")
        assert await redis.lpop("test_queue") == "hello"

        ps = redis.pubsub()
        await ps.subscribe("test_channel")
        await ps.get_message(timeout=5)

        await redis.publish("test_channel", "payload")
        received = None
        deadline = time.time() + 5
        while received is None and time.time() < deadline:
            msg = await ps.get_message(timeout=1)
            if msg and msg.get("type") == "message":
                received = msg["data"]
        assert received == "payload"

        await ps.unsubscribe("test_channel")
        await ps.close()

    _run(scenario())


def test_chat_flow_persists_and_streams(monkeypatch):
    async def fake_classify(self, user_input, messages, tools):
        return {"intent": "chat", "tool": None}

    async def fake_chat(self, user_input, transcript, context, tools):
        return "FAKE CHAT REPLY"

    monkeypatch.setattr(RouterAgent, "classify", fake_classify)
    monkeypatch.setattr(ChatAgent, "run", fake_chat)

    async def scenario():
        session = await _make_session()
        sid = session.id
        await add_message(sid, "USER", "CHAT", {"type": "chat", "content": "seed"})
        graph = build_graph()
        ps = await _subscribe(sid)
        try:
            result = await process_job({"session_id": sid, "user_input": "Hello"}, graph)
            events = await _collect(ps, 3)

            types = [m["type"] for m in result["messages"]]
            assert types == ["chat", "chat", "chat"]

            event_types = [e["type"] for e in events]
            assert event_types == ["chat", "suggestions", "end"]
            assert events[0]["content"] == "FAKE CHAT REPLY"
            assert {t["name"] for t in events[1]["tools"]} == {
                "questionnaire",
                "swot",
                "web_search",
            }

            msgs = await db.message.find_many(where={"sessionId": sid})
            assert sorted(m.agent for m in msgs) == ["CHAT", "CHAT", "CHAT"]
            assert all(m.role == "USER" for m in msgs[:2])

            await ps.unsubscribe(f"stream:{sid}")
            await ps.close()
        finally:
            await _cleanup(sid)

    _run(scenario())


def test_first_message_greeting_goes_to_chat(monkeypatch):
    async def fake_classify(self, user_input, messages, tools):
        return {"intent": "chat", "tool": None}

    async def fake_chat(self, user_input, transcript, context, tools):
        return "Hi! I'm KapexAI, your business consultant. How can I help your business?"

    monkeypatch.setattr(RouterAgent, "classify", fake_classify)
    monkeypatch.setattr(ChatAgent, "run", fake_chat)

    async def scenario():
        session = await _make_session()
        sid = session.id
        graph = build_graph()
        ps = await _subscribe(sid)
        try:
            result = await process_job({"session_id": sid, "user_input": "hi"}, graph)
            events = await _collect(ps, 3)

            assert [m["type"] for m in result["messages"]] == ["chat", "chat"]
            assert result["messages"][0]["role"] == "USER"
            assert result["messages"][1]["role"] == "ASSISTANT"
            assert result["messages"][1]["content"] == (
                "Hi! I'm KapexAI, your business consultant. How can I help your business?"
            )
            assert events[0]["type"] == "chat"
            assert events[1]["type"] == "suggestions"
            assert events[2]["type"] == "end"

            msgs = await db.message.find_many(where={"sessionId": sid})
            assert sorted(m.agent for m in msgs) == ["CHAT", "CHAT"]

            await ps.unsubscribe(f"stream:{sid}")
            await ps.close()
        finally:
            await _cleanup(sid)

    _run(scenario())


def test_questionnaire_rejects_nonsense_answers(monkeypatch):
    """Gibberish replies must not be absorbed into business context: the
    questionnaire stays pending and re-asks instead of completing."""

    async def fake_plan(self, idea):
        return {
            "facts": {"business_about": idea},
            "questions": [{"key": "q1", "question": "Who is your target customer?"}],
        }

    async def fake_validate(self, questions, answers_text):
        return answers_text != "bla bal ....."

    async def fake_parse(self, questions, answers_text):
        return [answers_text]

    async def fake_is_real_idea(self, idea):
        return True

    async def fake_classify(self, user_input, messages, tools):
        return {"intent": "tool", "tool": "questionnaire"}

    monkeypatch.setattr(QuestionnaireTool, "_plan", fake_plan)
    monkeypatch.setattr(QuestionnaireTool, "_validate", fake_validate)
    monkeypatch.setattr(QuestionnaireTool, "_parse", fake_parse)
    monkeypatch.setattr(QuestionnaireTool, "_is_real_idea", fake_is_real_idea)
    monkeypatch.setattr(RouterAgent, "classify", fake_classify)

    async def scenario():
        session = await _make_session()
        sid = session.id
        graph = build_graph()
        ps = await _subscribe(sid)
        try:
            await process_job({"session_id": sid, "user_input": TEST_IDEA}, graph)
            await _collect(ps, 3)

            second = await process_job(
                {"session_id": sid, "user_input": "bla bal ....."}, graph
            )
            events2 = await _collect(ps, 3)

            types = [m["type"] for m in second["messages"]]
            assert "questionnaire_answer" not in types
            assert "questionnaire_complete" not in types
            assert "questionnaire_invalid" in types
            assert types[-1] == "questionnaire"
            assert questionnaire_pending(second["messages"])

            # The garbage was never folded into the parsed answers.
            for m in second["messages"]:
                assert not any(
                    v == "bla bal ....."
                    for v in (m.get("answers") or {}).values()
                )

            # Questionnaire still pending → a real answer next completes it.
            third = await process_job(
                {"session_id": sid, "user_input": "Young professionals in Pune"}, graph
            )
            await _collect(ps, 3)
            assert third["messages"][-1]["type"] == "questionnaire_complete"
            assert (
                third["messages"][-1]["context"].get("q1")
                == "Young professionals in Pune"
            )

            msgs = await db.message.find_many(where={"sessionId": sid})
            assert sorted(m.agent for m in msgs) == [
                "TOOL",
                "TOOL",
                "TOOL",
                "TOOL",
                "TOOL",
                "TOOL",
            ]

            await ps.unsubscribe(f"stream:{sid}")
            await ps.close()
        finally:
            await _cleanup(sid)

    _run(scenario())


def test_questionnaire_asks_for_idea_when_trigger_phrase(monkeypatch):
    """A command like 'start the business questionnaire' must not be absorbed
    as the business idea — the tool asks for the real idea instead."""

    async def fake_is_real_idea(self, idea):
        return False

    async def fake_plan(self, idea):
        raise AssertionError("_plan must not run for a trigger phrase")

    async def fake_classify(self, user_input, messages, tools):
        return {"intent": "tool", "tool": "questionnaire"}

    monkeypatch.setattr(QuestionnaireTool, "_is_real_idea", fake_is_real_idea)
    monkeypatch.setattr(QuestionnaireTool, "_plan", fake_plan)
    monkeypatch.setattr(RouterAgent, "classify", fake_classify)

    async def scenario():
        session = await _make_session()
        sid = session.id
        graph = build_graph()
        ps = await _subscribe(sid)
        try:
            result = await process_job(
                {"session_id": sid, "user_input": "Start the business questionnaire"},
                graph,
            )
            events = await _collect(ps, 2)

            types = [m["type"] for m in result["messages"]]
            assert "questionnaire_start" not in types
            assert "questionnaire" not in types
            assert types[-1] == "chat"  # assistant asks for the real idea

            # No questionnaire context was created, and nothing was folded in.
            assert business_context(result["messages"]) == {}
            assert not questionnaire_pending(result["messages"])

            msgs = await db.message.find_many(where={"sessionId": sid})
            assert [m.agent for m in msgs] == ["TOOL", "TOOL"]

            await ps.unsubscribe(f"stream:{sid}")
            await ps.close()
        finally:
            await _cleanup(sid)

    _run(scenario())


def test_questionnaire_auto_starts_then_collects(monkeypatch):
    async def fake_plan(self, idea):
        return {
            "facts": {"business_about": idea, "business_location": "Pune"},
            "questions": [
                {"key": "q1", "question": "Who is your target customer?"},
                {"key": "q2", "question": "How will you fund this?"},
            ],
        }

    async def fake_parse(self, questions, answers_text):
        return ["Young professionals in Pune", "Self-funded"]

    async def fake_validate(self, questions, answers_text):
        return True

    async def fake_is_real_idea(self, idea):
        return True

    async def fake_classify(self, user_input, messages, tools):
        return {"intent": "tool", "tool": "questionnaire"}

    monkeypatch.setattr(QuestionnaireTool, "_plan", fake_plan)
    monkeypatch.setattr(QuestionnaireTool, "_parse", fake_parse)
    monkeypatch.setattr(QuestionnaireTool, "_validate", fake_validate)
    monkeypatch.setattr(QuestionnaireTool, "_is_real_idea", fake_is_real_idea)
    monkeypatch.setattr(RouterAgent, "classify", fake_classify)

    async def scenario():
        session = await _make_session()
        sid = session.id
        graph = build_graph()
        ps = await _subscribe(sid)
        try:
            first = await process_job(
                {"session_id": sid, "user_input": TEST_IDEA}, graph
            )
            events1 = await _collect(ps, 3)

            assert first["messages"][0]["type"] == "questionnaire_start"
            questions_msg = first["messages"][1]
            assert questions_msg["type"] == "questionnaire"
            assert [q["key"] for q in questions_msg["questions"]] == ["q1", "q2"]

            assert events1[0]["type"] == "questionnaire"
            assert [q["key"] for q in events1[0]["questions"]] == ["q1", "q2"]
            assert events1[-1]["type"] == "end"

            second = await process_job(
                {"session_id": sid, "user_input": "Young professionals. Self-funded."},
                graph,
            )
            events2 = await _collect(ps, 3)

            types = [m["type"] for m in second["messages"]]
            assert types == [
                "questionnaire_start",
                "questionnaire",
                "questionnaire_answer",
                "questionnaire_complete",
            ]
            assert second["messages"][2]["answers"]["q1"] == "Young professionals in Pune"
            assert events2[0]["type"] == "questionnaire_complete"
            assert business_context(second["messages"])["business_location"] == "Pune"

            msgs = await db.message.find_many(where={"sessionId": sid})
            assert sorted(m.agent for m in msgs) == ["TOOL", "TOOL", "TOOL", "TOOL"]

            await ps.unsubscribe(f"stream:{sid}")
            await ps.close()
        finally:
            await _cleanup(sid)

    _run(scenario())


def test_tool_flow_routes_and_streams(monkeypatch):
    async def fake_classify(self, user_input, messages, tools):
        return {"intent": "tool", "tool": "web_search"}

    def fake_search_run(self, state):
        return [
            {"role": "USER", "agent": "TOOL", "type": "research_request", "content": "q"},
            {"role": "ASSISTANT", "agent": "TOOL", "type": "research", "content": "FAKE RESEARCH"},
        ]

    monkeypatch.setattr(RouterAgent, "classify", fake_classify)
    monkeypatch.setattr(WebSearchTool, "run", fake_search_run)

    async def scenario():
        session = await _make_session()
        sid = session.id
        await add_message(sid, "USER", "CHAT", {"type": "chat", "content": "seed"})
        graph = build_graph()
        ps = await _subscribe(sid)
        try:
            result = await process_job(
                {"session_id": sid, "user_input": "search competitors"}, graph
            )
            events = await _collect(ps, 3)

            assert result["messages"][-1]["type"] == "research"
            assert result["messages"][-1]["content"] == "FAKE RESEARCH"
            assert events[0] == {"type": "research", "content": "FAKE RESEARCH"}
            assert events[1]["type"] == "suggestions"
            assert events[2]["type"] == "end"

            msgs = await db.message.find_many(where={"sessionId": sid})
            assert sorted(m.agent for m in msgs) == ["CHAT", "TOOL", "TOOL"]

            await ps.unsubscribe(f"stream:{sid}")
            await ps.close()
        finally:
            await _cleanup(sid)

    _run(scenario())


def test_unknown_tool_falls_back_to_chat(monkeypatch):
    async def fake_classify(self, user_input, messages, tools):
        return {"intent": "tool", "tool": "does_not_exist"}

    async def fake_chat(self, user_input, transcript, context, tools):
        return "FAKE CHAT REPLY"

    monkeypatch.setattr(RouterAgent, "classify", fake_classify)
    monkeypatch.setattr(ChatAgent, "run", fake_chat)

    async def scenario():
        session = await _make_session()
        sid = session.id
        await add_message(sid, "USER", "CHAT", {"type": "chat", "content": "seed"})
        graph = build_graph()
        ps = await _subscribe(sid)
        try:
            result = await process_job(
                {"session_id": sid, "user_input": "do the impossible"}, graph
            )
            events = await _collect(ps, 3)
            assert events[0]["type"] == "chat"
            assert result["messages"][-1]["content"] == "FAKE CHAT REPLY"

            await ps.unsubscribe(f"stream:{sid}")
            await ps.close()
        finally:
            await _cleanup(sid)

    _run(scenario())


def test_build_state_from_db_is_order_aware():
    from prisma import Json

    async def scenario():
        session = await _make_session()
        sid = session.id
        try:
            base = datetime.now(UTC)

            def create(role, agent, content, minutes):
                return db.message.create(
                    data={
                        "sessionId": sid,
                        "role": role,
                        "agent": agent,
                        "content": Json(content),
                        "created_at": base + timedelta(minutes=minutes),
                    }
                )

            await create("USER", "TOOL", {"type": "questionnaire_start", "content": "first"}, 3)
            await create("USER", "CHAT", {"type": "chat", "content": "second"}, 1)
            await create("ASSISTANT", "TOOL", {"type": "research", "content": "third"}, 2)

            state = await build_state_from_db(session)
            assert [m["type"] for m in state["messages"]] == [
                "chat",
                "research",
                "questionnaire_start",
            ]

            loaded = await load_state(sid)
            assert [m["type"] for m in loaded["messages"]] == [
                "chat",
                "research",
                "questionnaire_start",
            ]
        finally:
            await _cleanup(sid)

    _run(scenario())

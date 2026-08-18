import asyncio
import json
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from db_service import connect_db, db, disconnect_db
from langchain_core.runnables import RunnableLambda
from redis_service import connect_redis, disconnect_redis, redis

from worker.agent import build_graph, load_state, process_job
from worker.agents.chat_agent import ChatAgent
from worker.agents.router_agent import RouterAgent
from worker.helpers.messages import (
    business_context,
    business_profile,
    format_transcript,
    inject_business_profile,
    questionnaire_pending,
)
from worker.helpers.persistence import add_message, build_state_from_db
from worker.tools.questionnaire_tool import QuestionnaireTool
from worker.tools.swot_tool import SwotTool
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


async def _make_profile_session():
    """Creates a user that has filled in part of their business profile."""
    from prisma import Json

    session = await _make_session()
    await db.businessprofile.create(
        data={
            "userId": session.userId,
            "content": Json({"your_name": "Cafe Pune", "location": "Pune"}),
        }
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
    """Chat replies are persisted and streamed, and once the questionnaire is
    completed the turn ends with a `suggestions` event listing the tools."""
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
        # Questionnaire completed → suggestions are streamed after this turn.
        await add_message(sid, "ASSISTANT", "TOOL",
                          {"type": "questionnaire_complete", "content": "done",
                           "context": {"business_about": TEST_IDEA}})
        graph = build_graph()
        ps = await _subscribe(sid)
        try:
            result = await process_job({"session_id": sid, "user_input": "Hello"}, graph)
            events = await _collect(ps, 3)

            types = [m["type"] for m in result["messages"]]
            assert types == ["chat", "questionnaire_complete", "chat", "chat"]

            event_types = [e["type"] for e in events]
            assert event_types == ["chat", "suggestions", "end"]
            assert events[0]["content"] == "FAKE CHAT REPLY"
            assert {t["name"] for t in events[1]["tools"]} == {
                "swot",
                "web_search",
                "finance",
            }

            msgs = await db.message.find_many(where={"sessionId": sid})
            assert sorted(m.agent for m in msgs) == ["CHAT", "CHAT", "CHAT", "TOOL"]
            assert [m.role for m in msgs[:2]] == ["USER", "ASSISTANT"]

            await ps.unsubscribe(f"stream:{sid}")
            await ps.close()
        finally:
            await _cleanup(sid)

    _run(scenario())


def test_first_message_greeting_goes_to_chat(monkeypatch):
    """A greeting on a fresh session (no questionnaire yet) goes to the chat
    agent. Suggestions are NOT streamed until the questionnaire is answered."""
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
            events = await _collect(ps, 2)

            assert [m["type"] for m in result["messages"]] == ["chat", "chat"]
            assert result["messages"][0]["role"] == "USER"
            assert result["messages"][1]["role"] == "ASSISTANT"
            assert result["messages"][1]["content"] == (
                "Hi! I'm KapexAI, your business consultant. How can I help your business?"
            )
            assert events[0]["type"] == "chat"
            # No suggestions before the questionnaire is answered.
            assert events[1]["type"] == "end"
            assert not any(e["type"] == "suggestions" for e in events)

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

    async def fake_is_clarification(self, questions, answers_text):
        return False

    async def fake_is_real_idea(self, idea):
        return True

    async def fake_classify(self, user_input, messages, tools):
        return {"intent": "tool", "tool": "questionnaire"}

    monkeypatch.setattr(QuestionnaireTool, "_plan", fake_plan)
    monkeypatch.setattr(QuestionnaireTool, "_validate", fake_validate)
    monkeypatch.setattr(QuestionnaireTool, "_parse", fake_parse)
    monkeypatch.setattr(QuestionnaireTool, "_is_clarification", fake_is_clarification)
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


def test_questionnaire_answers_clarifying_question(monkeypatch):
    """A clarifying question about the questionnaire itself (e.g. 'can you
    explain this in clear words?') must NOT be rejected as a bad answer and
    re-asked. It gets a plain-language explanation while the questionnaire stays
    pending, so a real answer on the next turn completes it."""

    async def fake_plan(self, idea):
        return {
            "facts": {"business_about": idea},
            "questions": [{"key": "q1", "question": "Who is your target customer?"}],
        }

    async def fake_validate(self, questions, answers_text):
        return "clear words" not in answers_text

    async def fake_is_clarification(self, questions, answers_text):
        return "clear words" in answers_text

    async def fake_explain(self, questions, facts, user_text):
        return [
            {"role": "USER", "agent": "TOOL", "type": "chat", "content": user_text},
            {
                "role": "ASSISTANT",
                "agent": "TOOL",
                "type": "chat",
                "content": "In simple terms, I'd like to know who your shop is for. "
                "For example, students, working professionals, or tourists.",
            },
        ]

    async def fake_parse(self, questions, answers_text):
        return [answers_text]

    async def fake_is_real_idea(self, idea):
        return True

    async def fake_classify(self, user_input, messages, tools):
        return {"intent": "tool", "tool": "questionnaire"}

    monkeypatch.setattr(QuestionnaireTool, "_plan", fake_plan)
    monkeypatch.setattr(QuestionnaireTool, "_validate", fake_validate)
    monkeypatch.setattr(QuestionnaireTool, "_is_clarification", fake_is_clarification)
    monkeypatch.setattr(QuestionnaireTool, "_explain", fake_explain)
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
                {"session_id": sid, "user_input": "1) can you explain this in clear words.."},
                graph,
            )
            await _collect(ps, 2)

            types = [m["type"] for m in second["messages"]]
            # The clarifying question is answered conversationally — no
            # questionnaire_invalid rejection, no completion, still pending.
            assert "questionnaire_invalid" not in types
            assert "questionnaire_complete" not in types
            assert "questionnaire_answer" not in types
            assert types[-2:] == ["chat", "chat"]
            assert "simple terms" in second["messages"][-1]["content"].lower()
            assert questionnaire_pending(second["messages"])

            # A real answer on the next turn completes the questionnaire.
            third = await process_job(
                {"session_id": sid, "user_input": "Young professionals in Pune"}, graph
            )
            await _collect(ps, 3)
            assert third["messages"][-1]["type"] == "questionnaire_complete"
            assert (
                third["messages"][-1]["context"].get("q1")
                == "Young professionals in Pune"
            )

            await ps.unsubscribe(f"stream:{sid}")
            await ps.close()
        finally:
            await _cleanup(sid)

    _run(scenario())


def test_questionnaire_structured_clarification_explains(monkeypatch):
    """The deck's 'explain in simpler words' button sends a structured
    clarification payload; the tool explains the requested questions with chat
    bubbles and keeps the questionnaire pending (no rejection, no completion)."""

    async def fake_plan(self, idea):
        return {
            "facts": {"business_about": idea},
            "questions": [
                {"key": "q1", "question": "What product?"},
                {"key": "q2", "question": "Who is your target customer?"},
            ],
        }

    async def fake_explain(self, questions, facts, user_text):
        return [
            {"role": "USER", "agent": "TOOL", "type": "chat", "content": user_text},
            {
                "role": "ASSISTANT",
                "agent": "TOOL",
                "type": "chat",
                "content": "In plain words, I want to know who you will sell to.",
            },
        ]

    async def fake_validate_structured(self, questions, answers):
        return {a["key"]: True for a in answers}

    async def fake_is_real_idea(self, idea):
        return True

    async def fake_classify(self, user_input, messages, tools):
        return {"intent": "tool", "tool": "questionnaire"}

    monkeypatch.setattr(QuestionnaireTool, "_plan", fake_plan)
    monkeypatch.setattr(QuestionnaireTool, "_explain", fake_explain)
    monkeypatch.setattr(
        QuestionnaireTool, "_validate_structured", fake_validate_structured
    )
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

            payload = json.dumps(
                {"kind": "questionnaire_clarification", "keys": ["q2"]}
            )
            second = await process_job(
                {"session_id": sid, "user_input": payload}, graph
            )
            await _collect(ps, 2)

            types = [m["type"] for m in second["messages"]]
            assert "questionnaire_invalid" not in types
            assert "questionnaire_complete" not in types
            assert "questionnaire_answer" not in types
            assert types[-2:] == ["chat", "chat"]
            assert "plain words" in second["messages"][-1]["content"]
            assert questionnaire_pending(second["messages"])

            # The deck can still be answered afterwards.
            answers_payload = json.dumps(
                {
                    "kind": "questionnaire_answers",
                    "answers": [
                        {"key": "q1", "answer": "custom apparel"},
                        {"key": "q2", "answer": "local event organizers"},
                    ],
                }
            )
            third = await process_job(
                {"session_id": sid, "user_input": answers_payload}, graph
            )
            await _collect(ps, 2)
            assert third["messages"][-1]["type"] == "questionnaire_complete"
            assert third["messages"][-1]["context"]["q2"] == "local event organizers"

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


def test_questionnaire_structured_answers_bypass_parsing(monkeypatch):
    """Structured answers from the slide UI map 1:1 onto the questions without
    running the LLM validate/parse steps for *free-form* text, so genuine
    per-question answers are never rejected. (They still get per-answer
    validation via `_validate_structured`, patched here to all-valid.)"""
    async def fake_plan(self, idea):
        return {
            "facts": {"business_about": idea},
            "questions": [
                {"key": "q1", "question": "What product?"},
                {"key": "q2", "question": "Where do you source?"},
                {"key": "q3", "question": "Who is your target customer?"},
            ],
        }

    async def fake_is_real_idea(self, idea):
        return True

    async def fake_validate(self, questions, answers_text):
        raise AssertionError("_validate must not run for structured answers")

    async def fake_validate_structured(self, questions, answers):
        return {a["key"]: True for a in answers}

    async def fake_parse(self, questions, answers_text):
        raise AssertionError("_parse must not run for structured answers")

    async def fake_classify(self, user_input, messages, tools):
        return {"intent": "tool", "tool": "questionnaire"}

    monkeypatch.setattr(QuestionnaireTool, "_plan", fake_plan)
    monkeypatch.setattr(QuestionnaireTool, "_is_real_idea", fake_is_real_idea)
    monkeypatch.setattr(QuestionnaireTool, "_validate", fake_validate)
    monkeypatch.setattr(
        QuestionnaireTool, "_validate_structured", fake_validate_structured
    )
    monkeypatch.setattr(QuestionnaireTool, "_parse", fake_parse)
    monkeypatch.setattr(RouterAgent, "classify", fake_classify)

    async def scenario():
        session = await _make_session()
        sid = session.id
        graph = build_graph()
        ps = await _subscribe(sid)
        try:
            await process_job({"session_id": sid, "user_input": TEST_IDEA}, graph)
            await _collect(ps, 3)

            payload = json.dumps(
                {
                    "kind": "questionnaire_answers",
                    "answers": [
                        {"key": "q1", "answer": "dried mango"},
                        {"key": "q2", "answer": "local farms"},
                        {"key": "q3", "answer": "local market"},
                    ],
                }
            )
            second = await process_job(
                {"session_id": sid, "user_input": payload}, graph
            )
            events = await _collect(ps, 3)

            types = [m["type"] for m in second["messages"]]
            assert types == [
                "questionnaire_start",
                "questionnaire",
                "questionnaire_answer",
                "questionnaire_complete",
            ]
            complete = second["messages"][-1]
            assert complete["type"] == "questionnaire_complete"
            assert complete["context"]["q1"] == "dried mango"
            assert complete["context"]["q2"] == "local farms"
            assert complete["context"]["q3"] == "local market"

            # The user bubble shows a readable summary, not the raw JSON payload.
            answer_msg = second["messages"][-2]
            assert answer_msg["content"] == (
                "1) dried mango\n2) local farms\n3) local market"
            )
            assert "kind" not in answer_msg["content"]

            assert events[0]["type"] == "questionnaire_complete"
            assert not questionnaire_pending(second["messages"])
            assert business_context(second["messages"])["q1"] == "dried mango"

            msgs = await db.message.find_many(where={"sessionId": sid})
            assert len(msgs) == 4

            await ps.unsubscribe(f"stream:{sid}")
            await ps.close()
        finally:
            await _cleanup(sid)

    _run(scenario())


def test_validate_structured_prompt_renders():
    """The structured-answers validator prompt must render without treating the
    JSON literals inside it (e.g. {"valid": true|false}) as template variables."""
    from worker.prompts.questionnaire import VALIDATE_STRUCTURED_ANSWER_TEMPLATE

    rendered = VALIDATE_STRUCTURED_ANSWER_TEMPLATE.invoke(
        {
            "question": "What product?",
            "answer": "dried mango",
        }
    ).to_string()
    assert '{"valid": true|false}' in rendered


def test_questionnaire_structured_garbage_answers_rejected(monkeypatch):
    """Totally random structured answers (e.g. "hehe", "bruh", "loool") must be
    rejected per answer — the questionnaire stays pending and nothing garbage
    enters the business context."""
    async def fake_plan(self, idea):
        return {
            "facts": {"business_about": idea},
            "questions": [
                {"key": "q1", "question": "What product?"},
                {"key": "q2", "question": "Where do you source?"},
                {"key": "q3", "question": "Who is your target customer?"},
            ],
        }

    async def fake_is_real_idea(self, idea):
        return True

    async def fake_validate_structured(self, questions, answers):
        return {a["key"]: False for a in answers}

    async def fake_classify(self, user_input, messages, tools):
        return {"intent": "tool", "tool": "questionnaire"}

    monkeypatch.setattr(QuestionnaireTool, "_plan", fake_plan)
    monkeypatch.setattr(QuestionnaireTool, "_is_real_idea", fake_is_real_idea)
    monkeypatch.setattr(
        QuestionnaireTool, "_validate_structured", fake_validate_structured
    )
    monkeypatch.setattr(RouterAgent, "classify", fake_classify)

    async def scenario():
        session = await _make_session()
        sid = session.id
        graph = build_graph()
        ps = await _subscribe(sid)
        try:
            await process_job({"session_id": sid, "user_input": TEST_IDEA}, graph)
            await _collect(ps, 3)

            payload = json.dumps(
                {
                    "kind": "questionnaire_answers",
                    "answers": [
                        {"key": "q1", "answer": "hehe"},
                        {"key": "q2", "answer": "bruh"},
                        {"key": "q3", "answer": "loool"},
                    ],
                }
            )
            second = await process_job(
                {"session_id": sid, "user_input": payload}, graph
            )
            events = await _collect(ps, 2)

            types = [m["type"] for m in second["messages"]]
            # The submission is recorded but the questions are re-asked — no
            # completion, so the questionnaire stays pending.
            assert types[-2:] == ["questionnaire_invalid", "questionnaire"]
            assert questionnaire_pending(second["messages"])

            # The re-ask card shows ALL questions again (all answers were bad).
            reask = second["messages"][-1]
            assert [q["key"] for q in reask["questions"]] == ["q1", "q2", "q3"]
            assert "business_about" in reask["facts"]
            assert "q1" not in reask["facts"]

            # The invalid USER bubble is the readable summary, not the JSON.
            invalid = second["messages"][-2]
            assert invalid["content"] == "1) hehe\n2) bruh\n3) loool"

            assert events[0]["type"] == "questionnaire"
            # The garbage must not leak into the business context.
            ctx = business_context(second["messages"])
            assert "q1" not in ctx and "q2" not in ctx and "q3" not in ctx

            msgs = await db.message.find_many(where={"sessionId": sid})
            assert len(msgs) == 4

            await ps.unsubscribe(f"stream:{sid}")
            await ps.close()
        finally:
            await _cleanup(sid)

    _run(scenario())


def test_questionnaire_structured_partial_garbage_keeps_valid(monkeypatch):
    """When only some structured answers are garbage, the valid ones are folded
    into the context and only the bad questions are re-asked."""
    async def fake_plan(self, idea):
        return {
            "facts": {"business_about": idea},
            "questions": [
                {"key": "q1", "question": "What product?"},
                {"key": "q2", "question": "Where do you source?"},
                {"key": "q3", "question": "Who is your target customer?"},
            ],
        }

    async def fake_is_real_idea(self, idea):
        return True

    async def fake_validate_structured(self, questions, answers):
        return {a["key"]: a["key"] != "q2" for a in answers}

    async def fake_classify(self, user_input, messages, tools):
        return {"intent": "tool", "tool": "questionnaire"}

    monkeypatch.setattr(QuestionnaireTool, "_plan", fake_plan)
    monkeypatch.setattr(QuestionnaireTool, "_is_real_idea", fake_is_real_idea)
    monkeypatch.setattr(
        QuestionnaireTool, "_validate_structured", fake_validate_structured
    )
    monkeypatch.setattr(RouterAgent, "classify", fake_classify)

    async def scenario():
        session = await _make_session()
        sid = session.id
        graph = build_graph()
        ps = await _subscribe(sid)
        try:
            await process_job({"session_id": sid, "user_input": TEST_IDEA}, graph)
            await _collect(ps, 3)

            payload = json.dumps(
                {
                    "kind": "questionnaire_answers",
                    "answers": [
                        {"key": "q1", "answer": "dried mango"},
                        {"key": "q2", "answer": "bruh"},
                        {"key": "q3", "answer": "local market"},
                    ],
                }
            )
            second = await process_job(
                {"session_id": sid, "user_input": payload}, graph
            )
            await _collect(ps, 2)

            types = [m["type"] for m in second["messages"]]
            assert types[-2:] == ["questionnaire_invalid", "questionnaire"]

            # Only q2 was invalid → only q2 is re-asked.
            reask = second["messages"][-1]
            assert [q["key"] for q in reask["questions"]] == ["q2"]
            # The valid q1 answer is retained and persists through the re-ask.
            assert reask["facts"]["q1"] == "dried mango"

            assert questionnaire_pending(second["messages"])

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
        # web_search requires business context → seed a completed questionnaire.
        await add_message(sid, "USER", "TOOL", {"type": "questionnaire_start", "content": TEST_IDEA})
        await add_message(
            sid, "ASSISTANT", "TOOL",
            {"type": "questionnaire", "content": "q", "questions": [{"key": "q1", "question": "who?"}], "facts": {"business_about": TEST_IDEA}},
        )
        await add_message(
            sid, "USER", "TOOL",
            {"type": "questionnaire_answer", "content": "1) people", "answers": {"business_about": TEST_IDEA, "q1": "people"}},
        )
        await add_message(
            sid, "ASSISTANT", "TOOL",
            {"type": "questionnaire_complete", "content": "done", "context": {"business_about": TEST_IDEA, "q1": "people"}},
        )
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
            assert sorted(m.agent for m in msgs) == [
                "CHAT", "TOOL", "TOOL", "TOOL", "TOOL", "TOOL", "TOOL",
            ]

            await ps.unsubscribe(f"stream:{sid}")
            await ps.close()
        finally:
            await _cleanup(sid)

    _run(scenario())


def test_context_tools_gated_until_questionnaire_complete(monkeypatch):
    """SWOT (and other context-requiring tools) must NOT run until the
    questionnaire is completed — the router redirects the request to the
    questionnaire tool so context is gathered first."""
    async def fake_classify(self, user_input, messages, tools):
        return {"intent": "tool", "tool": "swot"}

    async def fake_is_real_idea(self, idea):
        return True

    async def fake_plan(self, idea):
        return {
            "facts": {"business_about": idea},
            "questions": [{"key": "q1", "question": "Who is your target customer?"}],
        }

    async def fake_swot_run(self, state):
        raise AssertionError("swot must not run before the questionnaire is completed")

    monkeypatch.setattr(RouterAgent, "classify", fake_classify)
    monkeypatch.setattr(QuestionnaireTool, "_is_real_idea", fake_is_real_idea)
    monkeypatch.setattr(QuestionnaireTool, "_plan", fake_plan)
    monkeypatch.setattr(SwotTool, "run", fake_swot_run)

    async def scenario():
        session = await _make_session()
        sid = session.id
        graph = build_graph()
        ps = await _subscribe(sid)
        request = "Run a SWOT analysis for my business"
        try:
            result = await process_job(
                {"session_id": sid, "user_input": request},
                graph,
            )
            await _collect(ps, 3)

            types = [m["type"] for m in result["messages"]]
            assert "swot" not in types
            assert "swot_request" not in types
            assert types == ["questionnaire_start", "questionnaire"]
            assert questionnaire_pending(result["messages"])
            assert business_context(result["messages"]) == {"business_about": request}

            await ps.unsubscribe(f"stream:{sid}")
            await ps.close()
        finally:
            await _cleanup(sid)

    _run(scenario())


def test_context_tool_runs_after_questionnaire_complete(monkeypatch):
    """Once the questionnaire is completed, context-requiring tools run as
    usual with the gathered business context."""
    async def fake_classify(self, user_input, messages, tools):
        return {"intent": "tool", "tool": "swot"}

    async def fake_swot_run(self, state):
        return [
            {"role": "USER", "agent": "TOOL", "type": "swot_request", "content": "req"},
            {"role": "ASSISTANT", "agent": "TOOL", "type": "swot", "content": "FAKE SWOT", "sections": {}},
        ]

    monkeypatch.setattr(RouterAgent, "classify", fake_classify)
    monkeypatch.setattr(SwotTool, "run", fake_swot_run)

    async def scenario():
        session = await _make_session()
        sid = session.id
        await add_message(sid, "USER", "TOOL", {"type": "questionnaire_start", "content": TEST_IDEA})
        await add_message(
            sid, "ASSISTANT", "TOOL",
            {"type": "questionnaire", "content": "q", "questions": [{"key": "q1", "question": "who?"}], "facts": {"business_about": TEST_IDEA}},
        )
        await add_message(
            sid, "USER", "TOOL",
            {"type": "questionnaire_answer", "content": "1) people", "answers": {"business_about": TEST_IDEA, "q1": "people"}},
        )
        await add_message(
            sid, "ASSISTANT", "TOOL",
            {"type": "questionnaire_complete", "content": "done", "context": {"business_about": TEST_IDEA, "q1": "people"}},
        )
        graph = build_graph()
        ps = await _subscribe(sid)
        try:
            result = await process_job(
                {"session_id": sid, "user_input": "Run a SWOT analysis"}, graph
            )
            events = await _collect(ps, 3)

            assert result["messages"][-1]["type"] == "swot"
            assert result["messages"][-1]["content"] == "FAKE SWOT"
            assert events[0] == {"type": "swot", "content": "FAKE SWOT", "sections": {}}
            assert events[1]["type"] == "suggestions"
            assert events[2]["type"] == "end"

            await ps.unsubscribe(f"stream:{sid}")
            await ps.close()
        finally:
            await _cleanup(sid)

    _run(scenario())


def test_swot_tool_includes_message_history(monkeypatch):
    """The SWOT tool must pass the conversation transcript (message history) to
    the LLM prompt, alongside the gathered business context."""
    captured = {}

    def fake_template(inputs):
        captured["inputs"] = dict(inputs)
        return "ok"

    def fake_llm(_):
        return SimpleNamespace(
            content=json.dumps(
                {
                    "summary": "test",
                    "sections": {
                        "strengths": ["a"],
                        "weaknesses": ["b"],
                        "opportunities": ["c"],
                        "threats": ["d"],
                    },
                }
            )
        )

    tool = SwotTool()
    tool.llm = RunnableLambda(fake_llm)
    monkeypatch.setattr(
        "worker.tools.swot_tool.SWOT_TEMPLATE", RunnableLambda(fake_template)
    )

    async def scenario():
        entries = await tool.run(
            {
                "session_id": "s",
                "user_input": "Run a SWOT analysis",
                "messages": [
                    {"role": "USER", "agent": "CHAT", "type": "chat", "content": "I plan to sell dried mangoes in Pune."},
                    {"role": "ASSISTANT", "agent": "TOOL", "type": "questionnaire_complete", "content": "done", "context": {"business_about": "dried mangoes", "business_location": "Pune"}},
                ],
            }
        )
        assert entries[1]["type"] == "swot"
        # The transcript (message history) reached the prompt.
        assert captured["inputs"]["transcript"] == (
            "USER (chat): I plan to sell dried mangoes in Pune.\n"
            "ASSISTANT (questionnaire_complete): done"
        )
        # The business context reached the prompt too.
        assert "dried mangoes" in captured["inputs"]["context"]

    _run(scenario())


def test_web_search_tool_includes_message_history():
    """The web search tool must build its system prompt from the business
    context AND the conversation transcript."""
    captured = {}

    class FakeAgent:
        def invoke(self, payload):
            captured["messages"] = payload["messages"]
            return {"messages": [SimpleNamespace(content="FINAL RESEARCH SUMMARY")]}

    tool = WebSearchTool()
    tool.agent = FakeAgent()

    async def scenario():
        entries = tool.run(
            {
                "session_id": "s",
                "user_input": "Who are my top competitors?",
                "messages": [
                    {"role": "USER", "agent": "CHAT", "type": "chat", "content": "I plan to sell dried mangoes in Pune."},
                    {"role": "ASSISTANT", "agent": "TOOL", "type": "questionnaire_complete", "content": "done", "context": {"business_about": "dried mangoes", "business_location": "Pune"}},
                ],
            }
        )
        assert entries[1]["type"] == "research"
        assert entries[1]["content"] == "FINAL RESEARCH SUMMARY"

        system, human = captured["messages"]
        assert system.type == "system"
        assert "dried mangoes" in system.content          # business context
        assert "I plan to sell dried mangoes in Pune." in system.content  # transcript
        assert human.content == "Who are my top competitors?"  # current request

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


def test_inject_business_profile_helpers():
    messages = [
        {"role": "USER", "type": "chat", "content": "hi"},
        {"role": "ASSISTANT", "type": "chat", "content": "hello"},
    ]
    profile = {"your_name": "Cafe Pune", "location": "Pune"}

    injected = inject_business_profile(messages, profile)
    assert msg_types(injected) == ["business_profile", "chat", "chat"]
    assert business_profile(injected) == profile
    # Profile is surfaced in the transcript and merged into the context.
    assert "Cafe Pune" in format_transcript(injected)
    assert business_context(injected)["business_profile"] == profile

    # Missing or all-blank profile → messages are left untouched.
    assert inject_business_profile(messages, {}) == messages
    assert inject_business_profile(messages, {"industry": "   "}) == messages

    # Re-injecting replaces the stale entry instead of duplicating it.
    refreshed = inject_business_profile(injected, {"location": "Mumbai"})
    assert msg_types(refreshed) == ["business_profile", "chat", "chat"]
    assert business_profile(refreshed) == {"location": "Mumbai"}


def msg_types(messages):
    return [m["type"] for m in messages]


def test_business_profile_injected_into_state_and_context(monkeypatch):
    """The user's business profile is injected into the message log on load, so
    `business_context` and the transcript include it without changing tools."""
    async def fake_classify(self, user_input, messages, tools):
        return {"intent": "chat", "tool": None}

    async def fake_chat(self, user_input, transcript, context, tools):
        assert "Cafe Pune" in transcript
        assert context["business_profile"]["location"] == "Pune"
        return "Thanks!"

    monkeypatch.setattr(RouterAgent, "classify", fake_classify)
    monkeypatch.setattr(ChatAgent, "run", fake_chat)

    async def scenario():
        session = await _make_profile_session()
        sid = session.id
        graph = build_graph()
        ps = await _subscribe(sid)
        try:
            # Seed a completed questionnaire so suggestions are streamed too.
            await add_message(sid, "ASSISTANT", "TOOL",
                              {"type": "questionnaire_complete", "content": "done",
                               "context": {"business_about": TEST_IDEA}})
            result = await process_job({"session_id": sid, "user_input": "hi"}, graph)
            await _collect(ps, 3)

            types = [m["type"] for m in result["messages"]]
            assert types == ["business_profile", "questionnaire_complete", "chat", "chat"]

            ctx = business_context(result["messages"])
            assert ctx["business_profile"]["your_name"] == "Cafe Pune"
            # The worker never persisted the profile as a real message.
            msgs = await db.message.find_many(where={"sessionId": sid})
            assert all((m.content or {}).get("type") != "business_profile" for m in msgs)

            await ps.unsubscribe(f"stream:{sid}")
            await ps.close()
        finally:
            await _cleanup(sid)

    _run(scenario())


def test_business_profile_updates_reflect_on_next_job(monkeypatch):
    """Because the profile is injected fresh on every load (replacing the cached
    entry), editing the profile is picked up by the very next job."""
    async def fake_classify(self, user_input, messages, tools):
        return {"intent": "chat", "tool": None}

    async def fake_chat(self, user_input, transcript, context, tools):
        return "ok"

    monkeypatch.setattr(RouterAgent, "classify", fake_classify)
    monkeypatch.setattr(ChatAgent, "run", fake_chat)

    async def scenario():
        from prisma import Json

        session = await _make_profile_session()
        sid = session.id
        graph = build_graph()
        ps = await _subscribe(sid)
        try:
            await process_job({"session_id": sid, "user_input": "hi"}, graph)
            await _collect(ps, 2)

            await db.businessprofile.update(
                where={"userId": session.userId},
                data={
                    "content": Json(
                        {"your_name": "Cafe Mumbai", "location": "Mumbai"}
                    )
                },
            )

            result = await process_job(
                {"session_id": sid, "user_input": "hi again"}, graph
            )
            await _collect(ps, 2)

            profile = business_profile(result["messages"])
            assert profile["your_name"] == "Cafe Mumbai"
            assert profile["location"] == "Mumbai"

            await ps.unsubscribe(f"stream:{sid}")
            await ps.close()
        finally:
            await _cleanup(sid)

    _run(scenario())

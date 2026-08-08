import asyncio
import inspect
import json
import logging
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from redis_service import redis

from worker.agents.chat_agent import ChatAgent
from worker.agents.router_agent import RouterAgent
from worker.helpers.events import publish_stream
from worker.helpers.messages import (
    append_message,
    business_context,
    format_transcript,
    inject_business_profile,
    questionnaire_complete,
    questionnaire_pending,
)
from worker.helpers.persistence import (
    add_message,
    build_state_from_db,
    get_business_profile,
    get_session,
    mark_session_active,
    mark_session_failed,
)
from worker.tools.registry import get_tool, list_tools

logger = logging.getLogger(__name__)

STATE_KEY = "langgraph_state:{session_id}"
STATE_TTL = 60 * 60 * 24  # 24 hours
PENDING_KEY = "pending:{session_id}"


class State(TypedDict):
    session_id: str
    user_id: str
    user_input: str
    messages: list[dict]
    intent: str
    tool: str


router_agent = RouterAgent()
chat_agent = ChatAgent()


async def router_node(state: State) -> dict:
    """Routes the user's message to a chat reply or a specific tool. On a fresh
    session the LLM decides whether to greet (chat) or kick off the
    questionnaire; while a questionnaire is pending, answers are routed back to
    it automatically. Tools that need business context (SWOT, web research) are
    gated: until the questionnaire is completed they are redirected to the
    questionnaire tool so context exists before the tool runs."""
    if questionnaire_pending(state["messages"]):
        return {"intent": "tool", "tool": "questionnaire"}
    
    decision = await router_agent.classify(
        state["user_input"], state["messages"], list_tools()
    )

    if decision.get("intent") == "tool" and get_tool(decision.get("tool", "")):
        tool = get_tool(decision["tool"])
        
        if tool.name == "questionnaire" and questionnaire_complete(state["messages"]):
            return {"intent": "chat"}
        if tool.requires_context and not questionnaire_complete(state["messages"]):
            return {"intent": "tool", "tool": "questionnaire"}
        return {"intent": "tool", "tool": decision["tool"]}
    
    return {"intent": "chat"}


async def chat_node(state: State) -> dict:
    session_id = state["session_id"]
    user_input = state["user_input"]
    context = business_context(state["messages"])
    transcript = format_transcript(state["messages"])

    reply = await chat_agent.run(user_input, transcript, context, list_tools())

    user_entry = {"role": "USER", "agent": "CHAT", "type": "chat", "content": user_input}
    assistant_entry = {
        "role": "ASSISTANT",
        "agent": "CHAT",
        "type": "chat",
        "content": reply,
    }

    messages = append_message(state["messages"], user_entry)
    messages = append_message(messages, assistant_entry)

    await add_message(session_id, "USER", "CHAT", {"type": "chat", "content": user_input})
    await add_message(
        session_id, "ASSISTANT", "CHAT", {"type": "chat", "content": reply}
    )

    await publish_stream(session_id, {"type": "chat", "content": reply})

    if questionnaire_complete(state["messages"]):
        await publish_suggestions(session_id, state["messages"])

    await publish_stream(session_id, {"type": "end"})
    return {"messages": messages}


async def tool_node(state: State) -> dict:
    session_id = state["session_id"]
    tool = get_tool(state.get("tool", ""))
    
    if tool is None:
        return await chat_node(state)

    if inspect.iscoroutinefunction(tool.run):
        entries = await tool.run(state)
    else:
        entries = await asyncio.to_thread(tool.run, state)

    messages = list(state["messages"])
    for entry in entries or []:
        content = {k: v for k, v in entry.items() if k not in ("role", "agent")}
        messages = append_message(messages, entry)
        await add_message(session_id, entry["role"], entry["agent"], content)
        if entry.get("role") == "ASSISTANT":
            await publish_stream(session_id, content)

    if questionnaire_complete(messages):
        await publish_suggestions(session_id, messages)

    await publish_stream(session_id, {"type": "end"})
    return {"messages": messages}


async def publish_suggestions(session_id: str, messages: list[dict]) -> None:
    """Streams the available tool suggestions. The questionnaire tool is left
    out once it has been completed — re-offering it would be pointless."""
    tools = list_tools()
    if questionnaire_complete(messages):
        tools = [t for t in tools if t["name"] != "questionnaire"]
    await publish_stream(session_id, {"type": "suggestions", "tools": tools})


def route(state: State) -> str:
    if state.get("intent") == "chat":
        return "chat"
    if state.get("intent") == "tool":
        return "tool"
    return END


def build_graph() -> CompiledStateGraph:
    graph = StateGraph(State)

    graph.add_node("router", router_node)
    graph.add_node("chat", chat_node)
    graph.add_node("tool", tool_node)

    graph.add_edge(START, "router")
    graph.add_conditional_edges(
        "router",
        route,
        {"chat": "chat", "tool": "tool", END: END},
    )
    graph.add_edge("chat", END)
    graph.add_edge("tool", END)

    return graph.compile()


async def load_state(session_id: str) -> State:
    raw = await redis.get(STATE_KEY.format(session_id=session_id))
    if raw:
        state = json.loads(raw)
        state.setdefault("messages", [])
        state.setdefault("intent", "")
        state.setdefault("tool", "")
        state.setdefault("user_id", "")
    else:
        session = await get_session(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")
        state = await build_state_from_db(session)

    # Inject the user's business profile into the message log. This is done fresh
    # on every load (replacing any stale cached entry), so a profile edit shows
    # up in the very next job — the messages/cache never go stale.
    row = await get_business_profile(state.get("user_id", ""))
    profile = row.content if row else {}
    if isinstance(profile, dict):
        state["messages"] = inject_business_profile(state["messages"], profile)
    return state


async def save_state(session_id: str, state: State) -> None:
    await redis.set(
        STATE_KEY.format(session_id=session_id),
        json.dumps(state),
        ex=STATE_TTL,
    )


async def process_job(job: dict, graph: CompiledStateGraph) -> State:
    session_id = job["session_id"]
    job_id = str(job.get("job_id", "") or "")
    user_input = str(job.get("user_input", "") or "")
    
    try:
        state = await load_state(session_id)
        state["user_input"] = user_input
        result = await graph.ainvoke(state)
        await save_state(session_id, result)
        # The job is done — the backend's in-flight marker is no longer needed.
        await redis.delete(PENDING_KEY.format(session_id=session_id))
        await mark_session_active(session_id)
        return result
    except Exception:
        logger.exception("Failed to process session %s (job %s)", session_id, job_id)
        try:
            await mark_session_failed(session_id)
            await redis.delete(PENDING_KEY.format(session_id=session_id))
            await publish_stream(
                session_id,
                {
                    "type": "error",
                    "job_id": job_id,
                    "content": f"Job {job_id} failed" if job_id else "Job failed",
                },
            )
        except Exception:
            logger.exception("Failed to notify error for session %s", session_id)
        raise

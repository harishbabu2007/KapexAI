# Agentic Pipeline

This document explains how KapexAI's agentic pipeline works: how a user message
becomes a job, how the worker's LangGraph router decides what to do, how tools
produce messages, and how everything is persisted and streamed.

## High-level flow

```
Frontend                    Backend                      Worker
   │                          │                           │
   │  POST /create_chat_session  (or /push_chat_message)   │
   │─────────────────────────►│                           │
   │                          │  1. Create/find Session   │
   │                          │  2. LPUSH jobs:queue      │
   │  { session_id, job_id }  │──────────────────────────►│
   │◄─────────────────────────│  3. BRPOP jobs:queue      │
   │                          │                           │
   │  WS /ws/session/{id}     │                           │
   │════════════════════════►│                           │
   │                          │  4. Run LangGraph router  │
   │                          │  5. PUBLISH stream:{id}   │
   │◄═════════════════════════│◄──────────────────────────│
   │   { type: "chat" }       │   (via redis.publish)     │
   │◄═════════════════════════│◄──────────────────────────│
   │   { type: "suggestions" }│                           │
   │◄═════════════════════════│◄──────────────────────────│
   │   { type: "end" }        │                           │
```

The pipeline is *message-driven*: every turn starts with a user message and ends
with an assistant message plus a `suggestions` frame. There is no fixed
multi-stage workflow — the router decides per-message whether to chat or run a
tool.

## The graph (`worker/agent.py`)

The worker runs a small LangGraph `StateGraph` with three nodes:

```
START → router ── chat ──▶ chat_node ──▶ END
               └─ tool ──▶ tool_node ──▶ END
```

### `router_node`

Decides how to handle the current message, in priority order:

1. **Pending questionnaire** — if the questionnaire asked questions and they
   have not been answered yet, route to the `questionnaire` tool again
   (`questionnaire_pending` in `worker/helpers/messages.py`).
2. **LLM intent classification** — otherwise `RouterAgent` (`worker/agents/router_agent.py`)
   reads the tool registry and the transcript, and returns either
   `{"intent": "chat"}` or `{"intent": "tool", "tool": "<name>"}`. If the
   selected tool is not registered, it falls back to `chat`. On a new session
   the router prompt tells the LLM to send greetings/small talk to `chat` and to
   route a shared business idea to the `questionnaire` tool.

### `chat_node`

Runs `ChatAgent` (a strictly business-focused consultant persona). It is given:

- the message transcript (`format_transcript`),
- the extracted business context (`business_context` — whatever the
  questionnaire has gathered),
- the list of available tools (so it can *suggest* them).

It persists the user message and the reply as `CHAT` messages, then streams
`chat` → `suggestions` → `end`. The persona handles greetings/small talk briefly
but declines and redirects anything outside business topics.

### `tool_node`

Looks up `state["tool"]` in the registry and calls `tool.run(state)`. Sync tools
run via `asyncio.to_thread` so the event loop is not blocked. Every message the
tool returns is persisted, and assistant messages are streamed. It finishes with
`suggestions` → `end`. If the tool is unknown it delegates to `chat_node`.

## State: a message log

LangGraph state is intentionally minimal (`worker/agent.py`):

```python
class State(TypedDict):
    session_id: str
    user_id: str
    user_input: str
    messages: list[dict]   # the conversation log
    intent: str            # "chat" | "tool"
    tool: str              # tool name when intent == "tool"
```

There are no phase/answers/report fields. The conversation lives entirely in
`messages`, and every entry has its own JSON shape defined by the tool that
produced it:

```json
{ "role": "USER|ASSISTANT", "agent": "CHAT|TOOL|...", "type": "...", "content": "...", ... }
```

### Loading & saving

- **Cache** — the full state is stored in Redis at `langgraph_state:{session_id}`
  with a 24h TTL (`save_state` / `load_state`).
- **Rebuild** — if the Redis state is gone, `build_state_from_db`
  (`worker/helpers/persistence.py`) reconstructs the log from the `Message`
  table, **ordered by `created_at` ascending**, so the conversation is rebuilt
  in sequence (a mid-questionnaire session correctly resumes where it left off).

### Persistence

Every log entry the tools/nodes produce is also written to the `Message` table
via `add_message` (`worker/helpers/persistence.py`). The `Message.agent` column
uses the `Agent` enum: `CHAT` for chat messages, `TOOL` for tool messages (the
specific tool is recoverable from `content.type`), `QUESTIONNAIRE`/`RESEARCH`/
`REPORT`/`GUARDRAIL` remain for legacy rows.

## Tools (`worker/tools/`)

Tools are the plug-and-play capabilities of the assistant. A tool:

1. tells the router when to use it (`description`, `example`),
2. advertises itself to the user (`suggestion`),
3. handles the message and returns log entries (`run`).

### Tool interface (`base.py`)

```python
class Tool:
    name: str = ""
    description: str = ""   # shown to the router for intent classification
    example: str = ""       # example user prompt
    suggestion: str = ""    # "wanna try this next?" phrase for the frontend

    def run(self, state: dict) -> list[dict]:
        """Return message log entries. May be sync or async.
        Each entry: {"role", "agent", "type", "content", ...extra}."""
```

### Registry (`registry.py`)

Tools register themselves once and are automatically picked up by the router,
the chat agent, and the `suggestions` frame:

```python
register(QuestionnaireTool())
register(SwotTool())
register(WebSearchTool())
```

### Built-in tools

| Tool | `type` (assistant msg) | What it does |
|---|---|---|
| `questionnaire` | `questionnaire` / `questionnaire_complete` | Multi-turn: asks up to 5 targeted questions on the first message, then parses the answers into structured business context |
| `swot` | `swot` | Generates a SWOT analysis as structured sections |
| `web_search` | `research` | Live web research via a Tavily-powered react agent |

## Message formats

Each tool owns the JSON format of the messages it emits. The `type` field
distinguishes them; extra fields carry tool-specific data.

### Chat (`agent: "CHAT"`)

| role | `type` | extra fields |
|---|---|---|
| USER | `chat` | `content` |
| ASSISTANT | `chat` | `content` |

### Questionnaire (`agent: "TOOL"`)

| role | `type` | extra fields |
|---|---|---|
| USER | `questionnaire_start` | `content` (the business idea) |
| ASSISTANT | `questionnaire` | `content`, `questions: [{key, question}]`, `facts: {...}` |
| USER | `questionnaire_answer` | `content` (raw answers), `answers: {...}` |
| ASSISTANT | `questionnaire_complete` | `content`, `context: {...}` (the parsed business context) |

The `context` from `questionnaire_complete` is what the chat agent and the SWOT
tool use as *business context* for later turns.

### SWOT (`agent: "TOOL"`)

| role | `type` | extra fields |
|---|---|---|
| USER | `swot_request` | `content` |
| ASSISTANT | `swot` | `content` (markdown), `sections: {strengths, weaknesses, opportunities, threats}`, `summary` |

### Web search (`agent: "TOOL"`)

| role | `type` | extra fields |
|---|---|---|
| USER | `research_request` | `content` |
| ASSISTANT | `research` | `content` |

## Streaming protocol

Each node publishes JSON frames to the pub/sub channel `stream:{session_id}`
(`worker/helpers/events.py`). The backend WebSocket endpoint
`ws/session/{session_id}` forwards them verbatim to the frontend.

| `type` | Payload | Description |
|---|---|---|
| `chat` | `content` | A chat reply |
| `questionnaire` | `content`, `questions`, `facts` | Questionnaire questions (all at once) |
| `questionnaire_complete` | `content`, `context` | Acknowledges the collected answers |
| `swot` | `content`, `sections`, `summary` | SWOT analysis result |
| `research` | `content` | Web search result |
| `suggestions` | `tools: [{name, description, example, suggestion}]` | "wanna try this next?" — the user can pick one to trigger a tool |
| `end` | — | Signals the turn is finished |
| `error` | `job_id`, `content` | The job failed; the session is marked `FAILED` |

User messages (e.g. `questionnaire_start`, `research_request`) are persisted but
**not** streamed — the client already has what the user typed.

## Adding a new tool

1. Create `worker/tools/<name>_tool.py` with a class that subclasses `Tool`.
2. Set `name`, `description`, `example`, `suggestion`.
3. Implement `run(state)` → list of log entries (sync or async). Emit a USER
   entry for the request and an ASSISTANT entry for the result, using your own
   `type` and extra fields.
4. Register it in `worker/tools/registry.py`.

That's it — the router prompt, chat context, and `suggestions` frame all read
from the registry, so the new tool is immediately visible to the model and the
frontend. Example (a future "location trend analysis" tool would follow the same
pattern as `swot_tool.py`).

## Error handling

If a job fails, `process_job` marks the session `FAILED` and publishes an
`error` frame containing the `job_id` so the failure can be correlated with the
submission that caused it.

## Key considerations

- **One tool per message** — the router picks a single intent. Chaining (e.g.
  "web search, then SWOT") is not yet supported and would require either a
  `chain` intent or letting tools invoke other tools.
- **Pub/sub is fire-and-forget** — if no WebSocket is connected, stream frames
  are lost; the DB `Message` log is the durable record.
- **Per-session serialization** — the queue is global, so two jobs for the same
  session are processed in arrival order by the single worker; with multiple
  workers you would need per-session locking.
- **The questionnaire runs once** — the router sends it a shared business idea
  (and any messages while questions are pending); once answered it never blocks
  again. Greetings and small talk go to `chat` instead.

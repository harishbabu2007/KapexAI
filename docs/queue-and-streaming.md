# Queue & Streaming

This document explains how the backend enqueues jobs and streams results back to
the frontend via Redis. For the agentic side (router, tools, message log, state)
see [agentic-pipeline.md](agentic-pipeline.md).

## Flow overview

```
Frontend                    Backend                      Worker
   │                          │                           │
   │  POST /create_chat_session                            │
   │─────────────────────────►│                           │
   │                          │  1. Create Session (DB)   │
   │                          │  2. LPUSH jobs:queue      │
   │                          │     + SET pending:{id}    │
   │  { session_id, job_id }  │──────────────────────────►│
   │◄─────────────────────────│  3. BRPOP jobs:queue      │
   │                          │                           │
   │  WS /ws/session/{id}     │                           │
   │════════════════════════►│                           │
   │                          │  4. Run langgraph graph   │
   │                          │  5. PUBLISH stream:{id}   │
   │◄═════════════════════════│◄──────────────────────────│
   │   { type: "chat" }       │   (via redis.publish)     │
   │◄═════════════════════════│◄──────────────────────────│
   │   { type: "suggestions" }│                           │
   │◄═════════════════════════│◄──────────────────────────│
   │   { type: "end" }        │                           │
```

## Job queue (`jobs:queue`)

The backend pushes jobs to a Redis list. The worker block-pops them.

### Backend — enqueue

`POST /create_chat_session`, `POST /push_chat_message` and
`POST /submit_questionnaire_answers` all enqueue the same job shape
(`backend/main.py`):

```python
job = {
    "job_id": str(uuid4()),
    "session_id": session.id,
    "user_input": user_data.content,
}
await redis.lpush("jobs:queue", json.dumps(job))
```

The questionnaire endpoint differs in one way: `user_input` carries a JSON
payload (`{"kind": "questionnaire_answers", "answers": [{key, answer}, ...]}`)
instead of free text, so the worker can map the answers onto the questions by
key without LLM parsing (see `docs/questionnaire-tool.md`).

Every enqueue also records the in-flight message so other tabs can surface it:
the backend calls `mark_pending(session_id, content, type)`, which sets
`pending:{session_id}` in Redis (5-min TTL) and flips `Session.status` to
`PENDING`. The worker clears the key and sets the status back to `ACTIVE` (or
`FAILED`) once the job finishes — see [In-flight tracking](#in-flight-tracking) below.

### Worker — dequeue

`worker/main.py` block-pops from the queue in its main loop and hands each job
to `process_job`:

```python
while not stop.is_set():
    result = await redis.brpop("jobs:queue", timeout=5)
    if result is None:
        continue
    _, raw = result
    job = json.loads(raw)
    await process_job(job, graph)
```

## Processing a job (`worker/agent.py`)

For each job the worker:

1. **Loads state** — reads `langgraph_state:{session_id}` from Redis. If absent,
   it rebuilds the message log from the session's chat history in the DB
   (ordered by `created_at`).
2. **Injects the user message** into the state and runs the graph.
3. **Saves state** back to Redis (24h TTL) and persists the produced messages to
   the `Message` table.
4. **Publishes** assistant results to the session's stream channel, followed by
   a `suggestions` frame and an `end` frame.

Every user message is persisted. The `Message.agent` column is `CHAT` for chat
messages and `TOOL` for tool messages; the tool-specific JSON shape lives in the
`content` column (`type` + extra fields). See
[agentic-pipeline.md](agentic-pipeline.md) for the full message formats.

### Error handling

If a job fails, the worker marks the session `FAILED` and publishes an error
frame to the session's stream channel:

```json
{"type": "error", "job_id": "…", "content": "Job … failed"}
```

The WebSocket forwards it to the frontend. Both backend endpoints return the
`job_id` in their responses so failures can be correlated.

## Streaming results (`stream:{session_id}`)

The worker publishes to the session's pub/sub channel. The backend WebSocket
(`/ws/session/{session_id}`) subscribes and forwards each frame to the frontend.

The endpoint is intentionally connection-safe:

- If no job is in flight (`pending:{session_id}` is absent), it sends `end` and
  closes immediately rather than holding an idle socket.
- While waiting for frames it polls the marker every 10s, so it also closes if
  the job finishes before publishing anything.
- Every send goes through a `_safe_send` helper that treats a client that
  disconnected mid-stream (e.g. a tab that was closed) as a normal close, so it
  never crashes the endpoint.

### Message protocol

Each message published to `stream:{session_id}` is a JSON string:

| `type` | Payload | Description |
|---|---|---|
| `chat` | `content` | A chat reply |
| `questionnaire` | `content`, `questions`, `facts` | Questionnaire questions (rendered as a slide UI, one at a time) |
| `questionnaire_complete` | `content`, `context` | Acknowledges the answers received |
| `swot` | `content`, `sections`, `summary` | SWOT analysis result |
| `research` | `content` | Web search result |
| `suggestions` | `tools: [{name, description, example, suggestion}]` | "wanna try this next?" suggestions |
| `error` | `job_id`, `content` | Job failed; the session is marked `FAILED` |
| `end` | — | Signals the stream is finished; the WebSocket closes |

The frontend should render each frame as it arrives and stop when it receives
`end`. User-generated messages are not streamed (the client already has them).

## Session status

`Session.status` (`services/database/schema.prisma`) tracks lifecycle:

| Status | Meaning |
|---|---|
| `ACTIVE` | Default; no job in flight (idle or completed) |
| `PENDING` | A job for this session is in the queue or being processed |
| `FAILED` | The worker encountered an error processing a job for this session |

## In-flight tracking (`pending:{session_id}`)

Pub/sub is fire-and-forget and a session's messages only exist in the DB once
the worker has processed them. To let a *fresh* tab (or the session list) see
that the assistant is still working, the backend keeps a lightweight marker:

- **On enqueue**, `mark_pending(session_id, content, type)` writes
  `pending:{session_id}` = `{"content": …, "type": …}` (5-min TTL) and sets the
  session status to `PENDING`. `content` is the user's message verbatim, except
  for questionnaire answers where it's the same numbered summary the frontend
  echoes (`"1) answer"` lines).
- **`GET /get_messages`** returns the marker as a top-level `pending` field
  alongside `data`, so a fresh tab can render the in-flight user bubble and
  connect to the live stream without waiting for the worker.
- **The worker clears it** in `process_job`: on success it deletes the key and
  marks the session `ACTIVE`; on failure it deletes the key and marks it
  `FAILED`.
- **The WebSocket** uses the marker to avoid dangling connections: if
  `pending:{session_id}` is absent at connect time it sends `end` and closes
  immediately, and while idle it polls the marker every 10s so it also closes
  once a job finishes without ever having streamed.

Frontend behavior: when `GET /get_messages` returns a non-null `pending`, the
tab appends the optimistic user bubble (flagged `pending: true`), shows the
typing indicator, and connects the WebSocket to receive the result live. Sending
is blocked while `streaming` is true, so a busy session never gets a second
message injected mid-turn from another tab.

## Key considerations

- **Pub/sub is fire-and-forget** — if no WebSocket is connected, published
  messages are lost; the `Message` table is the durable record. The
  `pending:{session_id}` marker (see above) lets tabs catch up live while a job
  is in flight.
- **One channel per session** — `stream:{session_id}` is unique per session.
  Multiple open tabs each connect their own WebSocket and receive the same
  frames; the frontend closes stale sockets before opening a new stream.
- **State persistence** — the state is stored at `langgraph_state:{session_id}`
  (24h TTL). If it's gone, the worker rebuilds the message log from the DB, so
  the conversation resumes instead of restarting.
- **Job IDs** — the backend generates a `job_id` per job and returns it in the
  API response; the worker includes it in error frames so failures can be
  correlated to a specific submission.

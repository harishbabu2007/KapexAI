# KapexAI — Agent Guide

## Workspace

uv workspace monorepo (Python >=3.12). Packages: `backend/`, `worker/`, `services/database/` (published as `db-service`), `services/redis-service/` (published as `redis-service`). `frontend/` is a Vite + React (TypeScript) app (not part of the uv workspace).

## Essential commands

| Command | What it does |
|---|---|
| `make install` | `uv sync` — install all workspace packages |
| `make generate` | `uv run prisma generate --schema=services/database/schema.prisma` — regenerate Prisma client after schema changes |
| `make migrate` | `uv run prisma migrate dev --schema=services/database/schema.prisma` — create & apply a new migration |
| `make dev-backend` | `uv run --package backend uvicorn backend.main:app --reload` — start FastAPI dev server |
| `make dev-worker` | `uv run --package worker python -m worker.main` — start worker |
| `cd frontend && npm run dev` | Start Vite dev server (default `http://localhost:3000`) |
| `cd frontend && npm run build` | Type-check (`tsc -b`) + production build to `frontend/dist/` |
| `cd frontend && npm run preview` | Serve the built `dist/` locally (has SPA fallback) |

## Dependency management

Use `uv add --package <pkg> <dep>` (never `pip install`). Example:
- `uv add --package backend "httpx>=0.27.0"`
- `uv add --package worker "redis>=5.0"`
- `uv add --dev "ruff"` (root dev dep)

`uv run` replaces virtualenv activation — it auto-finds the right environment.

Frontend deps go in `frontend/package.json` via `npm install <pkg>`.

## Testing

- Framework: `pytest` with `pytest-asyncio` for async tests
- Run backend tests: `.venv/bin/python -m pytest backend/tests/ -q` (on this machine `uv run pytest` resolves to a miniconda interpreter that's missing workspace packages — use `.venv/bin/python` instead)
- Run worker tests: `PYTHONPATH=. uv run --package worker pytest worker/tests/ -v` (worker tests hit real DB + Redis)
- Test files: `backend/tests/test_*.py`, `worker/tests/test_*.py`
- Frontend: no test framework; verify with `npm run build` (runs `tsc -b`)

## Services

### `db-service` — PostgreSQL (Prisma)

- ORM: Prisma, schema at `services/database/schema.prisma`
- Provider: PostgreSQL
- Connection string via `DATABASE_URL` env var (`.env`)
- Shared client: `from db_service import db, connect_db, disconnect_db`
- After editing `schema.prisma`, run `make generate` then `make migrate`
- `.prisma/` is gitignored (generated Prisma client)

Schema models: `User`, `Session`, `Message` (with `Role`, `Agent`, `Status` enums). The `Agent` enum tracks which agent produced a message (`QUESTIONNAIRE`, `RESEARCH`, `REPORT`, `GUARDRAIL`, `CHAT`, `TOOL`).

### `redis-service` — Redis Cloud (redis-py)

- Provider: Redis Cloud via `redis-py` (standard TCP Redis, supports pub/sub)
- Env var: `REDIS_URL` (e.g. `redis://user:pass@host:port`)
- Shared client: `from redis_service import redis, connect_redis, disconnect_redis`
- `connect_redis()` / `disconnect_redis()` are **async** (`await` them)
- Client is created with `socket_timeout=None` — required so blocking commands like `brpop` (used by the worker) return `None` instead of racing with the 5s socket default and raising `TimeoutError`
- Backend connects Redis in its `lifespan` alongside the DB
- Supports pub/sub — used by the WebSocket endpoint for real-time streaming

Full docs at `docs/agentic-pipeline.md` (router/tools/message log), `docs/services.md`, and `docs/queue-and-streaming.md`.

## Frontend

Vite + React (TypeScript), deps managed via `frontend/package.json` (`npm install`). Key libs: `react-router-dom` (routing), `@react-oauth/google` (Google popup sign-in), `react-markdown` + `remark-gfm` (assistant messages).

- Routes (`src/App.tsx`): `/` (landing), `/chat` (protected), `*` → `/`
- Auth: `src/lib/auth.tsx` AuthProvider stores the JWT + user in `localStorage` (persists across tabs); restores/validates on load via `GET /auth/me` and only drops the session on a 401
- API client: `src/lib/api.ts` (typed `fetch` wrapper, `ApiError` with `.status`, `wsUrl()` for the stream socket)
- Chat state: `src/hooks/useChatSession.ts` (sessions list, active session, streaming via WebSocket, rename/delete handlers)
- Styling: `src/styles/global.css` (landing) + `src/styles/chat.css` (workspace)
- Env: `VITE_API_BASE_URL` (default `http://localhost:8000`), `VITE_GOOGLE_CLIENT_ID` (in `frontend/.env.local`)
- Message rendering: `src/components/messages/` maps each tool's `type` to a card component

## OpenCode

Custom commands in `.opencode/commands/`:
- `start-work` — syncs main with upstream and creates a feature branch
- `pr-prep` — analyzes changes, generates tests, drafts PR description

## State of project

Functional end-to-end pipeline with Google OAuth authentication and a working frontend (landing page + chat workspace). Backend pushes jobs to a Redis queue; the worker consumes them and runs a LangGraph **chat + tools** graph; results stream back to the frontend over WebSocket + Redis pub/sub. Auth uses a popup ID token flow (`POST /auth/google`); endpoints are protected by JWT tokens.

## Architecture & data flow

1. **Backend** (`backend/main.py`) exposes REST endpoints that create sessions/messages and push jobs to Redis queue `jobs:queue`.
2. **Worker** (`worker/main.py`) polls `jobs:queue` with `brpop` (5s timeout), then runs the job through a compiled LangGraph graph.
3. **Graph** (`worker/agent.py`) is a `StateGraph` with a single `router` node that decides how to handle each user message:
   - `chat` — `chat_agent` (business-consultant persona) replies conversationally; the reply is saved as a `Message` and streamed.
   - `tool` — dispatch to a registered tool (see `worker/tools/registry.py`). Each tool returns message entries with its own JSON shape (`type` + extra fields); `tool_node` persists and streams them.
   - The **router** sends greetings/small talk to the chat agent (which stays strictly business-focused) and routes a shared business idea to the **questionnaire tool** to build context; while questions are pending, answers are routed back to it automatically.
   - Every chat/tool turn ends by streaming a `suggestions` event listing available tools (name + example + suggestion phrase) and an `end` event.
4. **Streaming** — each node publishes to pub/sub channel `stream:{session_id}`; the backend WebSocket endpoint `ws/session/{session_id}` forwards it to the client.
5. **State** — a **message log** (`messages`) is cached in Redis (`langgraph_state:{session_id}`, 24h TTL) and rebuilt from DB message history (ordered by `created_at`) via `worker/helpers/persistence.py`. Each log entry is `{role, agent, type, content, ...tool-specific fields}`.
6. **Frontend** — the React app signs in via a Google popup (`POST /auth/google`), then `src/hooks/useChatSession.ts` drives the workspace: sessions come from `GET /get_sessions`, messages from `GET /get_messages`, and streaming from the WebSocket. Sessions can be **renamed** (`POST /rename_session`, updates `business_idea`) or **deleted** (`POST /delete_session`, removes the session + all messages + the Redis `langgraph_state` key) from the sidebar's per-session ⋯ menu.

## Key modules

| File | Description |
|---|---|
| `backend/main.py` | FastAPI app: `/health`, `/waitlist`, `/create_chat_session`, `/push_chat_message`, `/get_sessions`, `/get_messages`, `/rename_session`, `/delete_session`, `ws/session/{session_id}` |
| `backend/utils/jwt_utils.py` | JWT token creation and verification using python-jose (HS256, 7-day expiry) |
| `backend/middleware/auth.py` | FastAPI `get_current_user` dependency — extracts Bearer token, decodes JWT, fetches user from DB |
| `backend/routers/auth.py` | Google OAuth endpoints: `/auth/google` (popup ID token), `/auth/google/callback`, `/auth/me` |
| `backend/utils/db_utils.py` | Backend-side Prisma helpers (`get_user`, `get_session`, `get_all_sessions`) |
| `backend/models/models.py` | Pydantic request bodies (waitlist, chat session/message, rename/delete session) |
| `worker/main.py` | Async worker loop; polls Redis queue and dispatches jobs |
| `worker/agent.py` | LangGraph graph definition, state load/save, `process_job` |
| `worker/agents/` | `router_agent.py` (intent classifier), `chat_agent.py` (consultant chat) |
| `worker/helpers/persistence.py` | Prisma helpers + DB message-log rebuild for the worker |
| `worker/helpers/messages.py` | Message-log helpers (transcript, questionnaire state, business context) |
| `worker/helpers/events.py` | Pub/sub stream publishing helpers |
| `worker/tools/` | Plug-and-play tools: `base.py`, `registry.py`, `questionnaire_tool.py`, `swot_tool.py`, `web_search_tool.py` |
| `worker/prompts/` | LLM prompt templates per agent/tool |
| `worker/tools/tavily_search.py` | Tavily search tool used by `web_search_tool` |
| `worker/tests/` | `test_chat_tools.py` — queue/pub-sub, chat, tool, questionnaire, state-rebuild tests |
| `backend/tests/` | `test_main.py`, `test_jwt_utils.py`, `test_auth.py`, `test_middleware.py` |
| `frontend/src/lib/api.ts` | Typed HTTP client (`request`, `ApiError`, `wsUrl`, auth/session/waitlist calls) |
| `frontend/src/lib/auth.tsx` | AuthProvider — Google sign-in, `localStorage` session persistence, 401-only clearing |
| `frontend/src/lib/types.ts` | Shared TS types (`SessionInfo`, `ChatMessage`, `StreamFrame`, `ToolInfo`) |
| `frontend/src/hooks/useChatSession.ts` | Chat workspace state: sessions, active session, WS streaming, rename/delete |
| `frontend/src/App.tsx` | Routes: `/` landing, `/chat` (protected), `*` → `/` |
| `frontend/src/pages/LandingPage.tsx` | Landing hero/CTA + sign-in block |
| `frontend/src/pages/ChatPage.tsx` | Chat workspace layout (sidebar + messages + composer) |
| `frontend/src/components/chat/Sidebar.tsx` | Session list with per-session ⋯ menu (rename inline, delete confirm) |
| `frontend/src/components/messages/` | Per-tool message card components, keyed by message `type` |

Before running either service, ensure the Prisma client is generated: `make generate`.

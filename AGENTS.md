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
- `worker/tests/conftest.py` owns the **single** event loop + the session-scoped DB/Redis `services` fixture. All worker test modules must use `from conftest import run as _run` — the `redis_service` client binds connections to whichever loop created them, so a second loop in the same pytest process (e.g. a second test file) collides with the first

## Services

### `db-service` — PostgreSQL (Prisma)

- ORM: Prisma, schema at `services/database/schema.prisma`
- Provider: PostgreSQL
- Connection string via `DATABASE_URL` env var (`.env`)
- Shared client: `from db_service import db, connect_db, disconnect_db`
- After editing `schema.prisma`, run `make generate` then `make migrate`
- `.prisma/` is gitignored (generated Prisma client)

Schema models: `User`, `Session`, `Message` (with `Role`, `Agent`, `Status` enums), `BusinessProfile` (`userId` unique, `content` Json, one-to-one with `User`). The `Agent` enum tracks which agent produced a message (`QUESTIONNAIRE`, `RESEARCH`, `REPORT`, `GUARDRAIL`, `CHAT`, `TOOL`).

### `redis-service` — Redis Cloud (redis-py)

- Provider: Redis Cloud via `redis-py` (standard TCP Redis, supports pub/sub)
- Env var: `REDIS_URL` (e.g. `redis://user:pass@host:port`)
- Shared client: `from redis_service import redis, connect_redis, disconnect_redis`
- `connect_redis()` / `disconnect_redis()` are **async** (`await` them)
- Client is created with `socket_timeout=None` — required so blocking commands like `brpop` (used by the worker) return `None` instead of racing with the 5s socket default and raising `TimeoutError`
- Backend connects Redis in its `lifespan` alongside the DB
- Supports pub/sub — used by the WebSocket endpoint for real-time streaming

Full docs at `docs/agentic-pipeline.md` (router/tools/message log), `docs/services.md`, `docs/queue-and-streaming.md` (jobs/streaming), and `docs/tab-switching.md` (single-tab lock + state resume).

## Frontend

Vite + React (TypeScript), deps managed via `frontend/package.json` (`npm install`). Key libs: `react-router-dom` (routing), `@react-oauth/google` (Google popup sign-in), `react-markdown` + `remark-gfm` (assistant messages).

- Routes (`src/App.tsx`): `/` (landing), `/chat` (protected), `/business-profile` (protected, first-fill profile), `*` → `/`
- Auth: `src/lib/auth.tsx` AuthProvider stores the JWT + user in `localStorage` (persists across tabs); restores/validates on load via `GET /auth/me` and only drops the session on a 401. Tracks `profileEmpty` so authenticated users are redirected past the landing page: empty profile → `/business-profile`, filled → `/chat` (`HomeRedirect` in `App.tsx`)
- API client: `src/lib/api.ts` (typed `fetch` wrapper, `ApiError` with `.status`, `wsUrl()` for the stream socket, `getBusinessProfile`/`updateBusinessProfile` for the profile page)
- Chat state: `src/hooks/useChatSession.ts` (sessions list, active session, streaming via WebSocket, rename/delete handlers)
- Styling: `src/styles/global.css` (landing) + `src/styles/chat.css` (workspace)
- Env: `VITE_API_BASE_URL` (default `http://localhost:8000`), `VITE_GOOGLE_CLIENT_ID` (in `frontend/.env.local`)
- Message rendering: `src/components/messages/` maps each tool's `type` to a card component — including `legal_research`/`case_search`/`issue_register` (`LegalResearchCard`, `CaseSearchCard`, `IssueRegisterCard`); unknown types fall back to plain markdown

## OpenCode

Custom commands in `.opencode/commands/`:
- `start-work` — syncs main with upstream and creates a feature branch
- `pr-prep` — analyzes changes, generates tests, drafts PR description

## State of project

Functional end-to-end pipeline with Google OAuth authentication and a working frontend (landing page + chat workspace). Backend pushes jobs to a Redis queue; the worker consumes them and runs a LangGraph **chat + tools** graph; results stream back to the frontend over WebSocket + Redis pub/sub. Auth uses a popup ID token flow (`POST /auth/google`); endpoints are protected by JWT tokens.

## Architecture & data flow

1. **Backend** (`backend/main.py`) exposes REST endpoints that create sessions/messages and push jobs to Redis queue `jobs:queue`. Every submission also records the in-flight message in Redis (`pending:{session_id}`, 5-min TTL) and flags the session `PENDING`, so any tab can surface it while the worker is still replying.
2. **Worker** (`worker/main.py`) polls `jobs:queue` with `brpop` (5s timeout), then runs the job through a compiled LangGraph graph. When a job finishes it clears the `pending:{session_id}` key and marks the session `ACTIVE` (or `FAILED` on error).
3. **Graph** (`worker/agent.py`) is a `StateGraph` with a single `router` node that decides how to handle each user message:
   - `chat` — `chat_agent` (business-consultant persona) replies conversationally; the reply is saved as a `Message` and streamed.
   - `tool` — dispatch to a registered tool (see `worker/tools/registry.py`). Each tool returns message entries with its own JSON shape (`type` + extra fields); `tool_node` persists and streams them.
   - The **router** sends greetings/small talk to the chat agent (which stays strictly business-focused) and routes a shared business idea to the **questionnaire tool** to build context; "set up / start / build a business" is also routed to the questionnaire so new users get the guided setup instead of an open-ended "what do you need?". While questions are pending, answers are routed back to the questionnaire automatically. The chat agent never repeats an already-asked question and, when there's no business context yet, proactively offers the guided setup.
   - Tools that need business context (`swot`, `web_search`, marked `requires_context = True` on the `Tool`) are **gated**: they only run after the questionnaire completes (`questionnaire_complete`); before that the router redirects the request to the questionnaire tool so context exists first.
   - The questionnaire answers are collected by the frontend **slide UI** (one question at a time) and submitted as structured `{key, answer}` pairs via `POST /submit_questionnaire_answers`; the worker maps them into context by key without LLM parsing, but validates each non-empty answer per-question (gibberish is rejected and re-asked, never absorbed). Free-form typed answers fall back to LLM validation/parsing.
   - **Questionnaire idea guard** — `QuestionnaireTool._is_real_idea()` decides whether the first message starts the questionnaire. It is **deterministic first**: rejects questionnaire commands ("start the business questionnaire"), greetings, and gibberish, and accepts any ≥2-word/≥8-char message as a valid idea ("south indian restaurant in pune") without calling the LLM. The LLM only adjudicates short single words, and fails open (any parse/API hiccup accepts rather than blocking a plausible idea).
   - **Legal & regulatory tools** (`indian_legal_search`, `indian_case_search`, `legal_issue_register`) are registered with `requires_context = False` so they run on any session without needing the questionnaire first. `indian_legal_search` discovers official sources via Tavily over a centralized **domain allowlist** (`worker/helpers/indian_sources.py`, 10 `.gov.in`/`.nic.in` domains) and grounds results in Python (invented URLs dropped, titles verbatim, official results first); `indian_case_search` queries the Indian Kanoon API (needs `INDIANKANOON_API_TOKEN` via `worker/helpers/cached_http.py`, TTL-cached) and is always labelled a third-party database; `legal_issue_register` scores compliance issues deterministically (`likelihood × severity × urgency` → critical/high/medium/low) and clamps LLM factors. Message types: `legal_research`, `case_search`, `issue_register`.
   - Every chat/tool turn ends by streaming a `suggestions` event listing available tools (name + example + suggestion phrase) and an `end` event.
4. **Streaming** — each node publishes to pub/sub channel `stream:{session_id}`; the backend WebSocket endpoint `ws/session/{session_id}` forwards it to the client. The socket closes right away if no job is in flight for the session and treats a client disconnecting mid-stream as a normal close.
5. **State** — a **message log** (`messages`) is cached in Redis (`langgraph_state:{session_id}`, 24h TTL) and rebuilt from DB message history (ordered by `created_at`) via `worker/helpers/persistence.py`. Each log entry is `{role, agent, type, content, ...tool-specific fields}`.
6. **Frontend** — the React app signs in via a Google popup (`POST /auth/google`), then `src/hooks/useChatSession.ts` drives the workspace: sessions come from `GET /get_sessions`, messages from `GET /get_messages`, and streaming from the WebSocket. Sessions can be **renamed** (`POST /rename_session`, updates `business_idea`) or **deleted** (`POST /delete_session`, removes the session + all messages + the Redis `langgraph_state` and `pending` keys) from the sidebar's per-session ⋯ menu. A fresh tab that loads a session with an in-flight job (the `pending` field from `GET /get_messages`) shows the pending bubble + typing indicator and connects to the live stream; sending another message is blocked until the current reply finishes. Incoming messages never auto-scroll the chat — the view only anchors to the bottom when the user sends a message or switches sessions.
7. **Business profile** — each `User` has one `BusinessProfile` row (created lazily by `ensure_business_profile` on signup). The frontend `/business-profile` page collects seven fields (`your_name`, `industry`, `about_you`, `business_history`, `location`, `monthly_income`, `monthly_expenditure`) and saves them via `POST /update_business_profile`; `GET /get_business_profile` returns the raw `content` dict. On every worker job, `load_state` refetches the profile and injects a `business_profile` message-log entry via `inject_business_profile` (replaces any stale cached entry, leaving the log empty if the profile is blank), so tools/the chat agent always read fresh values. After signup and on `/auth/me`, the backend returns `profile_empty`; `HomeRedirect` sends users with an empty profile to `/business-profile` instead of `/chat`.

## Key modules

| File | Description |
|---|---|
| `backend/main.py` | FastAPI app: `/health`, `/waitlist`, `/create_chat_session`, `/push_chat_message`, `/submit_questionnaire_answers`, `/get_sessions`, `/get_messages`, `/rename_session`, `/delete_session`, `/get_business_profile`, `/update_business_profile`, `ws/session/{session_id}`. Tracks in-flight jobs via the `pending:{session_id}` key + `PENDING` status |
| `backend/utils/jwt_utils.py` | JWT token creation and verification using python-jose (HS256, 7-day expiry) |
| `backend/middleware/auth.py` | FastAPI `get_current_user` dependency — extracts Bearer token, decodes JWT, fetches user from DB |
| `backend/routers/auth.py` | Google OAuth endpoints: `/auth/google` (popup ID token), `/auth/google/callback`, `/auth/me`. Ensures a `BusinessProfile` row on signup and returns `profile_empty` |
| `backend/utils/db_utils.py` | Backend-side Prisma helpers (`get_user`, `get_session`, `get_all_sessions`, `ensure_business_profile`, `business_profile_is_empty`) |
| `backend/models/models.py` | Pydantic request bodies (waitlist, chat session/message, rename/delete session, business profile) |
| `worker/main.py` | Async worker loop; polls Redis queue and dispatches jobs |
| `worker/agent.py` | LangGraph graph definition, state load/save, `process_job`; `load_state` injects the user's `business_profile` into the message log |
| `worker/agents/` | `router_agent.py` (intent classifier), `chat_agent.py` (consultant chat) |
| `worker/helpers/persistence.py` | Prisma helpers (`get_business_profile`) + DB message-log rebuild for the worker |
| `worker/helpers/messages.py` | Message-log helpers (transcript, questionnaire state, business profile injection/context) |
| `worker/helpers/events.py` | Pub/sub stream publishing helpers |
| `worker/helpers/cached_http.py` | TTL-cached HTTP for tools (`cached_json`): Redis `tool_cache:` keys, retry/backoff on transient failures, `require_env`, typed `ToolError`s. Cache keys never include headers, so tokens can't leak into keys |
| `worker/helpers/indian_sources.py` | Centralized Indian official-source allowlist (10 `.gov.in`/`.nic.in` domains) + `classify_source` → `(official_source, source_type, authority)` |
| `worker/tools/` | Plug-and-play tools: `base.py`, `registry.py`, `questionnaire_tool.py`, `swot_tool.py`, `web_search_tool.py`, `legal_tools.py` (`indian_legal_search`, `indian_case_search`, `legal_issue_register`) |
| `worker/prompts/` | LLM prompt templates per agent/tool (`router.py`, `chat.py`, `questionnaire.py`, `legal.py`) |
| `worker/tools/tavily_search.py` | Tavily search tool used by `web_search_tool` |
| `worker/tests/` | `test_chat_tools.py` (queue/pub-sub, chat, tool, questionnaire, state-rebuild tests), `test_legal_tools.py` (30 legal-tool tests incl. real E2E flows), `test_questionnaire_idea.py` (deterministic `_is_real_idea` guard tests), `test_cached_http.py` (TTL-cached HTTP unit tests) |
| `backend/tests/` | `test_main.py`, `test_jwt_utils.py`, `test_auth.py`, `test_middleware.py`, `test_db_utils.py` |
| `frontend/src/lib/api.ts` | Typed HTTP client (`request`, `ApiError`, `wsUrl`, auth/session/waitlist/profile calls) |
| `frontend/src/lib/auth.tsx` | AuthProvider — Google sign-in, `localStorage` session persistence, 401-only clearing, `profileEmpty` state + `markProfileFilled` |
| `frontend/src/lib/types.ts` | Shared TS types (`SessionInfo`, `ChatMessage`, `StreamFrame`, `ToolInfo`, `BusinessProfile`) |
| `frontend/src/hooks/useChatSession.ts` | Chat workspace state: sessions, active session, WS streaming, rename/delete |
| `frontend/src/App.tsx` | Routes: `/` landing, `/chat` (protected), `/business-profile` (protected), `*` → `/`; `HomeRedirect` sends profile-empty users to `/business-profile` |
| `frontend/src/pages/LandingPage.tsx` | Landing hero/CTA + sign-in block |
| `frontend/src/pages/ChatPage.tsx` | Chat workspace layout (sidebar + messages + composer); scrolls to bottom only on send/session switch, never on incoming content |
| `frontend/src/pages/BusinessProfilePage.tsx` | First-fill profile page — collects the seven profile fields, Save → `/chat`, "Skip for now" |
| `frontend/src/components/chat/Sidebar.tsx` | Session list with per-session ⋯ menu (rename inline, delete confirm) + "Business profile" button |
| `frontend/src/components/messages/` | Per-tool message card components, keyed by message `type` (incl. `LegalResearchCard`, `CaseSearchCard`, `IssueRegisterCard`) |

Before running either service, ensure the Prisma client is generated: `make generate`.

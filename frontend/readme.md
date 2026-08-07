# KapexAI frontend

React + TypeScript (Vite) app for KapexAI: a landing page with Google sign-in
and a ChatGPT-style chat workspace backed by the FastAPI + worker pipeline.

## Run locally

1. Install Node.js 20 LTS or newer.
2. Copy `.env.example` to `.env.local` and set `VITE_GOOGLE_CLIENT_ID`.
3. Run `npm install` and then `npm run dev`.
4. Open `http://localhost:3000`.

The FastAPI service must run at `http://localhost:8000` (or set
`VITE_API_BASE_URL`). Its root `.env` needs `GOOGLE_CLIENT_ID` (same value as
`VITE_GOOGLE_CLIENT_ID`), `JWT_SECRET`, `DATABASE_URL` and `REDIS_URL`; see the
repository-root `.env.example`.

## Routes

| Route | Access | What it is |
|---|---|---|
| `/` | public | Landing page with Google sign-in, features and waitlist |
| `/chat` | authenticated | Chat workspace (redirects unauthenticated users to `/`) |

## Structure

```
src/
  App.tsx                 routes
  main.tsx                GoogleOAuthProvider + BrowserRouter + AuthProvider
  lib/
    api.ts                typed HTTP client (auth, sessions, messages, waitlist) + wsUrl helper
    auth.tsx              AuthProvider / useAuth (token + user in sessionStorage)
    types.ts              shared types (SessionInfo, ChatMessage, StreamFrame, …)
    markdown.tsx          markdown renderer for assistant replies
  hooks/
    useChatSession.ts     sessions, message history, sending, WebSocket streaming
  components/
    auth/                 GoogleSignInButton, ProtectedRoute
    landing/              nav, features, waitlist section
    chat/                 sidebar, message list, composer, suggestions, …
    messages/             per-tool message renderers (see below)
  pages/
    LandingPage.tsx
    ChatPage.tsx
  styles/
    global.css            theme + landing page
    chat.css              chat workspace
```

## Streaming

`useChatSession` pushes your message (creating a session on first send), opens
`ws://<api>/ws/session/{id}` and appends assistant frames as they arrive. The
`end` frame stops the typing indicator; `suggestions` renders the "try next"
chips; `error` shows a banner. On reload, history is re-fetched from
`GET /get_messages`.

## Adding a new tool's UI

Every assistant message has a `type` field (the worker's tools emit their own
shapes). The frontend maps `type` → component in
`src/components/messages/index.tsx`:

1. Create a component that receives `{ message: ChatMessage }` and renders the
   extra fields your tool emits (e.g. `MyToolCard.tsx`).
2. Register it: `my_tool_type: MyToolCard`.

Unknown types fall back to a plain markdown bubble, so a tool without a
frontend component still degrades gracefully.

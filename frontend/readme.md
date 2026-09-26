# KapexAI frontend

React + TypeScript (Vite) app for KapexAI: a landing page with Google sign-in
and a ChatGPT-style chat workspace backed by the FastAPI + worker pipeline.

## Run locally

1. Use Node.js 22.23.2 (the version verified for this project).
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
| `/business-profile` | authenticated | Business profile fields; shown on first login until filled in |

## Structure

```
src/
  App.tsx                 routes
  main.tsx                GoogleOAuthProvider + BrowserRouter + AuthProvider
  lib/
    api.ts                typed HTTP client (auth, sessions, messages, feedback, waitlist) + wsUrl helper
    auth.tsx              AuthProvider / useAuth (token + user in localStorage)
    types.ts              shared types (SessionInfo, ChatMessage, StreamFrame, FeedbackCategory, …)
    feedbackLifecycle.ts  one-at-a-time submission rules (pending, sequence guard, uncertain-on-abort)
    markdown.tsx          markdown renderer for assistant replies
  hooks/
    useChatSession.ts     sessions, message history, sending, WebSocket streaming
  components/
    auth/                 GoogleSignInButton, ProtectedRoute
    landing/              nav, features, waitlist section
    chat/                 sidebar, message list, composer, suggestions, …
    feedback/             FeedbackDialog
    messages/             per-tool message renderers (see below)
  pages/
    LandingPage.tsx
    ChatPage.tsx
    BusinessProfilePage.tsx
  styles/
    global.css            theme + landing page
    chat.css              chat workspace + feedback dialog

tests/                    Node built-in runner, no test framework installed
  feedback-lifecycle.test.ts        lifecycle rules, with an injected fake `send`
  feedback-dialog-invariants.test.ts  source assertions on ChatPage/FeedbackDialog
```

## Streaming

`useChatSession` pushes your message (creating a session on first send), opens
`ws://<api>/ws/session/{id}` and appends assistant frames as they arrive. The
`end` frame stops the typing indicator; `suggestions` renders the "try next"
chips; `error` shows a banner. On reload, history is re-fetched from
`GET /get_messages`.

## Feedback

The **Feedback** button at the bottom of the sidebar (above the divider, so it
stays put in both the empty-chat and active-chat states) opens
`components/feedback/FeedbackDialog.tsx`, which posts to `POST /feedback`.

- The button is only rendered when `/auth/me` reports `feedback_enabled: true`.
  A response that omits the field is treated as **false**, so pointing the app at
  an older backend hides the button rather than breaking it.
- **No credentials belong in the frontend.** There is nothing to add to
  `.env.local`; all Google access happens in the backend.
- On a failure the form keeps everything you typed. If the backend reports
  `delivery: "uncertain"` the dialog says explicitly that the row may already be
  saved and that resending may duplicate it — respect that and don't auto-retry.
- **Closing the dialog only hides it.** `ChatPage` owns the draft, the pending
  flag and the outcome, and `lib/feedbackLifecycle.ts` owns the request rules
  (one at a time, sequence-guarded, no `close`/`cancel` method a dismissal could
  reach). Closing never aborts the request and never clears the pending state, so
  a reopened dialog still shows pending with the form disabled, and still shows
  the outcome once it arrives. Aborting only happens on unmount, and its result
  is reported as `uncertain` because an aborted fetch proves nothing about
  whether a row was written.
- `ChatPage` also renders `ChatHeader` inside `.chat-empty-header` for the
  empty-chat state. It is hidden on desktop and shown under 760px, purely to give
  mobile a way to open the sidebar (the empty state has no header of its own).

## Tests

There is no test framework installed. `npm test` runs Node's built-in runner over
`tests/` with `--experimental-strip-types`, and `npm run build` runs `tsc -b`.
The lifecycle tests inject a fake `send`, so they never reach `POST /feedback`.

The project declares `engines.node` as `>=22.6.0`. Use Node.js 22.23.2, which was verified with `npm test` and `npm run build`. The tests use `--experimental-strip-types`; dependencies may impose additional Node version requirements.

## Adding a new tool's UI

Every assistant message has a `type` field (the worker's tools emit their own
shapes). The frontend maps `type` → component in
`src/components/messages/index.tsx`:

1. Create a component that receives `{ message: ChatMessage }` and renders the
   extra fields your tool emits (e.g. `MyToolCard.tsx`).
2. Register it: `my_tool_type: MyToolCard`.

Unknown types fall back to a plain markdown bubble, so a tool without a
frontend component still degrades gracefully.

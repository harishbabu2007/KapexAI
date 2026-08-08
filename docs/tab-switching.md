# Tab switching & state resume

How KapexAI behaves when you switch tabs, open a second tab/window, or reload
the chat page — and how a fresh tab picks up the conversation (including one
that is still being generated in another tab).

## The short version

- **Auth is shared, not per-tab.** The JWT + user live in `localStorage`
  (`kapex_token`, `kapex_user`), so every new tab/window is instantly logged in.
- **Only one tab is ever "active" for chat.** A heartbeat + BroadcastChannel
  lock (`hooks/useSingleTab.ts`) lets a second tab detect the first and show a
  full-screen "Already open in another tab" blocker. The active tab can be
  taken over, and blocked tabs auto-reclaim when the active one closes.
- **Chat state is not stored in the tab — it's re-fetched.** Each tab starts
  with an empty view and pulls the session list, then the selected session's
  messages, from the backend on demand.
- **A job started in another tab is not lost.** The backend keeps an
  `pending:{session_id}` marker (5-min TTL) while a job is in flight. Any tab
  that loads that session shows the in-flight user bubble optimistically and
  connects to the live WebSocket, so the reply arrives in real time.

## The moving parts

| Piece | File | Role |
|---|---|---|
| Auth restore | `src/lib/auth.tsx` | Reads `kapex_token`/`kapex_user` from `localStorage`, validates against `GET /auth/me`, only drops the session on a 401 |
| Single-tab lock | `src/hooks/useSingleTab.ts` | localStorage heartbeat (`kapexai-tab-lock`) + `BroadcastChannel` (`kapexai-tab-lock`); returns `{ blocked, claimTab }` |
| Blocked UI | `src/components/chat/TabBlockedOverlay.tsx` | Full-screen overlay with a "Use this tab instead" button |
| Chat state | `src/hooks/useChatSession.ts` | Sessions, messages, streaming, send/rename/delete — all in-memory, fetched from the backend |
| API client | `src/lib/api.ts` | `getSessions`, `getMessages` (returns a `pending` field), `wsUrl` |
| Types | `src/lib/types.ts` | `ChatMessage.pending`, `PendingMessage`, `StreamFrame` |
| In-flight marker | backend `pending:{session_id}` + `Session.status` | Lets fresh tabs catch up on a job in flight (see `docs/queue-and-streaming.md`) |

## The single-tab lock, in detail

`useSingleTab` enforces *one active chat tab per browser*. Each tab gets a
`crypto.randomUUID()` id and keeps a `{ tabId, ts }` record in
`localStorage["kapexai-tab-lock"]`.

Constants:

- `HEARTBEAT_MS = 1500` — the active tab rewrites its lock every 1.5s.
- `STALE_MS = 6000` — a lock is considered "held" only if `now - ts < 6000`.
  If the active tab dies, its record goes stale after ~6s and another tab can
  take over.

### Normal flow (single tab)

1. On mount the tab writes its heartbeat immediately, then waits 300ms to
   settle. If no other tab holds a fresh lock, it broadcasts a `claim` on the
   `BroadcastChannel` and becomes the active tab.
2. Every 1.5s it rewrites the heartbeat (only while it is the active tab).
3. Every message on the channel from *another* tab with `type === 'claim'`
   flips it to `blocked`.

### Two tabs opened at the same time

Both write a heartbeat on mount, so the *last writer* ends up in storage. After
the 300ms settle timer, each tab checks `heldByOtherTab()`:

- The tab that did **not** write last sees the other's fresh record → becomes
  `blocked`.
- The tab that **did** write last sees its own record → broadcasts `claim` and
  stays active.

Because the lock is a single localStorage value and reads are synchronous, the
two timers settle on exactly one active tab (the last-mounted one wins).

### The active tab is closed

The heartbeat stops. After up to `STALE_MS` (6s), the blocked tab's heartbeat
interval sees `!heldByOtherTab()` and auto-reclaims via `claimTab()`. It becomes
interactive again without any user action. (It does not auto-resume a specific
session — it just unblocks with the state it already loaded, see below.)

### Manual takeover ("Use this tab instead")

The blocked tab's overlay calls `handleClaim` in `ChatPage.tsx`:

```ts
claimTab()                       // become active + broadcast claim to others
chat.refreshSessions()           // resync the sidebar from GET /get_sessions
chat.selectSession(chat.activeSessionId) // resync the open conversation (if any)
```

`claimTab` sets the tab active, writes its heartbeat, and broadcasts `claim`.
Every other tab receives it, sets `blocked`, and renders the overlay — so only
the new tab drives the chat. Note that a tab which was blocked from the start
never opened a conversation (`activeSessionId` is `null`), so it reclaims into
the new-chat hero and relies on the sidebar to open anything.

### Visibility change

When a tab becomes visible again (`visibilitychange`), it re-checks the lock:
another tab holds it → blocked; otherwise it reclaims. This covers
minimize/restore and OS-level focus switching where the heartbeat may have gone
stale.

## How state is resumed

A tab keeps **no chat state on disk** — `activeSessionId`, `messages`, etc. all
live in React state. On a fresh load every tab rebuilds its view from the
backend:

### 1. Auth (instant, shared)

`AuthProvider` reads `kapex_token` + `kapex_user` from `localStorage` and calls
`GET /auth/me` to validate. Only a **401** clears the stored session; a network
hiccup keeps the stored session so the user isn't logged out by a transient
failure. This is what makes a new window "just work" — it is logged in before
the first paint.

### 2. Session list

`useChatSession` runs `refreshSessions()` on mount → `GET /get_sessions`,
newest first. Every tab sees the same list because it's read from the DB.

### 3. Opening a session

`selectSession(id)`:

1. Closes any open WebSocket (so overlapping streams can't double-append).
2. Sets `activeSessionId`.
3. `loadMessages(id)` → `GET /get_messages?session_id=…`.

`getMessages` returns `{ data, pending }`. `data` is the persisted message log
from Postgres, ordered by `created_at`. `pending` is the in-flight marker if the
worker is still replying to that session.

### 4. In-flight resume (the important part)

If `pending` is non-null, the fresh tab:

- appends `{ role: 'USER', type: pending.type, content: pending.content,
  pending: true }` to the message list — the user's message that another tab
  sent — so the conversation reads as "user bubble, then typing indicator"
  instead of a hole;
- calls `streamSession(id)`, which opens `ws/session/{id}` and appends
  `ASSISTANT` frames as they arrive (`chat`, `questionnaire`, `swot`,
  `research`, …), shows `suggestions`, and stops on `end`.

So a brand-new window that opens a session mid-generation catches the reply
**live**, not on the next reload. Sending is blocked while `streaming` is true,
so a busy session never gets a second message injected mid-turn.

If `pending` is null, the tab just renders `data` and waits.

### What is NOT resumed

- **The currently-open session.** Nothing persists `activeSessionId`, so
  reloading `/chat` or opening a new tab lands on the new-chat hero, not the
  last-open conversation. Picking it from the sidebar re-fetches it.
- **In-memory state** (scrolled messages, streaming flag, optimistic bubbles)
  is per-tab and discarded on reload. The durable copy is Postgres (messages) +
  the worker's Redis state cache (`langgraph_state:{session_id}`, 24h TTL),
  which the worker rebuilds from DB history when it needs it.

## End-to-end: two tabs, job in flight

```
Tab A (active)                  Backend                      Tab B (new/blocked)
    │  sendMessage("...")          │                             │
    │──── LPUSH jobs:queue ──────►│                             │
    │  + mark_pending({id})       │  pending:{id} set,          │
    │  + Session.status = PENDING │  Session.status = PENDING   │
    │◄──── { session_id, job_id } │                             │
    │  open WS ws/session/{id}    │                             │
    │════════════════════════════►│                             │
    │                             │  worker runs graph,         │
    │                             │  PUBLISH stream:{id} frames │
    │◄════════ frames (chat, ...) │◄────────────────────────────│
    │                             │                             │
    │  user opens tab B, clicks   │                             │
    │  "Use this tab instead"     │                             │
    │◄ claim over BroadcastChannel│                             │
    │  becomes blocked (overlay)  │                             │
    │                             │  B: GET /get_messages       │
    │                             │◄──── { data, pending } ────│
    │                             │  (pending non-null)         │
    │                             │  B: optimistic user bubble  │
    │                             │  B: open WS ── join stream  │
    │◄════════ remaining frames ══│◄────────────frames──────────│
    │                             │  end → B clears pending,    │
    │                             │  marks session ACTIVE       │
```

Both tabs may receive frames while A is still connected, but only B is visible
(active); A is behind the overlay. The `pending` marker is what makes B's live
catch-up possible at all, since pub/sub is fire-and-forget and `data` only gains
the new messages after the worker persists them.

## Edge cases & notes

- **Auto-reclaim vs manual takeover.** Closing the active tab lets a blocked tab
  reclaim on its own after ~6s. Taking over explicitly ("Use this tab instead")
  also resyncs the session list and open conversation; auto-reclaim does not —
  it just unblocks the tab with whatever it had loaded.
- **Old sockets are dropped first.** `streamSession` closes the previous socket
  before opening a new one (`useChatSession.ts:83`), so switching sessions or
  reclaiming mid-stream can't double-append frames.
- **Blocked tabs keep nothing to catch up on.** A tab that was blocked the whole
  time has only its mount-time session list; after reclaiming it relies on the
  sidebar + `GET /get_messages` for anything newer.
- **The marker is per-session, not per-tab.** `pending:{session_id}` is written
  on *every* enqueue and cleared by the worker when the job finishes, so a fresh
  tab always reflects the true in-flight state regardless of which tab sent the
  message.

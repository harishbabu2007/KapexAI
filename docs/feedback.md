# Feedback → Google Sheets

Users can send product feedback from the chat workspace. The backend appends one
row per submission to a Google Sheet. Nothing goes through the LLM worker, and
no Prisma schema change is involved.

The whole feature is optional and off by default. When it is off, the Feedback
button is not rendered, `POST /feedback` returns `503`, and every other route
behaves exactly as before.

---

## Contents

- [How it works](#how-it-works)
- [Setup](#setup)
- [Disabled mode](#disabled-mode)
- [Teammate setup](#teammate-setup)
- [The sheet contract](#the-sheet-contract)
- [Two tabs are not a security boundary](#two-tabs-are-not-a-security-boundary)
- [What is and is not stored](#what-is-and-is-not-stored)
- [Dialog behaviour](#dialog-behaviour)
- [Rate limits](#rate-limits)
- [Delivery semantics and limitations](#delivery-semantics-and-limitations)
- [Tests](#tests)
- [Troubleshooting](#troubleshooting)
- [Support](#support)

---

## How it works

```
FeedbackDialog (frontend)
  └─ POST /feedback  (Bearer JWT)
       ├─ load_feedback_config()      env only, no network
       ├─ consume_feedback_quota()    Redis Lua: 20s cooldown + 10/hour
       ├─ get_session()               ownership check for the optional session_id
       ├─ build_feedback_row()        10 mapped values
       └─ append_feedback_row()       google-auth refresh (thread) + one
                                      httpx POST …/values/'Tab'!A10:J:append
```

`GET /auth/me` and `POST /auth/google` report `feedback_enabled`, which is how
the frontend knows whether to render the button. That value is a plain
environment read — **authentication never triggers a Google call**.

Relevant files:

| File | Role |
|---|---|
| `backend/routers/feedback.py` | The `POST /feedback` endpoint |
| `backend/utils/feedback_config.py` | Env-driven config, `sanitize_page_path` |
| `backend/utils/feedback_sheets.py` | Credential refresh + the single append call |
| `backend/utils/feedback_limits.py` | Redis Lua rate limiter |
| `backend/models/models.py` | `FeedbackRequest` (rejects unknown fields) |
| `backend/tests/test_feedback.py` | Mocked tests for all of the above |
| `frontend/src/components/feedback/FeedbackDialog.tsx` | The dialog |
| `frontend/src/components/chat/Sidebar.tsx` | Feedback button (bottom, above the divider) |
| `frontend/src/lib/api.ts` | `submitFeedback`, `describeFeedbackError` |

---

## Setup

### 1. Google Cloud project

1. Enable the **Google Sheets API** for the project.
2. Create a **service account** and download its JSON key. Keep the key outside
   the repository — the default location `~/.config/kapexai/` works well.
3. Create the spreadsheet, then **share it with the service account's
   `client_email` as an Editor**. Without this the append fails with `403`.

### 2. Create the tab

Both tabs (`FeedbackDev` and `Feedback`) must already exist with these headers
in **row 1, columns A–J**:

```
feedback_id | created_at_utc | user_id | category | message | page_path | session_id | contact_allowed | contact_email | status
```

The backend never writes a header row and never rewrites existing data. It
appends below the table using `valueInputOption=RAW` and
`insertDataOption=INSERT_ROWS`.

### 3. Configure the backend

Add to the repository-root `.env` (see `.env.example` for placeholders):

```sh
FEEDBACK_ENABLED="true"

# One of the two credential options:
FEEDBACK_GOOGLE_APPLICATION_CREDENTIALS="/home/you/.config/kapexai/feedback-service-account.json"
# FEEDBACK_GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account", ...}'

FEEDBACK_SPREADSHEET_ID="<spreadsheet id from the URL>"
FEEDBACK_SHEET_NAME="FeedbackDev"
```

`FEEDBACK_GOOGLE_APPLICATION_CREDENTIALS` is a **path** and is the normal local
setup. `FEEDBACK_GOOGLE_SERVICE_ACCOUNT_JSON` is the same key inlined as JSON and
is intended for deployments that inject secrets from a vault, so no key file has
to exist in the image. Both are backend-only; the frontend never sees either.

Values are read on **every request**, so you can flip `FEEDBACK_ENABLED` or
change the tab without restarting anything.

### 4. No frontend configuration

There is nothing to add to `frontend/.env.local`. The frontend only needs the
`feedback_enabled` flag that `/auth/me` already returns.

---

## Disabled mode

Leave `FEEDBACK_ENABLED` unset (or `false`, `0`, `no`, `off`). Then:

- `feedback_enabled` is `false` in the login and `/auth/me` responses;
- the Feedback button is not rendered;
- `POST /feedback` returns `503` with `code: "feedback_disabled"`;
- no credential is loaded, no client is created, and no Google call is made.

An unrecognised value (a typo) is treated as **off**, so a mistake fails safe
rather than enabling the feature by accident. A missing spreadsheet id, sheet
name, or usable credential also results in `503` rather than an error at
startup — misconfiguration can never take down auth, chat, or the WebSocket.

---

## Teammate setup

Each developer needs their own credentials. Do **not** copy a teammate's key
file into the repo or into a shared `.env`.

1. Ask the project owner to add your service account's `client_email` to the
   spreadsheet as an Editor (or create one service account per person).
2. Create your own `.env` from `.env.example` and fill in your own path.
3. If you would rather not keep a key file, use `FEEDBACK_GOOGLE_SERVICE_ACCOUNT_JSON`
   in your own `.env` instead.
4. Run `uv sync` (the `google-auth[requests]` dependency is already declared) and
   `make generate`.
5. Start the backend and confirm the button appears in the sidebar. Then send one
   row and check it landed in your tab.

To work without feedback at all, just leave `FEEDBACK_ENABLED` off — nothing
else in the app changes.

---

## The sheet contract

| Column | Source | Notes |
|---|---|---|
| `feedback_id` | server | UUID generated per submission; also returned to the user as the reference |
| `created_at_utc` | server | ISO-8601 UTC, e.g. `2026-01-31T09:15:00Z` |
| `user_id` | authenticated user | Never taken from the request body |
| `category` | request | `bug`, `feature_request` or `general` |
| `message` | request | Trimmed, 1–2,000 characters |
| `page_path` | request, sanitised | One of `/`, `/chat`, `/business-profile`; anything else becomes empty |
| `session_id` | request, ownership-verified | Empty when there is no active session (observed empty in manual testing) |
| `contact_allowed` | request | Written as a real boolean cell (`TRUE`/`FALSE`), not text |
| `contact_email` | authenticated user | **Empty unless** `contact_allowed` is true |
| `status` | server | Always `new` on insert |

`sanitize_page_path` drops query strings and fragments before matching, so a
path like `/chat?session=abc#x` is stored as `/chat`. Unknown paths (including
absolute URLs and traversal attempts) become empty rather than being stored.

### Two tabs are not a security boundary

`FeedbackDev` and `Feedback` are just two tabs on **one spreadsheet**, with one
set of Editor permissions. They are a convenience for separating test rows from
real ones — not an access-control boundary. Anything with Editor access to the
spreadsheet can read both tabs and every column in them, including the
`contact_email` column for users who consented to be contacted.

If you need real isolation, put the development spreadsheet in a **separate
Google Cloud project** with its own service account.

---

## What is and is not stored

Stored: the category, the message, a server-generated id, a UTC timestamp, your
KapexAI user id, the sanitised page path, an optional session id, the consent
flag, and — only with consent — your email.

Never stored: chat transcripts, business-profile fields, prompts, tokens,
credentials, or any raw response from Google. Only the ten mapped columns are
written.

Logs contain the feedback id, the category, the delivery outcome and a sanitised
reason code. They never contain the message, the email, an access token, or a
raw upstream response body.

---

## Dialog behaviour

Worth knowing before you change the form, because these are deliberate:

- The button sits **outside** the scrolling session list, above the divider, so
  it stays reachable with both an empty and an active chat.
- The empty-chat state renders `ChatHeader` inside `.chat-empty-header` purely
  to get its menu button on mobile. It is `display: none` above 760px, so the
  desktop welcome layout is unchanged.
- In-flight ownership lives in `ChatPage`, not in the dialog. The dialog unmounts
  when it closes, so a flag kept there would reset and let a *second*
  submission start while the first may still be written. The parent owns the
  draft, the pending flag and the outcome, and delegates the request rules to
  `createFeedbackLifecycle` (`frontend/src/lib/feedbackLifecycle.ts`).
- **Closing the dialog only hides it.** It does not abort the request and does
  not clear the pending state or the draft. Two reasons, both load-bearing:
  - Aborting a `fetch` does *not* establish that the backend skipped the write.
    Once the request is out, only the response can tell you the outcome, so
    discarding it would mean discarding the only chance of learning whether a row
    exists. (The backend's 20s cooldown is a *separate* guard against double
    sends; it is not a substitute for the client guard and does not undo a write.)
  - Clearing the pending flag on close would re-enable Send on a reopened dialog,
    which is exactly how a duplicate row gets written.
- A dialog that opens while a request is in flight shows "A previous submission
  is still being sent" with the form disabled, and the typed values are still
  there. `createFeedbackLifecycle` exposes only `submit`, `abort` and
  `isPending` — there is deliberately no `close`/`cancel` method for a dialog
  dismissal to reach, so this cannot regress by accident.
- Only the **owning request's completion** may publish state: each submission
  takes a sequence number and a stale completion is dropped, so a late reply can
  never overwrite a newer outcome. Only after it settles does the pending flag
  clear, which is when a new submission is allowed.
- On unmount the in-flight request is aborted, but that is **socket cleanup
  only** and is not a cancellation guarantee. If an abort does happen, the
  result is reported as `delivery: "uncertain"` with `code: "request_aborted"`,
  never as a confirmed failure.
- The submit button is disabled while a request is in flight, so a double-click
  cannot queue a second row. A second `submit()` while one is in flight is
  ignored outright, so it cannot send even if the button were re-enabled.
- Form values survive a failure and a close, and are cleared only by the
  explicit "Send more" reset. On success the dialog shows the reference id plus
  whether your email was kept.
- `aria-modal` is paired with a Tab focus trap, and focus returns to whichever
  control opened the dialog. Escape closes, including mid-request (which hides
  the dialog and leaves the request running).
- Regression tests for all of the above live in `frontend/tests/` and run on
  Node's built-in runner with an injected fake `send`, so they never reach
  `/feedback`: `npm test` in `frontend/`.

---

## Rate limits

Both limits are applied by a single Redis Lua script, so a submission cannot
slip past one of them and a rejection costs one round trip:

- **20-second cooldown** between submissions per user (`feedback:cooldown:{user_id}`);
- **10 submissions per hour** per user (`feedback:hourly:{user_id}`).

A limited request gets `429` with a `Retry-After` header and a `retry_after`
value in the body.

### Order of the guards

The exact sequence matters, so it is pinned by tests:

1. **Authentication** → `401`. Resolved by FastAPI before the handler runs, so an
   unauthenticated request reaches neither Redis nor Google.
2. **Body shape** → `422`. Also resolved by FastAPI (`extra="forbid"`, category
   `Literal`, length bounds), so a malformed body never enters the handler and
   cannot reach the sheet.
3. **Rate limit** → Redis. Ahead of the checks below, so a client cannot hammer
   them for free. A body that fails *shape* validation costs no quota — harmless,
   since it cannot reach the write path anyway.
4. **Semantic validation** → `422` for a message that is blank after trimming or
   over 2,000 characters. The model is given a looser bound (4,000) on purpose so
   an over-long paste gets a readable sentence instead of a raw validation dump.
5. **Session ownership** → `404` if the optional `session_id` is not the
   caller's.
6. **The write** → `201`, or `502` with an honest delivery verdict.

Because steps 1–2 are outside the handler, "the limiter runs before validation"
is only true of the *semantic* checks in steps 4–5.

If Redis cannot be reached the endpoint returns `503`
(`code: "feedback_limiter_unavailable"`) rather than serving unlimited writes.
This is fail-closed **for feedback only** — chat, auth, sessions and the
WebSocket are unaffected by a Redis outage.

---

## Delivery semantics and limitations

This is **best-effort delivery**. It is deliberately *not* exactly-once, and
*not* guaranteed at-least-once.

The response reports one of three verdicts, and they are not equally strong. Only
the first two establish what happened:

- **`delivered` — confirmed success.** Google returned a successful append
  response, so the row was accepted by the API. This does not mean a human has
  read it.
- **`failed` — confirmed failure *where it can be established*.** Some failures
  provably happened before or instead of a write: a rate-limit rejection, a
  validation or ownership error, or a `4xx` from Google (the append was rejected
  by the API). The message was not saved. Note that a transport error we
  classified as a connect failure is a best-effort inference from the error
  class, not a positive proof that no row exists.
- **`uncertain` — outcome unknown.** A read timeout, a connection broken
  mid-flight, or a `5xx` from Google returns `502` with
  `code: "feedback_uncertain"`. **The client cannot determine whether the row was
  written**, and neither can the user. This is the honest answer rather than a
  guess in either direction; the dialog says so explicitly and warns that
  resubmitting may create a duplicate.

Because the client cannot verify the sheet, **no response should be read as proof
of what is in the spreadsheet** beyond the confirmed cases above. To check, read
the tab with read-only access.

Additional limitations:

- **No automatic retries.** The append is issued exactly once. A retry after an
  ambiguous failure would create a duplicate row, so the code does not do it.
- **Feedback can be lost silently at the edges** — e.g. a tab closed before the
  request left, or a proxy cutting the connection. There is no queue and no
  dead-letter path.

### Resource handling

`google-auth`'s refresh is blocking, so it runs via `asyncio.to_thread`, never on
the event loop. Two details are load-bearing:

- **The token request carries its own timeout** (8s, imposed on the `requests`
  session). This is *not* redundant with the outer wait bound. `google-auth`'s
  transport defaults to **120s**, and its IAM-endpoint path passes
  `timeout=None` (block indefinitely). A thread cannot be cancelled, so without
  an explicit socket bound a hung token endpoint would keep a thread alive for
  minutes after the request that started it was already answered.
- **Single-flight, not a lock.** A plain `asyncio.Lock` would be wrong here: when
  a caller gives up waiting, the lock is released while its thread is still
  running, and the next caller starts a *second* concurrent token round trip.
  Instead there is at most one refresh task; a caller that times out abandons
  only the *wait* (`asyncio.shield`), and the next caller attaches to the same
  task and can even inherit its token. Cancelling instead would orphan the
  thread and throw the token away.

Bounds: token socket 8s, overall token wait 12s, Sheets call 15s. The
`httpx.AsyncClient` is created lazily and closed in the FastAPI lifespan
shutdown, so a process that never receives feedback holds no connection.

---

## Tests

```sh
.venv/bin/python -m pytest backend/tests/ -q
.venv/bin/python -m pytest backend/tests/test_feedback.py -q   # feedback only
```

`test_feedback.py` mocks the Google token refresh and HTTP call, Redis and the
database, so it performs **no network I/O and writes no rows**. It covers
authentication, the flag on both auth responses, validation and unknown-field
rejection, session ownership, consent, row mapping, the RAW/INSERT_ROWS request
shape, configuration states, both rate limits plus limiter failure, the
uncertain-write and confirmed-failure paths, and the client/token lifecycle
(including that the lifespan closes the client and that authentication never
initialises it).

`TestFeedbackEndToEnd` additionally drives the real endpoint with only the two
external boundaries faked — a `redis.eval` stub and an `httpx.MockTransport` —
so the config → limiter → row-builder → append wiring is exercised as a whole:
one submission asserted down to the ten individual column values, one
`ReadTimeout` surfaced as `502 feedback_uncertain`, and one cooldown rejection
produced by the limiter's own verdict rather than a stubbed decision.

The frontend's request lifecycle is covered by `frontend/tests/`, run with
`npm test` in `frontend/`. These use Node's built-in test runner
(`node --experimental-strip-types --test`) — **no test framework is installed** —
and inject a fake `send`, so they never reach `/feedback` or write a row. They
cover: one request at a time, pending surviving a close, close not aborting, the
success and failure outcome surviving a close, an abort reporting `uncertain`,
and source-level invariants on `ChatPage`/`FeedbackDialog` that pin the
close-only behaviour. Verify types with `npm run build`, which runs `tsc -b`.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| No Feedback button | `FEEDBACK_ENABLED` is not a truthy value, or the response predates the flag | Check the env value; the frontend defaults to hidden when the field is absent |
| `503 feedback_disabled` | Feature off, or spreadsheet id / sheet name / credentials missing or unusable | Compare your `.env` against `.env.example`; the value must be a real readable key file or valid JSON |
| `403` upstream → `feedback_failed` | The service account is not an Editor on the spreadsheet | Share the spreadsheet with the key's `client_email` |
| `404` on the spreadsheet | Wrong `FEEDBACK_SPREADSHEET_ID`, or the tab name is misspelled | The id is the long token in the sheet URL; the tab must already exist |
| `400` upstream → `feedback_failed` | Tab headers are missing or reordered | Row 1, A–J must match the contract above |
| `429` on every attempt | The 20s cooldown is active, or 10/hour is used up | Wait for `retry_after` seconds |
| `503 feedback_limiter_unavailable` | Redis is unreachable | Fix Redis; no other feature is affected |
| `502 feedback_uncertain` | Google timed out or returned `5xx` | Check the sheet before resending — it may already be there |
| Works locally, fails on Railway | No credentials in the deployment environment | Set the feedback env vars in the service's variables, and confirm `.dockerignore` did not strip a file you expected in the image |
| `ModuleNotFoundError: google.auth` | Dependencies not synced | `uv sync --all-packages` |

Check the backend logs: they print the feedback id, category and a sanitised
reason code — enough to correlate with the reference id the user was shown,
without logging the message itself.

### Smoke test for a new deployment (FeedbackDev)

Once a real write is approved, the smallest useful check is **one** row in
`FeedbackDev`:

1. Start the backend with `FEEDBACK_ENABLED=true`, `FEEDBACK_SHEET_NAME=FeedbackDev`.
2. Send one Bug from the chat workspace with the contact box **unchecked**, and
   note the reference id.
3. Confirm exactly one new row, with the ten headers intact, a boolean `FALSE` in
   `contact_allowed`, an **empty** `contact_email`, `status = new`, and
   `page_path` = `/chat`.
4. Check the backend log line for that correlation id contains no message text.

**Do not send a second submission** to observe a `429`. The cooldown and the
duplicate-row guards are covered by the automated tests; a second live request
buys nothing and costs a row plus a cooldown wait.

### What was actually verified, and how

Keep this distinction, because the two kinds of evidence are not
interchangeable: an **automated** test drives the code, while a **manual browser**
check means a person actually used the UI.

| Check | Kind | Result |
|---|---|---|
| Three manual submissions through the local chat UI | manual browser | **Done** — 3 rows written to `FeedbackDev` |
| Read-back of those 3 rows (see below) | manual + read-only API | **Done — all checks passed** |
| Ten A–J headers intact | read-only API | **Done — exact match** |
| `contact_allowed` stored as a real boolean cell | read-only API | **Done — `userEnteredValue` is `boolValue`, not text** |
| Production `Feedback` tab untouched | read-only API | **Done — header row only, 0 data rows** |
| Request lifecycle: one-at-a-time, pending survives close, close does not abort, outcome survives close, abort reports `uncertain` | **automated** (`frontend/tests/`, Node built-in runner, injected fake `send`) | **Done — 15/15 pass** |
| `closeFeedback`/`openFeedback` source invariants (no abort, no state clearing on close) | **automated** (source assertions) | **Done** |
| Backend guard order, rate limiting, row mapping, timeout/single-flight token refresh, error contract | **automated** (`backend/tests/test_feedback.py`) | **Done — 174 pass** |
| Close/reopen in a real browser with an intercepted request | manual browser | **NOT DONE** |
| Keyboard: focus trap, Tab order, Escape, focus return | manual browser | **NOT DONE** |
| Mobile layout / sidebar entry point at narrow widths | manual browser | **NOT DONE** |
| Leading-`=` `RAW` string handling (a message beginning with `=`) | manual browser | **NOT DONE** |

The three rows were read back with **read-only** Sheets access
(`spreadsheets.readonly` scope, `values.get` / `spreadsheets.get` only). No
update, insert, clear or delete call was made at any point, and no additional
feedback was submitted.

| Row | Category | `contact_allowed` | `contact_email` | Other columns |
|---|---|---|---|---|
| 10 | `general` | boolean `TRUE` | present, matches the user's DB email | id distinct; message `testing feedback`; `/chat`; `status=new`; ISO-8601 UTC with `Z` |
| 11 | `feature_request` | boolean `FALSE` | **empty** (consent withheld) | id distinct; message `testing feedback 2.0`; `/chat`; `status=new`; ISO-8601 UTC with `Z` |
| 12 | `bug` | boolean `TRUE` | present, matches the user's DB email | id distinct; message `testing feedback 3.0`; `/chat`; `status=new`; ISO-8601 UTC with `Z` |

The withheld email on row 11 is the point of `contact_allowed`: the same user
produced both a populated and an empty `contact_email` purely from the checkbox,
which confirms consent is honoured server-side and not just in the UI.

**Row positions:** the three verified submissions occupy rows 10, 11 and 12. Rows
2–9 are blank — no values in either `userEnteredValue` or `effectiveValue`, and no
background, border or number-format styling. We did not establish why the first
append landed on row 10 rather than row 2, so treat the insert position as unknown.
Nothing is lost or overwritten and later appends followed sequentially (11, then
12), but do not assume rows will be tightly packed, and never compute an offset
from the row number.

### Checking close/reopen without writing anything

This is covered automatically (`npm test` in `frontend/`) but has **not** been
performed in a browser. To check it by hand, **intercept the request so it cannot
reach the backend** — e.g. a DevTools local override, or a request block on
`*/api/feedback` that you then replace with a stubbed response. Never do this
with the real backend pointed at `FeedbackDev`, because a blocked request that
has already left the browser may still be written.

With the request stubbed to stay in flight, confirm that:

1. submitting shows the pending state and disables the form;
2. closing and reopening the dialog still shows pending, still disabled, with the
   typed values intact;
3. a second Send click while pending does not produce a second request;
4. once the stub resolves, closing and reopening shows the success and its
   reference id (or the failure and its code) with the values still there.

---

## Support

The `feedback_enabled` flag is reported on `/auth/me` and the popup login
response, so the frontend never has to guess. When reporting an issue, include
the feedback id and the `code` from the response body — never the message text.

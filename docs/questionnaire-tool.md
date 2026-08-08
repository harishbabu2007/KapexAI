# The Questionnaire Tool — a beginner's guide

This document explains how the **questionnaire tool** works, in plain language,
so that someone opening the code for the first time can follow along.

**Files you'll touch/read:**
- `worker/tools/questionnaire_tool.py` — the tool itself (the main file, 197 lines)
- `worker/prompts/questionnaire.py` — the LLM "instructions" (prompt templates)
- `worker/helpers/messages.py` — the helpers the tool relies on
- `worker/agent.py` — the graph that decides *when* to run the tool

If you're new to the agentic pipeline, skim
[agentic-pipeline.md](agentic-pipeline.md) and
[queue-and-streaming.md](queue-and-streaming.md) first. This doc is a deep-dive
on just the questionnaire.

---

## 1. What the tool does (one paragraph)

When a user shares a business idea (e.g. "I want to open a coffee shop in
Pune"), the tool runs a short **interview**: it asks up to 5 targeted
questions, then stores the answers as the business "context" that the chat
agent and the other tools use later. Think of it as a polite interviewer:

1. **Phase 1 — "Let's start"**: read the idea, plan the questions, ask them.
2. **Phase 2 — "Let's listen"**: collect the answers (via the frontend slide
   UI or free-form text), store them as context.

The tool is also the **gatekeeper** for the whole assistant: tools that need
business context (SWOT, web research) are **not allowed to run** until this
questionnaire completes. Asking for a SWOT before the interview is done just
sends you here instead (see section 2).

The tool is also a **bouncer**. It will *not* accept:
- a command phrase like "Start the business questionnaire" as if it were a
  business idea, and
- gibberish / off-topic answers like "bla bal .....".

If either happens, it gently re-asks instead of absorbing the nonsense.

---

## 2. Where the tool sits in the pipeline

```
User message → router_node → tool_node → QuestionnaireTool.run() → message log + stream
```

`worker/agent.py` has two nodes:

- **`router_node`** decides *what* to do with the message. If a questionnaire is
  already waiting for answers, it **always** routes to the questionnaire tool —
  no LLM call needed:

  ```python
  # worker/agent.py:52
  if questionnaire_pending(state["messages"]):
      return {"intent": "tool", "tool": "questionnaire"}
  ```

  Otherwise it asks an LLM (`router_agent.classify`) whether the message is
  small talk (`chat`) or a request for a tool. The router is told that a new
  business idea — and also "set up / start / build a business" — should be
  routed to the questionnaire tool, so a user who wants guided setup gets the
  interview instead of an open-ended "what do you need?". The chat agent also
  proactively offers the questionnaire when there's no business context yet,
  rather than repeating "how can I help?".

  Finally there is a **context gate**: any tool with `requires_context = True`
  (SWOT, web research) is redirected to the questionnaire tool until a
  `questionnaire_complete` message exists:

  ```python
  # worker/agent.py:60
  if tool.requires_context and not questionnaire_complete(state["messages"]):
      return {"intent": "tool", "tool": "questionnaire"}
  ```

  So asking for a SWOT before the interview is done doesn't produce a generic
  SWOT from an empty context — it routes you to the questionnaire to build
  context first.

- **`tool_node`** looks up the tool by name in `worker/tools/registry.py`,
  calls its `run()` method, then persists + streams whatever it returns.

The questionnaire tool is registered in `worker/tools/registry.py:13`:

```python
register(QuestionnaireTool())
```

> **How does a tool get picked?** The router sees each tool's `name`,
> `description` and `example` (see `registry.list_tools()`). The questionnaire
> tool advertises itself as:
> `example = "Start the business questionnaire"` — that's how the LLM knows a
> user asking to "start the business questionnaire" should be sent here.

---

## 3. The magic state flag: `questionnaire_pending`

The tool has no internal memory of "am I mid-interview?" — it **recomputes** it
from the message log every turn. That's what
`questionnaire_pending()` does (`worker/helpers/messages.py:25`):

```python
def questionnaire_pending(messages: list[dict]) -> bool:
    pending = False
    for msg in messages:
        msg_type = msg.get("type")
        if msg_type == "questionnaire":
            pending = True            # assistant just asked questions
        elif msg_type == "questionnaire_answer":
            pending = False           # user just answered them
    return pending
```

Two message **types** flip the flag:

| Message `type` | What it means | Effect on the flag |
|---|---|---|
| `questionnaire` | The assistant asked the questions | **ON** |
| `questionnaire_answer` | The user answered them | **OFF** |

Because the flag is *derived from the log*, it survives restarts: if the Redis
state is rebuilt from the database, the questionnaire simply resumes where it
left off.

---

## 4. The entry point — `run()`

Every tool implements `run(state)` (see `worker/tools/base.py`). For the
questionnaire it's just two lines that pick the phase:

```python
# worker/tools/questionnaire_tool.py:34
async def run(self, state: dict) -> list[dict]:
    if questionnaire_pending(state["messages"]):
        return await self._collect(state)   # questions already asked → collect answers
    return await self._ask(state)           # nothing pending → start the questionnaire
```

`state` is the current conversation state. The only two fields the tool reads
are `state["messages"]` (the whole message log) and `state["user_input"]` (the
user's latest message).

`run()` returns a **list of message entries**. Each entry is a dict with at
least `role`, `agent`, `type`, `content`, plus extra fields that define the
message's own JSON shape. `tool_node` persists every entry to the DB and
streams the `ASSISTANT` ones to the frontend.

---

## 5. Phase 1 — `_ask()` (start the interview)

```python
# worker/tools/questionnaire_tool.py:39
async def _ask(self, state: dict) -> list[dict]:
    idea = str(state.get("user_input") or "").strip()

    if not idea or not await self._is_real_idea(idea):
        return self._request_idea(idea)                 # ← bouncer: not an idea

    plan = await self._plan(idea)
    facts = plan.get("facts", {}) or {}
    questions = plan.get("questions", [])[:MAX_QUESTIONS]

    answers = {"business_about": idea}
    for key in FACTS_KEYS:
        value = (facts.get(key) or "").strip()
        if value:
            answers[key] = value

    await update_session_business_idea(state["session_id"], idea)

    return [
        {"role": "USER", "agent": "TOOL", "type": "questionnaire_start",
         "content": idea},
        {"role": "ASSISTANT", "agent": "TOOL", "type": "questionnaire",
         "content": "Tell me a bit more so I can help you best. Please answer the following:",
         "questions": questions, "facts": answers},
    ]
```

Step by step:

1. **Take the idea.** `idea` = the user's latest message, trimmed.
2. **Bouncer check** (the newest guardrail). `_is_real_idea()` asks the LLM:
   *"is this actually a business idea?"* If the user typed a *command*
   ("Start the business questionnaire") or greeting or gibberish, it's `False`
   and we return `_request_idea()` instead — see section 7. This is what stops
   the literal phrase "Start the business questionnaire" from becoming the
   session's business idea.
3. **Plan the interview.** `_plan()` (section 8) calls the LLM and gets back a
   JSON plan: `{"facts": {...}, "questions": [{key, question}, ...]}`.
   - `facts` = details the idea *already* contains (location, target customer,
     vision) that we don't need to ask about.
   - `questions` = the gaps to fill, capped at `MAX_QUESTIONS` (= 5, defined in
     `worker/prompts/questionnaire.py:3`).
4. **Seed the answers.** We start the answer sheet with `business_about` (the
   raw idea text) plus any facts the idea already stated. The list of known
   keys is `FACTS_KEYS = ("business_location", "business_vision", "target_customers")`
   (`questionnaire_tool.py:22`).
5. **Rename the session.** `update_session_business_idea(session_id, idea)`
   sets the session's title / `business_idea` to the idea.
6. **Return two entries**:
   - `questionnaire_start` (USER) — records the idea in the log.
   - `questionnaire` (ASSISTANT) — the questions + `facts`. This is the entry
     that flips `questionnaire_pending` to **ON**, so the *next* message goes
     to `_collect()`.

---

## 6. Phase 2 — `_collect()` (gather the answers)

```python
# worker/tools/questionnaire_tool.py:77
async def _collect(self, state: dict) -> list[dict]:
    prior = last_message(state["messages"], "questionnaire")
    questions = prior.get("questions", []) if prior else []
    facts = dict(prior.get("facts", {}) or {}) if prior else {}

    answers_text = str(state.get("user_input") or "").strip()

    # Structured answers (submitted from the slide UI) arrive as a JSON
    # payload and map 1:1 onto the questions by key — no LLM *parsing* needed.
    # Each non-empty answer is still validated per-question; invalid ones
    # (gibberish) are re-asked and never folded into the context.
    structured = self._structured_answers(answers_text)
    if structured is not None:
        validity = await self._validate_structured(questions, structured)
        submitted = {
            str(a.get("key", "")): str(a.get("answer") or "").strip()
            for a in structured
        }
        bad = []
        for question in questions:
            key = question.get("key", "")
            answer = submitted.get(key, "")
            if not answer:
                continue
            if validity.get(key, True):
                facts[key] = answer
            else:
                bad.append(question)
        if bad:
            return self._reask(bad, facts, self._format_answers(bad, submitted))
        content = self._format_answers(questions, facts)
    else:
        # Bouncer check #2: genuine free-form answer? If not, re-ask.
        if not await self._validate(questions, answers_text):
            return self._reask(questions, facts, answers_text)
        parsed = await self._parse(questions, answers_text)
        for question, answer in zip(questions, parsed):
            key = question.get("key", "")
            if key:
                facts[key] = answer
        content = answers_text

    return [
        {"role": "USER", "agent": "TOOL", "type": "questionnaire_answer",
         "content": content, "answers": facts},
        {"role": "ASSISTANT", "agent": "TOOL", "type": "questionnaire_complete",
         "content": "Got it. I now have context about your business.",
         "context": facts},
    ]
```

Step by step:

1. **Recover the questions.** `last_message(messages, "questionnaire")`
   (`worker/helpers/messages.py:18`) scans backwards for the most recent
   `questionnaire` entry. Its `questions` and `facts` are copied so the new
   answer builds on them.
2. **Two ways to answer.** There are now two paths:
   - **Structured (default, from the slide UI).** The frontend collects one
     answer per question and posts them to
     `POST /submit_questionnaire_answers` as `[{key, answer}, ...]`. The worker
     receives a JSON payload like
     `{"kind": "questionnaire_answers", "answers": [...]}`; `_structured_answers()`
     recognises it and maps each answer onto its question **by key** — no LLM
     *parsing* is involved. But each non-empty answer is still checked by
     `_validate_structured()` (section 8b): gibberish like `"asdf"`/`"hehe"` is
     rejected so it never reaches the business context. Valid answers are folded
     in and only the invalid questions are re-asked (valid ones persist), so a
     genuine per-question answer is never lost.
   - **Free-form (legacy, typed in the composer).** `_validate()` (section 8)
     asks the LLM whether the reply genuinely answers the questions. If not
     (gibberish, off-topic, refusal), we return `_reask()` (section 7) — which
     re-emits a `questionnaire` entry, so `questionnaire_pending` stays **ON**
     and the interview continues. If valid, `_parse()` aligns the messy text to
     one JSON string per question.
3. **Merge into the facts.** Each answer is stored under its question's `key`
   (e.g. `q1`, `q2`, ...). For structured answers, `_format_answers()` also
   builds a readable numbered summary (e.g. `"1) dried mango"`) for the message
   log. Invalid answers are never written into `facts`.
4. **Return two entries**:
   - `questionnaire_answer` (USER) — the summary + the full merged `facts`.
     This flips `questionnaire_pending` to **OFF** → the questionnaire is done.
   - `questionnaire_complete` (ASSISTANT) — an acknowledgement carrying the
     final `context`. This is the message `business_context()` looks for, and
     the one that unlocks the context-gated tools.

If every submitted structured answer was garbage, `_reask()` is returned instead
of step 4: the questionnaire stays pending and no `questionnaire_complete` is
ever emitted, so nothing nonsense enters the business context.

---

## 7. The two "polite rejection" helpers

These are the bouncer's two re-ask scripts.

### `_request_idea()` — used when the first message isn't an idea

```python
# worker/tools/questionnaire_tool.py:132
def _request_idea(self, raw: str) -> list[dict]:
    return [
        {"role": "USER", "agent": "TOOL", "type": "questionnaire_request",
         "content": raw},
        {"role": "ASSISTANT", "agent": "TOOL", "type": "chat",
         "content": "Sure! To get started, could you share a little about your "
                    "business idea? For example, what you want to build or sell, "
                    "where, and who it's for."},
    ]
```

It replies with a friendly *"tell me your idea"* message (type `chat`, so the
frontend renders it as a normal bubble). Because it emits **no**
`questionnaire` entry, `questionnaire_pending` stays **OFF** — the user's next
message will be re-checked as a potential idea.

### `_reask()` — used when the answers are nonsense

```python
# worker/tools/questionnaire_tool.py:113
def _reask(self, questions: list[dict], facts: dict, answers_text: str) -> list[dict]:
    return [
        {"role": "USER", "agent": "TOOL", "type": "questionnaire_invalid",
         "content": answers_text},
        {"role": "ASSISTANT", "agent": "TOOL", "type": "questionnaire",
         "content": "That didn't quite answer the questions. ...",
         "questions": questions, "facts": facts},
    ]
```

It acknowledges the bad answer (as `questionnaire_invalid`, so the transcript
shows what happened), then **re-asks the same questions**. Re-emitting
`questionnaire` keeps `questionnaire_pending` = **ON** — the loop repeats until
the user gives real answers.

### Clarifying questions — "can you explain this in clearer words?"

A message that isn't a genuine answer is **not always a rejection**. In
`_collect`, when `_validate()` returns `False` the tool first runs
`_is_clarification()` (a lightweight LLM call, `CLARIFY_REQUEST_TEMPLATE`). If
the user is asking a question **about the questionnaire itself** — rephrasing
something in simpler words, what a term means, why it's asked, or an example —
`_explain()` answers it conversationally instead of re-asking:

```python
# worker/tools/questionnaire_tool.py — _explain()
return [
    {"role": "USER", "agent": "TOOL", "type": "chat", "content": user_text},
    {"role": "ASSISTANT", "agent": "TOOL", "type": "chat",
     "content": explanation},   # plain-language rephrase of the questions
]
```

It emits two `chat` bubbles (`EXPLAIN_QUESTIONS_TEMPLATE` rephrases each question
in simple words, focused on the one the user asked about). Because **no**
`questionnaire_answer` is written, `questionnaire_pending` stays **ON** and the
interview continues — the user's next message routes back into `_collect`. This
fixes the trap where *"can you explain this in clear words"* was rejected as a
botched answer and re-asked. On a `_is_clarification` parse hiccup it returns
`False`, so the normal re-ask path is the safe fallback.

`_is_clarification` is deliberately **permissive**: a clarification request
mixed with partial answers (e.g. *"1) can you explain this question again 2)
local this expand, 1cr"*) still counts as a clarification, so the user is
explained to instead of being told their whole message didn't answer the
questions.

### Structured clarification (the deck's "Explain in simpler words" button)

The slide deck exposes an **"Explain in simpler words"** button per question
(`frontend/src/components/messages/QuestionnaireCard.tsx`). Clicking it posts to
`POST /submit_questionnaire_clarification` (backend `main.py`) with
`{session_id, keys: [questionKey]}`. The backend pushes a structured job whose
`user_input` is `{"kind": "questionnaire_clarification", "keys": [...]}`.

In `_collect`, before the free-form guardrail, `_structured_clarification()`
recognises this payload and calls `_explain_keys()` — which filters to the
requested questions and calls `_explain()`. The questionnaire stays pending and
the user answers via the deck right after. No LLM validation is involved, so the
request can never be misclassified as a bad answer.

> Both `_reask` / `_request_idea` helpers are **synchronous** (no LLM call) —
> they just return message entries. The LLM decisions happen in
> `_is_real_idea` / `_validate` / `_is_clarification`.

---

## 8. The seven LLM calls (the "brains")

All use the same model (`mistral-small-2506`, `temperature=0.1`) and are
just a prompt template piped into the model. The prompts live in
`worker/prompts/questionnaire.py`.

> `_validate`, `_parse` and `_is_clarification` are only used for **free-form**
> answers typed in the composer. Answers from the frontend slide UI arrive as
> structured `{key, answer}` pairs — they skip *parsing* entirely, but are still
> individually checked by `_validate_structured`. `_explain` is used both by the
> free-form clarification path and by the deck's structured clarify button
> (via `_explain_keys`).

| Method | Prompt template | Input → Output | Failure mode |
|---|---|---|---|
| `_is_real_idea` (`:274`) | `IS_IDEA_TEMPLATE` | message → `{real_idea: bool}` | returns `False` (ask for idea) |
| `_plan` (`:208`) | `PLAN_QUESTIONNAIRE_TEMPLATE` | idea → `{facts, questions[]}` | raises `ValueError` |
| `_validate` (`:226`) | `VALIDATE_ANSWERS_TEMPLATE` | questions + free-form reply → `{valid: bool}` | returns `True` (don't block real answers) |
| `_validate_structured` (`:244`) | `VALIDATE_STRUCTURED_ANSWERS_TEMPLATE` | questions + `[{key, answer}]` → `{key: valid}` | returns `{}` (nothing blocked) |
| `_parse` (`:216`) | `PARSE_ANSWERS_TEMPLATE` | questions + free-form reply → `[answers]` | raises `TypeError` |
| `_is_clarification` | `CLARIFY_REQUEST_TEMPLATE` | questions + free-form reply → `{clarification: bool}` | returns `False` (fall back to re-ask) |
| `_explain` | `EXPLAIN_QUESTIONS_TEMPLATE` | user message + idea + questions → markdown explanation | falls back to `_reask` on empty output |
| `_structured_clarification` | — (parses JSON) | text → `list[str]` (keys) or `None` | returns `None` (free-form path) |
| `_explain_keys` | — (calls `_explain`) | questions + keys → `chat` bubbles | falls back to all questions |

A typical call looks like:

```python
# worker/tools/questionnaire_tool.py:150
async def _plan(self, idea: str) -> dict:
    chain = PLAN_QUESTIONNAIRE_TEMPLATE | self.llm
    response = await chain.ainvoke({"idea": idea, "max_questions": MAX_QUESTIONS})
    plan = parse_json(response.content)
    if not isinstance(plan, dict) or "questions" not in plan:
        raise ValueError(f"Unexpected questionnaire plan: {response.content}")
    return plan
```

Notes:
- `parse_json` (`worker/helpers/json_utils.py`) parses the LLM's JSON output
  **and raises on malformed JSON** — so the guard methods wrap it in
  `try/except`.
- The guard methods fail **safely** by design:
  - `_is_real_idea` → on a parse hiccup returns `False` (ask for the idea
    rather than risk absorbing a command).
  - `_validate` → on a parse hiccup returns `True` (don't annoy a user who gave
    a genuine answer).
  - `_validate_structured` → on a parse hiccup returns `{}`, which the caller
    reads as "nothing blocked" (every submitted answer passes).

---

## 9. What "business context" ends up being

After the questionnaire completes, the `facts` dict looks something like:

```json
{
  "business_about": "I want to open a specialty coffee shop in Pune...",
  "business_location": "Pune",
  "target_customers": "Young professionals",
  "q1": "Direct competitors: Starbucks, Blue Tokai...",
  "q2": "I'd charge Rs 250-350 per cup..."
}
```

`business_context()` (`worker/helpers/messages.py:38`) extracts it:

```python
def business_context(messages: list[dict]) -> dict:
    complete = last_message(messages, "questionnaire_complete")
    if complete:
        return complete.get("context") or {}     # full context after completion
    start = last_message(messages, "questionnaire_start")
    if start:
        return {"business_about": start.get("content", "")}   # idea only, mid-interview
    return {}
```

This dict is passed to the chat agent and other tools (see
`worker/agent.py:65`, `chat_node`) so every reply knows the business it's
talking about.

**The context gate.** `worker/agent.py` refuses to run tools that declare
`requires_context = True` (SWOT, web research) until
`questionnaire_complete(messages)` returns `True` — i.e. until this dict is
populated. Until then those requests are routed to the questionnaire tool.

---

## 10. Message types produced by this tool

| `type` | `role` | When it's emitted | Frontend rendering |
|---|---|---|---|
| `questionnaire_start` | USER | a real idea was accepted | user bubble |
| `questionnaire` | ASSISTANT | questions asked (or re-asked) | **slide questionnaire card** |
| `questionnaire_answer` | USER | answers collected (structured or free-form) | user bubble (numbered summary) |
| `questionnaire_complete` | ASSISTANT | answers acknowledged | "context saved" card |
| `questionnaire_request` | USER | command phrase seen, idea requested | user bubble |
| `questionnaire_invalid` | USER | nonsense answer rejected, re-ask sent | user bubble |

The `questionnaire` card renders as a **slide UI** (one question at a time with
Back / Next / Submit) — see `frontend/src/components/messages/QuestionnaireCard.tsx`.
Each slide also has an **"Explain in simpler words"** button that requests a
plain-language explanation of that question (see section 7). When the
questionnaire is already completed (or superseded by a re-ask), the card renders
as a plain read-only list instead. The frontend renders unknown types as plain
bubbles (see `frontend/src/components/messages/index.tsx`), so the two guardrail
types (`questionnaire_request` / `questionnaire_invalid`) need no special UI.

**The composer is locked while the deck is pending.** `useChatSession` computes
`questionnairePending` (a `questionnaire` message with no later
`questionnaire_answer` / `questionnaire_complete`) and `ChatPage` disables the
main input bar while it's true. The user can't abandon the deck by typing a
separate message; the only input channels are the deck itself and its
"Explain in simpler words" button. The composer unlocks once the questionnaire
completes.

---

## 11. A full example conversation

**Turn 1** — User: `"Start the business questionnaire"`

1. `router_node`: no questionnaire pending → LLM classifies → tool
   `questionnaire` (matches the tool's `example`).
2. `_ask()` → `_is_real_idea("Start the business questionnaire")` → **false**.
3. `_request_idea()` returns `questionnaire_request` (USER) + `chat`
   (ASSISTANT): *"Sure! To get started, could you share a little about your
   business idea?..."*
4. Result: no questionnaire started, session title unchanged. ✅

**Turn 2** — User: `"I want to open a specialty coffee shop in Pune, targeting young professionals"`

1. `_ask()` → `_is_real_idea` → **true**.
2. `_plan()` → facts `{business_location: "Pune", target_customers: "Young
   professionals"}`, 3 questions (competitors, pricing, differentiation).
3. Session title set to the idea. `questionnaire_start` + `questionnaire`
   emitted → `questionnaire_pending` = **ON**. ✅

**Turn 3** — User: `"bla bal ....."`

1. `router_node`: questionnaire pending → routes straight to the tool (no LLM).
2. `_collect()` → `_validate(...)` → **false**.
3. `_is_clarification(...)` → **false** (it's nonsense, not a question).
4. `_reask()` emits `questionnaire_invalid` (USER) + `questionnaire`
   (ASSISTANT) re-asking the same questions → `questionnaire_pending` stays
   **ON**. ✅ Nothing was absorbed.

**Turn 3b** — User (instead): `"1) can you explain this in clear words.."`

1. `router_node`: questionnaire pending → routes straight to the tool.
2. `_collect()` → `_validate(...)` → **false** (not an answer).
3. `_is_clarification(...)` → **true** (a question about the questionnaire).
4. `_explain()` emits two `chat` bubbles: the user's question + a plain-language
   rephrase of the questions. **No** `questionnaire_invalid` / re-ask.
   `questionnaire_pending` stays **ON**. ✅ The user is not trapped.

**Turn 4** — The user fills the slide UI and clicks **Submit**. The frontend
posts `POST /submit_questionnaire_answers` with
`[{key: "q1", answer: "Competitors: Starbucks and Blue Tokai."}, ...]`.

1. `_collect()` → `_structured_answers()` recognises the JSON payload.
2. Answers mapped onto `q1`, `q2`, `q3` **by key** — no `_validate` / `_parse`
   call, so nothing can be wrongly rejected.
3. `questionnaire_answer` (numbered summary) + `questionnaire_complete` emitted
   → `questionnaire_pending` = **OFF**. ✅

*(If the user instead types the answers free-form in the composer,
`_validate` → `_parse` are used as described in section 6.)*

Now `business_context(messages)` returns the full facts for the chat agent and
the context-gated tools (SWOT, web search, ...).

---

## 12. How to tweak it

- **Change the question cap**: edit `MAX_QUESTIONS` in
  `worker/prompts/questionnaire.py:3`.
- **Change which facts are seeded from the idea**: edit `FACTS_KEYS` in
  `questionnaire_tool.py:22` (and mirror it in `PLAN_QUESTIONNAIRE_PROMPT`).
- **Change the guardrail strictness**: edit `VALIDATE_ANSWERS_PROMPT` /
  `IS_IDEA_PROMPT` in `worker/prompts/questionnaire.py`.
- **Re-ask wording**: edit the `content` strings in `_request_idea()` /
  `_reask()`.

The tests that cover all of this live in `worker/tests/test_chat_tools.py`
(`test_questionnaire_asks_for_idea_when_trigger_phrase`,
`test_questionnaire_rejects_nonsense_answers`,
`test_questionnaire_auto_starts_then_collects`,
`test_questionnaire_structured_answers_bypass_parsing`,
`test_context_tools_gated_until_questionnaire_complete`,
`test_context_tool_runs_after_questionnaire_complete`). Run them with:

```bash
cd /home/harish/Code/KapexAI && PYTHONPATH=. .venv/bin/python -m pytest worker/tests/ -q
```

---

## 13. Key takeaways

- The tool is **stateless**: everything (pending state, questions, facts)
  lives in the message log, so it survives restarts.
- Two phases (`_ask` / `_collect`) are chosen purely by
  `questionnaire_pending()`, which is flipped by the `questionnaire` /
  `questionnaire_answer` message types.
- Answers arrive **structured by key** from the slide UI (no LLM), with a
  free-form fallback that keeps the `_validate` / `_parse` guards.
- Two LLM-powered guards keep the interview on track: `_is_real_idea`
  (command phrases can't become the idea) and `_validate` (nonsense answers
  can't become context). Both fail safely.
- The tool is the **context gatekeeper**: `requires_context` tools (SWOT, web
  research) don't run until `questionnaire_complete` exists.
- The tool returns **message entries**, and `tool_node` handles persisting +
  streaming them — the tool itself never touches the DB or pub/sub directly
  (except the session-title update in `_ask`).

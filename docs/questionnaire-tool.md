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
2. **Phase 2 — "Let's listen"**: read the answers, validate them, store them.

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
  business idea should be routed to the questionnaire tool.

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

    if not await self._validate(questions, answers_text):
        return self._reask(questions, facts, answers_text)   # ← bouncer: bad answer

    parsed = await self._parse(questions, answers_text)
    for question, answer in zip(questions, parsed):
        key = question.get("key", "")
        if key:
            facts[key] = answer

    return [
        {"role": "USER", "agent": "TOOL", "type": "questionnaire_answer",
         "content": answers_text, "answers": facts},
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
2. **Bouncer check #2.** `_validate()` (section 8) asks the LLM: *"does this
   reply genuinely answer the questions?"* If not (gibberish, off-topic,
   refusal), we return `_reask()` (section 7). The key detail: **`_reask`
   re-emits a `questionnaire` entry, not a `questionnaire_answer`**, so
   `questionnaire_pending` stays **ON** and the interview continues.
3. **Parse the free-form text.** `_parse()` (section 8) asks the LLM to align
   the user's messy reply ("1) Pune 2) young professionals ...") to a JSON
   array, one string per question (empty string if a question wasn't answered).
4. **Merge into the facts.** Each parsed answer is stored under its question's
   `key` (e.g. `q1`, `q2`, ...).
5. **Return two entries**:
   - `questionnaire_answer` (USER) — the raw answer + the full merged `facts`.
     This flips `questionnaire_pending` to **OFF** → the questionnaire is done.
   - `questionnaire_complete` (ASSISTANT) — an acknowledgement carrying the
     final `context`. This is the message `business_context()` looks for.

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

> Both helpers are **synchronous** (no LLM call) — they just return message
> entries. The LLM decisions happen in `_is_real_idea` / `_validate`.

---

## 8. The four LLM calls (the "brains")

All four use the same model (`mistral-small-2506`, `temperature=0`) and are
just a prompt template piped into the model. The prompts live in
`worker/prompts/questionnaire.py`.

| Method | Prompt template | Input → Output | Failure mode |
|---|---|---|---|
| `_is_real_idea` (`:186`) | `IS_IDEA_TEMPLATE` | message → `{real_idea: bool}` | returns `False` (ask for idea) |
| `_plan` (`:150`) | `PLAN_QUESTIONNAIRE_TEMPLATE` | idea → `{facts, questions[]}` | raises `ValueError` |
| `_validate` (`:168`) | `VALIDATE_ANSWERS_TEMPLATE` | questions + reply → `{valid: bool}` | returns `True` (don't block real answers) |
| `_parse` (`:158`) | `PARSE_ANSWERS_TEMPLATE` | questions + reply → `[answers]` | raises `TypeError` |

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

---

## 10. Message types produced by this tool

| `type` | `role` | When it's emitted | Frontend rendering |
|---|---|---|---|
| `questionnaire_start` | USER | a real idea was accepted | user bubble |
| `questionnaire` | ASSISTANT | questions asked (or re-asked) | questionnaire card |
| `questionnaire_answer` | USER | valid answers collected | user bubble |
| `questionnaire_complete` | ASSISTANT | answers acknowledged | "context saved" card |
| `questionnaire_request` | USER | command phrase seen, idea requested | user bubble |
| `questionnaire_invalid` | USER | nonsense answer rejected, re-ask sent | user bubble |

The frontend renders unknown types as plain bubbles (see
`frontend/src/components/messages/index.tsx`), so the two guardrail types
(`questionnaire_request` / `questionnaire_invalid`) need no special UI.

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
3. `_reask()` emits `questionnaire_invalid` (USER) + `questionnaire`
   (ASSISTANT) re-asking the same questions → `questionnaire_pending` stays
   **ON**. ✅ Nothing was absorbed.

**Turn 4** — User: `"1) Competitors: Starbucks and Blue Tokai. 2) Rs 250-350 per cup. 3) Single-origin specialty beans."`

1. `_collect()` → `_validate` → **true**.
2. `_parse()` → `["Competitors: Starbucks and Blue Tokai.", "Rs 250-350 per cup.", "Single-origin specialty beans."]`.
3. Facts merged under `q1`, `q2`, `q3`. `questionnaire_answer` +
   `questionnaire_complete` emitted → `questionnaire_pending` = **OFF**. ✅

Now `business_context(messages)` returns the full facts for the chat agent and
the other tools (SWOT, web search, ...).

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
`test_questionnaire_auto_starts_then_collects`). Run them with:

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
- Two LLM-powered guards keep the interview on track: `_is_real_idea`
  (command phrases can't become the idea) and `_validate` (nonsense answers
  can't become context). Both fail safely.
- The tool returns **message entries**, and `tool_node` handles persisting +
  streaming them — the tool itself never touches the DB or pub/sub directly
  (except the session-title update in `_ask`).

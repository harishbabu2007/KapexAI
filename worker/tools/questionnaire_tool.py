import json
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from langchain_mistralai import ChatMistralAI

from worker.helpers.json_utils import parse_json
from worker.helpers.messages import last_message, questionnaire_pending
from worker.helpers.persistence import update_session_business_idea
from worker.prompts.questionnaire import (
    CLARIFY_REQUEST_TEMPLATE,
    EXPLAIN_QUESTIONS_TEMPLATE,
    IS_IDEA_TEMPLATE,
    MAX_QUESTIONS,
    PARSE_ANSWERS_TEMPLATE,
    PLAN_QUESTIONNAIRE_TEMPLATE,
    VALIDATE_ANSWERS_TEMPLATE,
    VALIDATE_STRUCTURED_ANSWER_TEMPLATE,
)
from worker.tools.base import Tool

FACTS_KEYS = ("business_location", "business_vision", "target_customers")

MAX_REASKS = 2  # how often a single question may be re-asked before accepting

# Greetings/small talk that are never business ideas, even though they are
# meaningful prose. Kept deliberately small — anything longer or more specific
# is treated as an idea (conservative acceptance) rather than being rejected.
_GREETINGS = {
    "hi",
    "hello",
    "hey",
    "hii",
    "heyy",
    "heya",
    "hiya",
    "hola",
    "yo",
    "sup",
    "namaste",
    "namaskar",
    "hi there",
    "hey there",
    "hello there",
    "good morning",
    "good afternoon",
    "good evening",
    "good night",
    "how are you",
    "how are you doing",
    "whats up",
    "what's up",
    "are you there",
}


def _normalize(text: str) -> str:
    """Lowercases, removes punctuation and collapses whitespace so the
    deterministic checks below survive capitalization/casual typing."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text.lower())).strip()


def _is_questionnaire_command(text: str) -> bool:
    """True when the message is purely a command to run the questionnaire
    (e.g. "start the business questionnaire", "begin questionnaire"). The word
    "questionnaire" appearing anywhere in the message is treated as a command
    — business ideas essentially never mention it."""
    compact = re.sub(r"\W", "", text)
    return "questionnaire" in compact


def _is_gibberish(text: str, tokens: list[str]) -> bool:
    """True for keyboard mashing, filler and single-word fragments that cannot
    describe a business. Multi-token messages with real words are always
    meaningful enough to proceed."""
    if len(tokens) == 1 and len(text) <= 5:
        return True  # "asdf", "start", "cafe" — no meaningful idea here
    if len(tokens) > 1 and all(t == tokens[0] for t in tokens):
        return True  # "bla bla", "ha ha", "test test"
    for token in tokens:
        if len(token) >= 3 and not re.search(r"[aeiouy]", token):
            return True  # random consonant mash ("qwerty", "zxcvbn")
        if re.search(r"(.)\1\1", token):
            return True  # repeated keystrokes ("ssss", "haaaa")
    return False


def _is_obvious_idea(text: str, tokens: list[str]) -> bool:
    """True when the message clearly describes a business without needing the
    LLM: at least two words totalling eight or more characters. This covers
    short-but-meaningful ideas ("south indian restaurant in pune",
    "coffee shop in Pune") that a conservative LLM might reject."""
    return len(text) >= 8 and len(tokens) >= 2


class QuestionnaireTool(Tool):
    name = "questionnaire"
    description = "Gathers the business idea and asks a few targeted questions to build context."
    example = "Start the business questionnaire"
    suggestion = "Wanna fill in the business questionnaire to give me better context?"

    def __init__(self) -> None:
        self.llm = ChatMistralAI(model="mistral-small-2506", temperature=0.1)

    async def run(self, state: dict) -> list[dict]:
        if questionnaire_pending(state["messages"]):
            return await self._collect(state)
        return await self._ask(state)

    async def _ask(self, state: dict) -> list[dict]:
        idea = str(state.get("user_input") or "").strip()

        # A trigger phrase like "start the business questionnaire" is a request
        # to run the questionnaire, not a business idea. Ask for the real idea
        # instead of absorbing the command phrase as the business context.
        if not idea or not await self._is_real_idea(idea):
            return self._request_idea(idea)

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
            {
                "role": "USER",
                "agent": "TOOL",
                "type": "questionnaire_start",
                "content": idea,
            },
            {
                "role": "ASSISTANT",
                "agent": "TOOL",
                "type": "questionnaire",
                "content": "Tell me a bit more so I can help you best. Please answer the following:",
                "questions": questions,
                "facts": answers,
            },
        ]

    async def _collect(self, state: dict) -> list[dict]:
        prior = last_message(state["messages"], "questionnaire")
        questions = prior.get("questions", []) if prior else []
        facts = dict(prior.get("facts", {}) or {}) if prior else {}
        attempts = dict(prior.get("attempts", {}) or {}) if prior else {}

        answers_text = str(state.get("user_input") or "").strip()

        # Structured answers (submitted from the slide UI) arrive as a JSON
        # payload and map 1:1 onto the questions by key — no LLM *parsing* needed.
        # But they are still validated per answer: gibberish like "asdf"/"hehe"
        # must not be absorbed into the business context. Empty answers count as
        # skipped; only non-empty invalid ones are re-asked (valid ones persist).
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
                if validity.get(key, True) or attempts.get(key, 0) >= MAX_REASKS:
                    facts[key] = answer
                else:
                    attempts[key] = attempts.get(key, 0) + 1
                    bad.append(question)
            if bad:
                return self._reask(bad, facts, self._format_answers(bad, submitted), attempts)
            content = self._format_answers(questions, facts)
        else:
            # Structured "explain this in simpler words" requests (sent by the
            # deck's clarify button) are answered with a plain-language
            # explanation of the requested questions — the questionnaire stays
            # pending so the user can answer right after.
            clarification_keys = self._structured_clarification(answers_text)
            if clarification_keys is not None:
                return await self._explain_keys(questions, facts, clarification_keys)

            # Guardrail: if the reply doesn't genuinely answer the questions
            # (gibberish, off-topic, refusal), don't absorb it into the business
            # context. Re-ask instead so the questionnaire stays pending. A
            # persistent re-ask is capped by MAX_REASKS so the interview can
            # never loop forever.
            if not await self._validate(questions, answers_text):
                # But a question ABOUT the questionnaire itself (e.g. "can you
                # explain this in clearer words?", "what does X mean?") is not a
                # bad answer — answer it conversationally and keep the
                # questionnaire pending instead of rejecting the user.
                if await self._is_clarification(questions, answers_text):
                    return await self._explain(questions, facts, answers_text)
                if attempts.get("__reask__", 0) >= MAX_REASKS:
                    pass  # last resort: accept below
                else:
                    attempts["__reask__"] = attempts.get("__reask__", 0) + 1
                    return self._reask(questions, facts, answers_text, attempts)

            parsed = await self._parse(questions, answers_text)
            for question, answer in zip(questions, parsed):
                key = question.get("key", "")
                if key:
                    facts[key] = answer
            content = answers_text

        return [
            {
                "role": "USER",
                "agent": "TOOL",
                "type": "questionnaire_answer",
                "content": content,
                "answers": facts,
            },
            {
                "role": "ASSISTANT",
                "agent": "TOOL",
                "type": "questionnaire_complete",
                "content": "Got it. I now have context about your business.",
                "context": facts,
            },
        ]

    def _structured_answers(self, text: str) -> list[dict] | None:
        """Parses the structured answers payload sent by the frontend slide UI.
        Returns a list of `{key, answer}` dicts, or None when `text` is not a
        structured payload (so the legacy free-form path takes over)."""
        if not text:
            return None
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(data, dict) or data.get("kind") != "questionnaire_answers":
            return None
        answers = data.get("answers")
        if not isinstance(answers, list):
            return None
        return [
            a
            for a in answers
            if isinstance(a, dict) and isinstance(a.get("key"), str)
        ]

    def _structured_clarification(self, text: str) -> list[str] | None:
        """Parses the structured clarification payload sent by the deck's
        "explain in simpler words" button. Returns the question keys to explain,
        or None when `text` is not a clarification payload."""
        if not text:
            return None
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(data, dict) or data.get("kind") != "questionnaire_clarification":
            return None
        keys = data.get("keys")
        if not isinstance(keys, list):
            return None
        return [k for k in keys if isinstance(k, str)]

    def _format_answers(self, questions: list[dict], facts: dict) -> str:
        """Builds a readable summary of the collected answers for the message log."""
        lines = []
        for i, question in enumerate(questions, 1):
            key = question.get("key", "")
            answer = facts.get(key, "") if key else ""
            lines.append(f"{i}) {answer or 'Skipped'}")
        return "\n".join(lines)

    def _reask(
        self,
        questions: list[dict],
        facts: dict,
        answers_text: str,
        attempts: dict | None = None,
    ) -> list[dict]:
        return [
            {
                "role": "USER",
                "agent": "TOOL",
                "type": "questionnaire_invalid",
                "content": answers_text,
            },
            {
                "role": "ASSISTANT",
                "agent": "TOOL",
                "type": "questionnaire",
                "content": "That didn't quite answer the questions. Could you tell me a bit more about "
                "your business? Please reply to each question below:",
                "questions": questions,
                "facts": facts,
                "attempts": attempts or {},
            },
        ]

    async def _is_clarification(self, questions: list[dict], answers_text: str) -> bool:
        """True when the user's message is a question ABOUT the questionnaire
        itself (asking for simpler wording, a term's meaning, an example) rather
        than an attempt to answer. On a parse hiccup it returns False so the
        existing invalid-answer path (re-ask) takes over."""
        if not answers_text.strip():
            return False
        chain = CLARIFY_REQUEST_TEMPLATE | self.llm
        response = await chain.ainvoke(
            {
                "questions": json.dumps([q.get("question", "") for q in questions]),
                "message": answers_text,
            }
        )
        try:
            data = parse_json(response.content)
        except (json.JSONDecodeError, IndexError):
            return False
        if not isinstance(data, dict):
            return False
        return bool(data.get("clarification"))

    async def _explain(self, questions: list[dict], facts: dict, user_text: str) -> list[dict]:
        """Answers a clarifying question about the questionnaire with a
        plain-language explanation, keeping the questionnaire pending. Emits the
        user's question as a `chat` USER bubble and the explanation as a `chat`
        ASSISTANT bubble — no `questionnaire_answer` is written, so
        `questionnaire_pending` stays ON and the interview continues."""
        chain = EXPLAIN_QUESTIONS_TEMPLATE | self.llm
        response = await chain.ainvoke(
            {
                "user_message": user_text,
                "idea": str(facts.get("business_about", "") or ""),
                "questions": json.dumps(
                    [q.get("question", "") for q in questions], indent=2
                ),
            }
        )
        explanation = str(response.content or "").strip()
        if not explanation:
            return self._reask(questions, facts, user_text)
        return [
            {
                "role": "USER",
                "agent": "TOOL",
                "type": "chat",
                "content": user_text,
            },
            {
                "role": "ASSISTANT",
                "agent": "TOOL",
                "type": "chat",
                "content": explanation,
            },
        ]

    async def _explain_keys(
        self, questions: list[dict], facts: dict, keys: list[str]
    ) -> list[dict]:
        """Explains only the requested questions (from the deck's clarify
        button). Unknown keys fall back to explaining all questions."""
        wanted = [q for q in questions if q.get("key", "") in keys] or questions
        if len(wanted) == 1:
            user_text = "Could you please explain this question in simpler words?"
        else:
            user_text = "Could you please explain these questions in simpler words?"
        return await self._explain(wanted, facts, user_text)

    def _request_idea(self, raw: str) -> list[dict]:
        return [
            {
                "role": "USER",
                "agent": "TOOL",
                "type": "questionnaire_request",
                "content": raw,
            },
            {
                "role": "ASSISTANT",
                "agent": "TOOL",
                "type": "chat",
                "content": "Sure! To tailor my help to your business, I first need a little "
                "context about it. Could you share your business idea? For example, "
                "what you want to build or sell, where, and who it's for.",
            },
        ]

    async def _plan(self, idea: str) -> dict:
        chain = PLAN_QUESTIONNAIRE_TEMPLATE | self.llm
        response = await chain.ainvoke({"idea": idea, "max_questions": MAX_QUESTIONS})
        plan = parse_json(response.content)
        if not isinstance(plan, dict) or "questions" not in plan:
            raise ValueError(f"Unexpected questionnaire plan: {response.content}")
        return plan

    async def _parse(self, questions: list[dict], answers_text: str) -> list[str]:
        chain = PARSE_ANSWERS_TEMPLATE | self.llm
        response = await chain.ainvoke(
            {"questions": json.dumps(questions), "answers": answers_text}
        )
        data = parse_json(response.content)
        if not isinstance(data, list):
            raise TypeError(f"Expected a JSON list of answers: {response.content}")
        return [str(a) for a in data]

    async def _validate(self, questions: list[dict], answers_text: str) -> bool:
        """Returns True when the reply looks like a genuine answer to the
        questions. Nonsense/off-topic replies return False so the questionnaire
        stays pending instead of absorbing them."""
        if not answers_text.strip():
            return False
        chain = VALIDATE_ANSWERS_TEMPLATE | self.llm
        response = await chain.ainvoke(
            {"questions": json.dumps(questions), "answers": answers_text}
        )
        try:
            data = parse_json(response.content)
        except (json.JSONDecodeError, IndexError):
            return True  # on a parse hiccup, don't block genuine answers
        if not isinstance(data, dict):
            return True
        return bool(data.get("valid"))

    async def _validate_structured(
        self, questions: list[dict], answers: list[dict]
    ) -> dict[str, bool]:
        """Validates each non-empty structured answer against its own question,
        one LLM call per answer. Returns a `{key: valid}` map. Only clear
        gibberish/off-topic/refusal answers are rejected; genuine on-topic
        answers (even brief, partial, or unsure) pass. On a parse hiccup the
        answer passes so real ones aren't blocked."""
        q_by_key = {
            str(q.get("key", "")): str(q.get("question", "") or "")
            for q in questions
        }
        validity: dict[str, bool] = {}
        chain = VALIDATE_STRUCTURED_ANSWER_TEMPLATE | self.llm
        for a in answers:
            key = str(a.get("key", ""))
            answer = str(a.get("answer") or "").strip()
            if not answer or key not in q_by_key:
                continue
            try:
                response = await chain.ainvoke(
                    {"question": q_by_key[key], "answer": answer}
                )
                data = parse_json(response.content)
                validity[key] = (
                    bool(data.get("valid")) if isinstance(data, dict) else True
                )
            except (json.JSONDecodeError, IndexError):
                validity[key] = True
        return validity

    async def _is_real_idea(self, idea: str) -> bool:
        """True when the user's first message actually describes a business
        idea rather than being a command/greeting/gibberish.

        Deterministic checks run first and decide the obvious cases with no
        LLM dependency (a business description that simply names the product
        and place must never be blocked — and must not fail when Mistral is
        slow/down or returns malformed JSON). The LLM is retained only for the
        ambiguous middle (short single words), where classifying the intent
        adds value. In that middle path a malformed or failed response accepts
        instead of rejecting: the command/greeting/gibberish rejections above
        already guaranteed the message is plausible, so the safer outcome is
        to let the questionnaire proceed rather than ask for the idea again.
        """
        text = _normalize(idea)
        tokens = text.split()
        if not tokens:
            return False
        if _is_questionnaire_command(text):
            return False
        if text in _GREETINGS:
            return False
        if _is_gibberish(text, tokens):
            return False
        if _is_obvious_idea(text, tokens):
            return True

        chain = IS_IDEA_TEMPLATE | self.llm
        try:
            response = await chain.ainvoke({"idea": idea})
            data = parse_json(response.content)
            return bool(data.get("real_idea")) if isinstance(data, dict) else True
        except Exception:  # noqa: BLE001 - LLM/parse/network hiccup: accept, don't block
            return True

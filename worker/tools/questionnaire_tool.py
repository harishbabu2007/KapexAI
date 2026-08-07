import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from langchain_mistralai import ChatMistralAI

from worker.helpers.json_utils import parse_json
from worker.helpers.messages import last_message, questionnaire_pending
from worker.helpers.persistence import update_session_business_idea
from worker.prompts.questionnaire import (
    IS_IDEA_TEMPLATE,
    MAX_QUESTIONS,
    PARSE_ANSWERS_TEMPLATE,
    PLAN_QUESTIONNAIRE_TEMPLATE,
    VALIDATE_ANSWERS_TEMPLATE,
)
from worker.tools.base import Tool

FACTS_KEYS = ("business_location", "business_vision", "target_customers")


class QuestionnaireTool(Tool):
    name = "questionnaire"
    description = "Gathers the business idea and asks a few targeted questions to build context."
    example = "Start the business questionnaire"
    suggestion = "Wanna fill in the business questionnaire to give me better context?"

    def __init__(self) -> None:
        self.llm = ChatMistralAI(model="mistral-small-2506", temperature=0)

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

        answers_text = str(state.get("user_input") or "").strip()

        # Guardrail: if the reply doesn't genuinely answer the questions
        # (gibberish, off-topic, refusal), don't absorb it into the business
        # context. Re-ask instead so the questionnaire stays pending.
        if not await self._validate(questions, answers_text):
            return self._reask(questions, facts, answers_text)

        parsed = await self._parse(questions, answers_text)
        for question, answer in zip(questions, parsed):
            key = question.get("key", "")
            if key:
                facts[key] = answer

        return [
            {
                "role": "USER",
                "agent": "TOOL",
                "type": "questionnaire_answer",
                "content": answers_text,
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

    def _reask(self, questions: list[dict], facts: dict, answers_text: str) -> list[dict]:
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
            },
        ]

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
                "content": "Sure! To get started, could you share a little about your business "
                "idea? For example, what you want to build or sell, where, and who "
                "it's for.",
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
        except Exception:
            return True  # on a parse hiccup, don't block genuine answers
        if not isinstance(data, dict):
            return True
        return bool(data.get("valid"))

    async def _is_real_idea(self, idea: str) -> bool:
        """True when the user's first message actually describes a business
        idea rather than being a command/greeting/gibberish."""
        chain = IS_IDEA_TEMPLATE | self.llm
        response = await chain.ainvoke({"idea": idea})
        try:
            data = parse_json(response.content)
        except Exception:
            return False  # on a parse hiccup, ask for the idea instead of guessing
        if not isinstance(data, dict):
            return False
        return bool(data.get("real_idea"))

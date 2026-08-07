"""Optional LLM-backed analysis tools."""

from typing import Dict

from kapexai.prompts import SWOT_PROMPT

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency
    OpenAI = None


class LangChainAgent:
    def __init__(self, model_name: str = "gpt-4o", temperature: float = 0.2):
        if OpenAI is None:
            raise RuntimeError("The OpenAI package is not installed")
        self.client = OpenAI()
        self.model_name = model_name
        self.temperature = temperature

    def _call_llm(self, prompt: str) -> str:
        response = self.client.responses.create(
            model=self.model_name,
            input=prompt,
            temperature=self.temperature,
        )
        return response.output_text

    def generate_swot(self, topic: str) -> Dict:
        raw = self._call_llm(SWOT_PROMPT.format(topic=topic))
        return {"topic": topic, "raw": raw}

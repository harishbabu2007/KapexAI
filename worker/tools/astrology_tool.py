import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from langchain_mistralai import ChatMistralAI

from worker.helpers.json_utils import parse_json
from worker.helpers.messages import business_context, format_transcript
from worker.prompts.astrology import ASTROLOGY_TEMPLATE
from worker.tools.base import Tool

_DEFAULT_DISCLAIMER = (
    "Astrology is non-scientific and interpretive. Do not use for financial or legal decisions."
)


class AstrologyTool(Tool):
    name = "astrology"
    description = "Provide symbolic astrological chart insights for business timing, career themes, and reflective planning using Vedic and Western astrology."
    example = "Give me an astrological perspective on my business launch timing"
    suggestion = "Want an astrological perspective on your business?"
    requires_context = False

    def __init__(self) -> None:
        self.llm = ChatMistralAI(model="mistral-small-2506", temperature=0.4)

    async def run(self, state: dict) -> list[dict]:
        request = str(state.get("user_input") or "")
        context = business_context(state["messages"])
        transcript = format_transcript(state["messages"])

        chain = ASTROLOGY_TEMPLATE | self.llm
        response = await chain.ainvoke(
            {
                "business_context": json.dumps(context, indent=2),
                "transcript": transcript,
                "request": request,
            }
        )
        data = parse_json(response.content)
        if not isinstance(data, dict):
            raise TypeError(f"Unexpected astrology output: {response.content}")

        return [
            {
                "role": "USER",
                "agent": "TOOL",
                "type": "astrology_request",
                "content": request,
            },
            {
                "role": "ASSISTANT",
                "agent": "TOOL",
                "type": "astrology",
                "content": _format_insights(data),
                "insights": _insights_list(data),
                "disclaimer": str(data.get("disclaimer") or _DEFAULT_DISCLAIMER),
            },
        ]


def _insights_list(data: dict) -> list[str]:
    """Extracts the insights array, tolerating missing or malformed values."""
    insights = data.get("insights", [])
    if not isinstance(insights, list):
        return []
    return [str(i) for i in insights if str(i).strip()]


def _format_insights(data: dict) -> str:
    """Formats the astrology response into a readable markdown summary."""
    lines = []
    summary = str(data.get("summary") or "").strip()
    chart_type = str(data.get("chart_type") or "").strip()
    business_application = str(data.get("business_application") or "").strip()

    if summary:
        lines.append(summary)
        lines.append("")
    if chart_type:
        lines.append(f"**Chart type:** {chart_type}")
    for insight in _insights_list(data):
        lines.append(f"- {insight}")
    if business_application:
        lines.append("")
        lines.append(f"**Business application:** {business_application}")
    return "\n".join(lines).strip()
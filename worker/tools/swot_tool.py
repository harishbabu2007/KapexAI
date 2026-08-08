import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from langchain_mistralai import ChatMistralAI

from worker.helpers.json_utils import parse_json
from worker.helpers.messages import business_context, format_transcript
from worker.prompts.swot import SWOT_TEMPLATE
from worker.tools.base import Tool

_SECTION_LABELS = {
    "strengths": "Strengths",
    "weaknesses": "Weaknesses",
    "opportunities": "Opportunities",
    "threats": "Threats",
}


class SwotTool(Tool):
    name = "swot"
    description = "Creates a SWOT (Strengths, Weaknesses, Opportunities, Threats) analysis for a business."
    example = "Run a SWOT analysis for my business"
    suggestion = "Wanna get a SWOT analysis of your business?"
    requires_context = True

    def __init__(self) -> None:
        self.llm = ChatMistralAI(model="mistral-small-2506", temperature=0.4)

    async def run(self, state: dict) -> list[dict]:
        request = str(state.get("user_input") or "")
        context = business_context(state["messages"])
        transcript = format_transcript(state["messages"])

        chain = SWOT_TEMPLATE | self.llm
        response = await chain.ainvoke(
            {
                "request": request,
                "context": json.dumps(context, indent=2),
                "transcript": transcript,
            }
        )
        data = parse_json(response.content)
        if not isinstance(data, dict) or "sections" not in data:
            raise ValueError(f"Unexpected SWOT output: {response.content}")

        return [
            {
                "role": "USER",
                "agent": "TOOL",
                "type": "swot_request",
                "content": request,
            },
            {
                "role": "ASSISTANT",
                "agent": "TOOL",
                "type": "swot",
                "content": _format_swot(data),
                "sections": data.get("sections", {}),
                "summary": data.get("summary", ""),
            },
        ]


def _format_swot(data: dict) -> str:
    sections = data.get("sections", {})
    lines = []
    for key, label in _SECTION_LABELS.items():
        lines.append(f"### {label}")
        for item in sections.get(key, []):
            lines.append(f"- {item}")
        lines.append("")
    return "\n".join(lines).strip()

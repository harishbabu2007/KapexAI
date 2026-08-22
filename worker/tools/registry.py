from worker.tools.astrology_tool import AstrologyTool
from worker.tools.base import Tool
from worker.tools.legal_tools import (
    IndianCaseSearchTool,
    IndianLegalSearchTool,
    LegalIssueRegisterTool,
)
from worker.tools.finance_tool import FinanceTool
from worker.tools.indian_finance_tool import IndianFinanceTool
from worker.tools.questionnaire_tool import QuestionnaireTool
from worker.tools.swot_tool import SwotTool
from worker.tools.web_search_tool import WebSearchTool

_REGISTRY: dict[str, Tool] = {}


def register(tool: Tool) -> None:
    _REGISTRY[tool.name] = tool


register(QuestionnaireTool())
register(SwotTool())
register(WebSearchTool())
register(FinanceTool())
register(AstrologyTool())
register(IndianLegalSearchTool())
register(IndianCaseSearchTool())
register(LegalIssueRegisterTool())
register(IndianFinanceTool())


def get_tool(name: str) -> Tool | None:
    return _REGISTRY.get(name)


def list_tools() -> list[dict]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "example": tool.example,
            "suggestion": tool.suggestion,
        }
        for tool in _REGISTRY.values()
    ]

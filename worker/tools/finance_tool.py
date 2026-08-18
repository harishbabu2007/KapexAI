import json
import logging
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_mistralai import ChatMistralAI
from langgraph.prebuilt import create_react_agent

from worker.helpers.messages import business_context, format_transcript
from worker.tools.base import Tool
from worker.tools.equity_calculators import EQUITY_CALCULATOR_TOOLS
from worker.tools.finance_calculators import FINANCE_CALCULATOR_TOOLS
from worker.tools.finance_tools import FINANCE_TOOLS

FINANCE_SYSTEM_PROMPT = """\
You are KapexAI's finance specialist. You help business owners and entrepreneurs with financial
calculations, investment analysis, valuation, risk metrics, equity analysis, and U.S.
public-company (SEC) data.

You have access to a large library of precise financial tools (calculators, equity models, and
SEC filing lookups). ALWAYS prefer calling the right tool over estimating or guessing: every
number you produce should come from a tool call.

Guidance:
- Identify which operation(s) the user needs and call the matching tool(s) with the exact numbers
  the user provided. Never invent figures that were not given — if a value is missing, ask for it
  or state the assumption clearly.
- For public-company information, start with sec_company_lookup to resolve a ticker to its CIK,
  then use sec_company_submissions (filings) or sec_company_facts (XBRL financial facts).
- Rates are decimal values unless a tool's description says otherwise (e.g. 0.10 for 10%).
  Percent fields such as *_percent outputs are already multiplied by 100.
- A request may need SEVERAL tools. Call them in sequence and combine the results into one clear
  answer (for example: compute a company's beta, then its CAPM cost of equity and WACC).
- If a tool returns an "error" field or a tool fails (missing configuration, bad CIK, SEC
  request failure, invalid arguments), explain the problem to the user in plain language and
  suggest what they can fix — do not fabricate numbers to work around it.
- Present results concisely, labelling every computed figure, and note any limitations or
  assumptions.

Known business context (gathered from the questionnaire):
{context}

Conversation so far:
{transcript}"""


class FinanceTool(Tool):
    name = "finance"
    description = (
        "Performs financial calculations and analysis: investment returns, "
        "valuation (DCF, NPV, IRR), equity metrics (CAPM, WACC, ratios), risk "
        "(Sharpe, VaR), compound interest, and SEC public-company filings."
    )
    example = "Calculate the CAGR and future value of my investments"
    suggestion = "Wanna run a financial calculation (returns, valuation, risk, equity)?"
    requires_context = False

    def __init__(self) -> None:
        # One shared agent for the whole process: the underlying tools are bound
        # once here and reused across every run() call. The system prompt is
        # built per request (with the business context and message history), so
        # the agent is created without a static prompt.
        self.llm = ChatMistralAI(model="mistral-small-2506", temperature=0.1)
        self.agent = create_react_agent(
            self.llm,
            [
                *FINANCE_CALCULATOR_TOOLS,
                *EQUITY_CALCULATOR_TOOLS,
                *FINANCE_TOOLS,
            ],
        )

    def run(self, state: dict) -> list[dict]:
        prompt = str(state.get("user_input") or "").strip()
        context = business_context(state["messages"])
        transcript = format_transcript(state["messages"])

        system = FINANCE_SYSTEM_PROMPT.format(
            context=json.dumps(context, indent=2),
            transcript=transcript,
        )

        try:
            result = self.agent.invoke(
                {
                    "messages": [
                        SystemMessage(content=system),
                        HumanMessage(content=prompt),
                    ]
                }
            )
            content = result["messages"][-1].content
        except Exception as exc:  # defensive: never let an internal error escape raw
            logger.exception("Finance tool agent error")
            content = (
                "I couldn't complete that finance calculation — the finance service "
                f"hit an error ({exc.__class__.__name__}). Please try again, or rephrase "
                "your request with the numbers you have."
            )

        return [
            {
                "role": "USER",
                "agent": "TOOL",
                "type": "finance_request",
                "content": prompt,
            },
            {
                "role": "ASSISTANT",
                "agent": "TOOL",
                "type": "finance",
                "content": content,
            },
        ]
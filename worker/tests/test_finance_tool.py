import asyncio

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable

from worker.tools.base import Tool
from worker.tools.equity_calculators import EQUITY_CALCULATOR_TOOLS
from worker.tools.finance_calculators import FINANCE_CALCULATOR_TOOLS
from worker.tools.finance_tool import FINANCE_SYSTEM_PROMPT, FinanceTool
from worker.tools.finance_tools import (
    FINANCE_TOOLS,
    FinanceToolError,
    cached_json,
    require_env,
)
from worker.tools.registry import _REGISTRY, get_tool, list_tools

_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_loop)


def _run(coro):
    return _loop.run_until_complete(coro)


# --- Main router exposes ONE top-level `finance` tool ---------------------


def test_registry_exposes_only_finance():
    """The main KapexAI registry must expose exactly one finance tool named
    `finance`, and NONE of the 109 underlying calculator/SEC functions."""
    names = {t["name"] for t in list_tools()}
    assert "finance" in names
    assert get_tool("finance") is not None

    underlying = {t.name for t in FINANCE_CALCULATOR_TOOLS}
    underlying |= {t.name for t in EQUITY_CALCULATOR_TOOLS}
    underlying |= {t.name for t in FINANCE_TOOLS}
    assert len(underlying) == 109
    # No underlying function may be a top-level agent tool.
    assert not (set(_REGISTRY) & underlying)


def test_finance_tool_is_a_tool():
    tool = get_tool("finance")
    assert isinstance(tool, FinanceTool)
    assert isinstance(tool, Tool)
    assert tool.name == "finance"
    assert not tool.requires_context


def test_finance_agent_binds_all_underlying_tools():
    """The internal react agent holds the 109 tools (so the LLM can call them),
    but they stay out of the main registry."""
    tool = FinanceTool()
    bound = tool.agent.nodes["tools"].bound
    bound_names = set(bound.tools_by_name)
    assert len(bound_names) == 109


# --- Routing to a finance calculator ---------------------------------------


class _FakeModel(Runnable):
    """Fake chat model that drives the react agent: emits the scripted tool
    calls, then answers once every scripted call has run."""

    def __init__(self, tool_calls: list[dict], answer: str):
        self._tool_calls = tool_calls
        self._answer = answer

    def bind_tools(self, tools, **kwargs):
        self._tools = {t.name: t for t in tools}
        return self

    def invoke(self, input, config=None, **kwargs):
        messages = input["messages"] if isinstance(input, dict) else input
        executed = [m for m in messages if getattr(m, "tool_calls", None)]
        if len(executed) < len(self._tool_calls):
            return AIMessage(content="", tool_calls=[self._tool_calls[len(executed)]])
        return AIMessage(content=self._answer)


def _agent_with(fake_model: _FakeModel):
    from langgraph.prebuilt import create_react_agent

    tool = FinanceTool()
    tool.agent = create_react_agent(
        fake_model,
        [*FINANCE_CALCULATOR_TOOLS, *EQUITY_CALCULATOR_TOOLS, *FINANCE_TOOLS],
    )
    return tool


def test_finance_routes_to_finance_calculator(monkeypatch):
    """A CAGR request routes to the cagr_calculator tool and its result is used."""
    captured = {}

    def fake_cagr(beginning_value, ending_value, years):
        captured["args"] = {"beginning_value": beginning_value, "ending_value": ending_value, "years": years}
        return {"cagr": 0.189, "cagr_percent": 18.9}

    monkeypatch.setattr(
        "worker.tools.finance_calculators.cagr_calculator.func", fake_cagr
    )

    fake = _FakeModel(
        [
            {
                "name": "cagr_calculator",
                "args": {"beginning_value": 1000, "ending_value": 2000, "years": 4},
                "id": "call_cagr",
            }
        ],
        "The CAGR is 18.9%.",
    )
    tool = _agent_with(fake)

    entries = tool.run(
        {
            "session_id": "s",
            "user_input": "What is the CAGR from 1000 to 2000 over 4 years?",
            "messages": [],
        }
    )
    assert entries[0] == {
        "role": "USER",
        "agent": "TOOL",
        "type": "finance_request",
        "content": "What is the CAGR from 1000 to 2000 over 4 years?",
    }
    assert entries[1]["role"] == "ASSISTANT"
    assert entries[1]["agent"] == "TOOL"
    assert entries[1]["type"] == "finance"
    assert captured["args"] == {
        "beginning_value": 1000,
        "ending_value": 2000,
        "years": 4,
    }


def test_finance_routes_to_equity_calculator(monkeypatch):
    """A CAPM request routes to the capm_calculator (equity module)."""
    captured = {}

    def fake_capm(risk_free_rate, beta, expected_market_return, country_risk_premium=0.0):
        captured["args"] = {
            "risk_free_rate": risk_free_rate,
            "beta": beta,
            "expected_market_return": expected_market_return,
        }
        return {"expected_return": 0.114, "market_risk_premium": 0.07}

    monkeypatch.setattr(
        "worker.tools.equity_calculators.capm_calculator.func", fake_capm
    )

    fake = _FakeModel(
        [
            {
                "name": "capm_calculator",
                "args": {"risk_free_rate": 0.03, "beta": 1.2, "expected_market_return": 0.10},
                "id": "call_capm",
            }
        ],
        "The expected return is 11.4%.",
    )
    tool = _agent_with(fake)

    entries = tool.run(
        {
            "session_id": "s",
            "user_input": "CAPM for beta 1.2, risk free 3%, market return 10%?",
            "messages": [],
        }
    )
    assert entries[1]["type"] == "finance"
    assert captured["args"] == {
        "risk_free_rate": 0.03,
        "beta": 1.2,
        "expected_market_return": 0.10,
    }


def test_finance_routes_to_sec_tool(monkeypatch):
    """A public-company request routes to the SEC lookup tool."""
    captured = {}

    def fake_lookup(ticker):
        captured["ticker"] = ticker
        return {"ticker": "AAPL", "cik": "0000320193", "name": "Apple Inc."}

    monkeypatch.setattr(
        "worker.tools.finance_tools.sec_company_lookup.func", fake_lookup
    )

    fake = _FakeModel(
        [{"name": "sec_company_lookup", "args": {"ticker": "AAPL"}, "id": "call_sec"}],
        "Apple Inc. has CIK 0000320193.",
    )
    tool = _agent_with(fake)

    entries = tool.run(
        {
            "session_id": "s",
            "user_input": "What is Apple's SEC CIK?",
            "messages": [],
        }
    )
    assert entries[1]["type"] == "finance"
    assert captured["ticker"] == "AAPL"


def test_finance_can_use_multiple_tools():
    """A request needing several operations uses several underlying tools in
    sequence (beta, then CAPM on top of it)."""
    fake = _FakeModel(
        [
            {
                "name": "beta_stock_calculator",
                "args": {
                    "stock_returns": [0.05, 0.02, -0.01, 0.03],
                    "market_returns": [0.03, 0.01, 0.0, 0.02],
                },
                "id": "call_beta",
            },
            {
                "name": "capm_calculator",
                "args": {"risk_free_rate": 0.03, "beta": 1.1, "expected_market_return": 0.10},
                "id": "call_capm",
            },
        ],
        "Beta is 1.1 and the CAPM expected return is 10.7%.",
    )
    tool = _agent_with(fake)

    entries = tool.run(
        {
            "session_id": "s",
            "user_input": "Estimate the beta of these returns then the CAPM cost of equity.",
            "messages": [],
        }
    )
    assert entries[1]["type"] == "finance"
    assert "Beta is 1.1" in entries[1]["content"]


def test_finance_system_prompt_prefers_tools():
    assert "KapexAI's finance specialist" in FINANCE_SYSTEM_PROMPT
    assert "ALWAYS prefer calling the right tool" in FINANCE_SYSTEM_PROMPT
    assert "SEVERAL tools" in FINANCE_SYSTEM_PROMPT


# --- Invalid requests / error handling -------------------------------------


def test_invalid_calculator_args_raise_value_error():
    from worker.tools.finance_calculators import cagr_calculator

    with pytest.raises(ValueError):
        cagr_calculator.invoke(
            {"beginning_value": -1, "ending_value": 2, "years": 1}
        )


def test_sec_missing_env_returns_friendly_error(monkeypatch):
    """Without SEC_USER_AGENT, the SEC tool returns a clear error instead of
    raising or leaking config internals."""
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    result = __import__(
        "worker.tools.finance_tools", fromlist=["sec_company_lookup"]
    ).sec_company_lookup.invoke({"ticker": "AAPL"})
    assert "error" in result
    assert "SEC_USER_AGENT" in result["error"]


def test_require_env_raises_friendly_error(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    with pytest.raises(FinanceToolError):
        require_env("SEC_USER_AGENT")


def test_cached_json_surfaces_http_errors(monkeypatch):
    import httpx

    def fake_request(*args, **kwargs):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr("worker.tools.finance_tools.httpx.request", fake_request)
    with pytest.raises(FinanceToolError):
        cached_json("GET", "https://data.sec.gov/x", headers={}, ttl_seconds=0)


def test_finance_run_handles_agent_failure_gracefully():
    """If the internal agent raises, run() still returns a friendly finance
    message rather than propagating the raw exception."""

    class BoomAgent:
        def invoke(self, payload):
            raise RuntimeError("agent exploded")

    tool = FinanceTool()
    tool.agent = BoomAgent()
    entries = tool.run(
        {"session_id": "s", "user_input": "do a calc", "messages": []}
    )
    assert entries[0]["type"] == "finance_request"
    assert entries[1]["type"] == "finance"
    assert "couldn't complete" in entries[1]["content"].lower()
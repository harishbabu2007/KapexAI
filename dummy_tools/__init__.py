"""Reusable analysis and reporting tools."""

from kapexai.tools.astrology_tools import FREE_ASTROLOGY_API_TOOLS
from kapexai.tools.analysis import run_all
from kapexai.tools.charts import (
    create_bar_chart,
    create_candlestick_chart,
    create_donut_chart,
    create_line_chart,
    create_waterfall_chart,
)
from kapexai.tools.presentation import build_ppt
from kapexai.tools.debt_calculators import DEBT_CALCULATOR_TOOLS
from kapexai.tools.debt_management_calculators import (
    DEBT_MANAGEMENT_CALCULATOR_TOOLS,
)
from kapexai.tools.equity_calculators import EQUITY_CALCULATOR_TOOLS
from kapexai.tools.finance_calculators import FINANCE_CALCULATOR_TOOLS
from kapexai.tools.indian_finance_calculators import (
    INDIAN_FINANCE_CALCULATOR_TOOLS,
)
from kapexai.tools.macroeconomics_calculators import (
    MACROECONOMICS_CALCULATOR_TOOLS,
)
from kapexai.tools.microeconomics_calculators import (
    MICROECONOMICS_CALCULATOR_TOOLS,
)
from kapexai.tools.personal_finance_calculators import (
    PERSONAL_FINANCE_CALCULATOR_TOOLS,
)
from kapexai.tools.real_estate_calculators import REAL_ESTATE_CALCULATOR_TOOLS
from kapexai.tools.retirement_calculators import RETIREMENT_CALCULATOR_TOOLS
from kapexai.tools.registry import (
    get_tool,
    get_tools_for_agent,
    list_tool_metadata,
)
from kapexai.tools.runtime import (
    InMemoryTTLCache,
    RedisToolCache,
    configure_tool_cache,
)
from kapexai.tools.tax_salary_calculators import TAX_SALARY_CALCULATOR_TOOLS
from kapexai.tools.sales_calculators import SALES_CALCULATOR_TOOLS

__all__ = [
    "build_ppt",
    "create_bar_chart",
    "create_candlestick_chart",
    "create_donut_chart",
    "create_line_chart",
    "create_waterfall_chart",
    "configure_tool_cache",
    "DEBT_CALCULATOR_TOOLS",
    "DEBT_MANAGEMENT_CALCULATOR_TOOLS",
    "EQUITY_CALCULATOR_TOOLS",
    "FINANCE_CALCULATOR_TOOLS",
    "FREE_ASTROLOGY_API_TOOLS",
    "INDIAN_FINANCE_CALCULATOR_TOOLS",
    "get_tool",
    "get_tools_for_agent",
    "InMemoryTTLCache",
    "list_tool_metadata",
    "MACROECONOMICS_CALCULATOR_TOOLS",
    "MICROECONOMICS_CALCULATOR_TOOLS",
    "PERSONAL_FINANCE_CALCULATOR_TOOLS",
    "REAL_ESTATE_CALCULATOR_TOOLS",
    "RETIREMENT_CALCULATOR_TOOLS",
    "RedisToolCache",
    "run_all",
    "SALES_CALCULATOR_TOOLS",
    "TAX_SALARY_CALCULATOR_TOOLS",
]

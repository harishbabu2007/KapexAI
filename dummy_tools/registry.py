"""Curated LangChain tool registry for each KapexAI specialist."""

from dataclasses import dataclass
from typing import Iterable

from langchain_core.tools import BaseTool

from kapexai.tools.astrology_tools import FREE_ASTROLOGY_API_TOOLS
from kapexai.tools.artifact_tools import (
    create_finance_chart,
    create_presentation_from_outline,
    render_mermaid_svg,
    validate_mermaid,
)
from kapexai.tools.consulting import (
    kpi_tree_builder,
    market_size_model,
    raci_validator,
    risk_register,
    scenario_projection,
    weighted_decision_matrix,
)
from kapexai.tools.economics import (
    bls_time_series,
    exchange_rate_series,
    world_bank_country_profile,
    world_bank_indicator,
)
from kapexai.tools.debt_calculators import DEBT_CALCULATOR_TOOLS
from kapexai.tools.debt_management_calculators import (
    DEBT_MANAGEMENT_CALCULATOR_TOOLS,
)
from kapexai.tools.equity_calculators import EQUITY_CALCULATOR_TOOLS
from kapexai.tools.finance_tools import (
    calculate_financial_ratios,
    discounted_cash_flow,
    investment_return_metrics,
    sec_company_facts,
    sec_company_lookup,
    sec_company_submissions,
)
from kapexai.tools.finance_calculators import FINANCE_CALCULATOR_TOOLS
from kapexai.tools.foresight import (
    future_signpost_matrix,
    jpl_horizons_ephemeris,
)
from kapexai.tools.legal_tools import (
    courtlistener_case_search,
    federal_register_search,
    legal_issue_register,
)
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
from kapexai.tools.research import (
    crossref_research_search,
    gdelt_news_search,
    openalex_research_search,
    wikipedia_search,
)
from kapexai.tools.tax_salary_calculators import TAX_SALARY_CALCULATOR_TOOLS
from kapexai.tools.sales_calculators import SALES_CALCULATOR_TOOLS


@dataclass(frozen=True)
class ToolDefinition:
    tool: BaseTool
    agents: tuple[str, ...]
    category: str
    source: str
    free_service: bool = True
    required_env: tuple[str, ...] = ()

    def metadata(self) -> dict:
        return {
            "name": self.tool.name,
            "description": self.tool.description,
            "agents": list(self.agents),
            "category": self.category,
            "source": self.source,
            "free_service": self.free_service,
            "required_env": list(self.required_env),
            "input_schema": self.tool.args_schema.model_json_schema()
            if self.tool.args_schema
            else {},
        }


CORE_DEFINITIONS = (
    ToolDefinition(
        gdelt_news_search,
        ("market_analysis", "economist", "business_strategy", "legal_advisor"),
        "research",
        "GDELT DOC 2.0",
    ),
    ToolDefinition(
        crossref_research_search,
        ("market_analysis", "economist", "business_strategy", "legal_advisor"),
        "research",
        "Crossref REST API",
    ),
    ToolDefinition(
        openalex_research_search,
        ("market_analysis",),
        "research",
        "OpenAlex API",
        required_env=("OPENALEX_API_KEY",),
    ),
    ToolDefinition(
        wikipedia_search,
        ("market_analysis",),
        "research",
        "Wikimedia MediaWiki API",
    ),
    ToolDefinition(
        world_bank_indicator,
        ("market_analysis", "economist", "business_strategy"),
        "economics",
        "World Bank Indicators API",
    ),
    ToolDefinition(
        world_bank_country_profile,
        ("market_analysis", "economist", "legal_advisor"),
        "economics",
        "World Bank Indicators API",
    ),
    ToolDefinition(
        bls_time_series,
        ("market_analysis", "economist", "business_management"),
        "economics",
        "U.S. Bureau of Labor Statistics Public Data API",
    ),
    ToolDefinition(
        exchange_rate_series,
        ("economist", "financial_accounting_asset", "business_strategy"),
        "finance",
        "Frankfurter API",
    ),
    ToolDefinition(
        sec_company_lookup,
        ("market_analysis", "financial_accounting_asset", "legal_advisor"),
        "finance",
        "SEC EDGAR",
        required_env=("SEC_USER_AGENT",),
    ),
    ToolDefinition(
        sec_company_submissions,
        ("market_analysis", "financial_accounting_asset", "legal_advisor"),
        "finance",
        "SEC EDGAR",
        required_env=("SEC_USER_AGENT",),
    ),
    ToolDefinition(
        sec_company_facts,
        ("financial_accounting_asset",),
        "finance",
        "SEC EDGAR XBRL API",
        required_env=("SEC_USER_AGENT",),
    ),
    ToolDefinition(
        calculate_financial_ratios,
        ("financial_accounting_asset", "business_management"),
        "analysis",
        "Local deterministic model",
    ),
    ToolDefinition(
        discounted_cash_flow,
        ("financial_accounting_asset", "business_strategy"),
        "analysis",
        "Local deterministic model",
    ),
    ToolDefinition(
        investment_return_metrics,
        ("financial_accounting_asset",),
        "analysis",
        "Local deterministic model",
    ),
    ToolDefinition(
        market_size_model,
        ("market_analysis", "business_strategy"),
        "analysis",
        "Local deterministic model",
    ),
    ToolDefinition(
        weighted_decision_matrix,
        ("orchestrator", "business_management", "business_strategy"),
        "analysis",
        "Local deterministic model",
    ),
    ToolDefinition(
        scenario_projection,
        ("economist", "business_strategy", "financial_accounting_asset"),
        "analysis",
        "Local deterministic model",
    ),
    ToolDefinition(
        risk_register,
        (
            "orchestrator",
            "business_management",
            "business_strategy",
            "financial_accounting_asset",
        ),
        "analysis",
        "Local deterministic model",
    ),
    ToolDefinition(
        raci_validator,
        ("business_management",),
        "operations",
        "Local deterministic model",
    ),
    ToolDefinition(
        kpi_tree_builder,
        ("business_management",),
        "operations",
        "Local deterministic model",
    ),
    ToolDefinition(
        federal_register_search,
        ("legal_advisor", "economist", "market_analysis"),
        "legal",
        "FederalRegister.gov API",
    ),
    ToolDefinition(
        courtlistener_case_search,
        ("legal_advisor",),
        "legal",
        "CourtListener REST API",
        required_env=("COURTLISTENER_API_TOKEN",),
    ),
    ToolDefinition(
        legal_issue_register,
        ("legal_advisor", "orchestrator"),
        "legal",
        "Local deterministic model",
    ),
    ToolDefinition(
        create_finance_chart,
        ("presentation_designer", "financial_accounting_asset"),
        "artifact",
        "Local Matplotlib renderer",
    ),
    ToolDefinition(
        create_presentation_from_outline,
        ("presentation_designer",),
        "artifact",
        "Local python-pptx renderer",
    ),
    ToolDefinition(
        validate_mermaid,
        ("mermaid_workflow",),
        "artifact",
        "Local Mermaid validation",
    ),
    ToolDefinition(
        render_mermaid_svg,
        ("mermaid_workflow", "presentation_designer"),
        "artifact",
        "Kroki HTTP API",
    ),
    ToolDefinition(
        future_signpost_matrix,
        ("astrologer_future", "economist", "business_strategy"),
        "foresight",
        "Local deterministic model",
    ),
    ToolDefinition(
        jpl_horizons_ephemeris,
        ("astrologer_future",),
        "foresight",
        "NASA JPL Horizons API",
    ),
)

ECONOMIST_CALCULATORS = {
    "apy_calculator",
    "basis_point_calculator",
    "compound_interest_rate_calculator",
    "discount_rate_calculator",
    "ear_calculator",
    "effective_annual_yield_calculator",
    "effective_interest_rate_calculator",
    "equivalent_rate_aer_calculator",
    "real_rate_of_return_calculator",
}

MANAGEMENT_CALCULATORS = {
    "mva_calculator",
    "nopat_calculator",
    "opportunity_cost_calculator",
    "roce_calculator",
    "roi_calculator",
    "ttm_calculator",
    "week_over_week_calculator",
}

MARKET_CALCULATORS = {
    "annualized_rate_of_return_calculator",
    "appreciation_calculator",
    "cagr_calculator",
    "capital_gains_yield_calculator",
    "holding_period_return_calculator",
    "maximum_drawdown_calculator",
    "moving_average_calculator",
    "percentage_return_calculator",
    "rate_of_return_calculator",
    "value_at_risk_calculator",
}

STRATEGY_CALCULATORS = {
    "dcf_calculator",
    "discount_rate_calculator",
    "expected_return_calculator",
    "expected_utility_calculator",
    "irr_calculator",
    "mirr_calculator",
    "mva_calculator",
    "nopat_calculator",
    "npv_calculator",
    "opportunity_cost_calculator",
    "perpetuity_calculator",
    "present_value_calculator",
    "roce_calculator",
    "roi_calculator",
}

EQUITY_MARKET_CALCULATORS = {
    "beta_stock_calculator",
    "capm_calculator",
    "dividend_calculator",
    "dividend_yield_calculator",
    "earnings_per_share_calculator",
    "earnings_per_share_growth_calculator",
    "enterprise_value_calculator",
    "ev_to_sales_calculator",
    "free_float_calculator",
    "market_capitalization_calculator",
    "peg_ratio_calculator",
    "portfolio_beta_calculator",
    "price_to_book_ratio_calculator",
    "price_to_cash_flow_ratio_calculator",
    "price_to_earnings_ratio_calculator",
    "price_to_sales_ratio_calculator",
    "stock_calculator",
    "stock_average_calculator",
    "stock_split_calculator",
}

EQUITY_MANAGEMENT_CALCULATORS = {
    "dividend_payout_ratio_calculator",
    "dupont_analysis_calculator",
    "economic_value_added_calculator",
    "operating_cash_flow_ratio_calculator",
    "retention_ratio_calculator",
    "return_on_assets_calculator",
    "return_on_equity_calculator",
    "return_on_sales_calculator",
    "roic_calculator",
    "sustainable_growth_rate_calculator",
}

EQUITY_STRATEGY_CALCULATORS = {
    "capm_calculator",
    "carried_interest_calculator",
    "cost_of_capital_calculator",
    "cost_of_equity_calculator",
    "dividend_discount_model_calculator",
    "ebitda_multiple_calculator",
    "economic_value_added_calculator",
    "enterprise_value_calculator",
    "ev_to_sales_calculator",
    "graham_number_calculator",
    "intrinsic_value_calculator",
    "margin_of_safety_calculator",
    "nav_calculator",
    "residual_income_calculator",
    "roic_calculator",
    "sustainable_growth_rate_calculator",
    "unlevered_beta_calculator",
    "wacc_calculator",
}

DEBT_MARKET_CALCULATORS = {
    "bond_convexity_calculator",
    "bond_current_yield_calculator",
    "bond_equivalent_yield_calculator",
    "bond_price_calculator",
    "bond_yield_calculator",
    "bond_ytm_calculator",
    "coupon_payment_calculator",
    "coupon_rate_calculator",
    "credit_spread_calculator",
    "effective_duration_calculator",
    "yield_to_maturity_calculator",
}

DEBT_ECONOMIST_CALCULATORS = {
    "after_tax_cost_of_debt_calculator",
    "bond_equivalent_yield_calculator",
    "credit_spread_calculator",
    "tax_equivalent_yield_calculator",
}

DEBT_MANAGEMENT_CALCULATORS = {
    "altman_z_score_calculator",
    "debt_service_coverage_ratio_calculator",
    "debt_to_asset_ratio_calculator",
    "debt_to_capital_ratio_calculator",
    "debt_to_equity_calculator",
    "defensive_interval_ratio_calculator",
    "interest_coverage_ratio_calculator",
    "lgd_calculator",
    "quick_ratio_calculator",
    "times_interest_earned_ratio_calculator",
}

DEBT_STRATEGY_CALCULATORS = {
    "after_tax_cost_of_debt_calculator",
    "altman_z_score_calculator",
    "credit_spread_calculator",
    "debt_service_coverage_ratio_calculator",
    "debt_to_capital_ratio_calculator",
    "lgd_calculator",
}

TAX_MANAGEMENT_CALCULATORS = {
    "twelve_hour_shift_pay_calculator",
    "annual_income_calculator",
    "billable_hours_calculator",
    "bill_rate_calculator",
    "future_salary_calculator",
    "gross_to_net_calculator",
    "hourly_to_salary_calculator",
    "net_to_gross_calculator",
    "overtime_calculator",
    "pay_raise_calculator",
    "prorated_salary_calculator",
    "salary_calculator",
    "salary_inflation_calculator",
    "salary_to_hourly_calculator",
    "time_and_a_half_calculator",
}

TAX_ECONOMIST_CALCULATORS = {
    "adjusted_gross_income_calculator",
    "amt_calculator",
    "biden_tax_plan_calculator",
    "build_back_better_calculator",
    "fica_tax_calculator",
    "gst_calculator",
    "gst_qst_canada_calculator",
    "modified_adjusted_gross_income_calculator",
    "sales_tax_calculator",
    "state_tax_calculator",
    "tax_bracket_calculator",
    "trump_taxes_vs_your_taxes_calculator",
    "vat_calculator",
}

TAX_LEGAL_CALCULATORS = {
    "alabama_tax_calculator",
    "amt_calculator",
    "australia_income_tax_cuts_2020_21_calculator",
    "biden_tax_plan_calculator",
    "build_back_better_calculator",
    "california_stimulus_check_ii_calculator",
    "california_tax_calculator",
    "child_tax_credit_calculator",
    "fica_tax_calculator",
    "illinois_tax_calculator",
    "new_york_tax_calculator",
    "philippines_income_tax_calculator",
    "rmd_calculator",
    "state_tax_calculator",
    "tax_bracket_calculator",
    "texas_tax_calculator",
    "trump_taxes_vs_your_taxes_calculator",
}

REAL_ESTATE_MARKET_CALCULATORS = {
    "adr_calculator",
    "arv_calculator",
    "cap_rate_calculator",
    "gross_rent_multiplier_calculator",
    "net_effective_rent_calculator",
    "net_operating_income_calculator",
    "occupancy_rate_calculator",
    "price_per_square_foot_calculator",
    "price_per_square_meter_calculator",
    "home_value_calculator",
    "ltv_calculator",
    "real_estate_commission_calculator",
    "rent_calculator",
    "rental_property_calculator",
    "rent_increase_calculator",
    "rent_or_buy_calculator",
    "what_to_offer_on_house_calculator",
}

REAL_ESTATE_MANAGEMENT_CALCULATORS = {
    "adr_calculator",
    "affo_calculator",
    "commercial_lease_calculator",
    "net_effective_rent_calculator",
    "net_operating_income_calculator",
    "occupancy_rate_calculator",
    "prorated_rent_calculator",
    "real_estate_commission_calculator",
    "rental_commission_calculator",
    "rental_property_calculator",
    "rent_increase_calculator",
}

REAL_ESTATE_STRATEGY_CALCULATORS = {
    "affo_calculator",
    "arv_calculator",
    "cap_rate_calculator",
    "commercial_lease_calculator",
    "gross_rent_multiplier_calculator",
    "mortgage_refinance_calculator",
    "net_operating_income_calculator",
    "home_affordability_calculator",
    "home_value_calculator",
    "ltv_calculator",
    "mortgage_comparison_calculator",
    "rent_or_buy_calculator",
    "rental_property_calculator",
    "true_cost_real_estate_commission_calculator",
}

PERSONAL_MANAGEMENT_CALCULATORS = {
    "bank_reconciliation_calculator",
    "budget_calculator",
    "cell_phone_plan_calculator",
    "emergency_fund_calculator",
    "fifty_thirty_twenty_rule_calculator",
    "net_worth_calculator",
    "seventy_twenty_ten_rule_money_calculator",
    "subscription_waste_calculator",
    "unpaid_work_calculator",
    "wedding_budget_calculator",
}

PERSONAL_ECONOMIST_CALCULATORS = {
    "apc_calculator",
    "lifetime_earnings_calculator",
    "pakistan_income_tax_calculator",
    "quiz_us_income_percentile_calculator",
    "salary_inflation_calculator",
    "us_income_percentile_calculator",
}

PERSONAL_LEGAL_CALCULATORS = {
    "pakistan_income_tax_calculator",
    "second_stimulus_900_billion_bill_calculator",
    "second_stimulus_cash_act_calculator",
    "second_stimulus_heals_act_calculator",
    "second_stimulus_heroes_act_calculator",
    "stimulus_caaf_vs_heals_vs_heroes_calculator",
    "stimulus_check_40k_cap_calculator",
    "stimulus_check_calculator",
    "third_stimulus_american_rescue_plan_calculator",
    "unemployment_benefit_cares_act_calculator",
    "unemployment_benefit_heals_vs_heroes_calculator",
    "unemployment_benefit_lwa_calculator",
    "zakat_calculator",
}

DEBT_MANAGEMENT_BUSINESS_CALCULATORS = {
    "apr_calculator",
    "blended_rate_calculator",
    "debt_calculator",
    "debt_avalanche_calculator",
    "debt_consolidation_calculator",
    "debt_payoff_calculator",
    "debt_snowball_calculator",
    "debt_to_income_ratio_calculator",
    "finance_charge_calculator",
    "loan_comparison_calculator",
    "refinance_calculator",
    "refinance_break_even_calculator",
}

DEBT_MANAGEMENT_STRATEGY_CALCULATORS = {
    "blended_rate_calculator",
    "cash_out_refinance_calculator",
    "debt_consolidation_calculator",
    "loan_comparison_calculator",
    "refinance_calculator",
    "refinance_break_even_calculator",
}

DEBT_MANAGEMENT_LEGAL_CALCULATORS = {
    "eidl_emergency_advance_calculator",
    "paycheck_protection_program_loan_calculator",
    "post_judgment_interest_calculator",
    "student_loan_forgiveness_calculator",
    "student_loan_repayment_covid19_calculator",
}


def _calculator_agents(tool_name: str) -> tuple[str, ...]:
    agents = ["financial_accounting_asset"]
    if tool_name in ECONOMIST_CALCULATORS:
        agents.append("economist")
    if tool_name in MANAGEMENT_CALCULATORS:
        agents.append("business_management")
    if tool_name in MARKET_CALCULATORS:
        agents.append("market_analysis")
    if tool_name in STRATEGY_CALCULATORS:
        agents.append("business_strategy")
    return tuple(agents)


def _equity_calculator_agents(tool_name: str) -> tuple[str, ...]:
    agents = ["financial_accounting_asset"]
    if tool_name in EQUITY_MARKET_CALCULATORS:
        agents.append("market_analysis")
    if tool_name in EQUITY_MANAGEMENT_CALCULATORS:
        agents.append("business_management")
    if tool_name in EQUITY_STRATEGY_CALCULATORS:
        agents.append("business_strategy")
    return tuple(agents)


def _debt_calculator_agents(tool_name: str) -> tuple[str, ...]:
    agents = ["financial_accounting_asset"]
    if tool_name in DEBT_MARKET_CALCULATORS:
        agents.append("market_analysis")
    if tool_name in DEBT_ECONOMIST_CALCULATORS:
        agents.append("economist")
    if tool_name in DEBT_MANAGEMENT_CALCULATORS:
        agents.append("business_management")
    if tool_name in DEBT_STRATEGY_CALCULATORS:
        agents.append("business_strategy")
    return tuple(agents)


def _tax_calculator_agents(tool_name: str) -> tuple[str, ...]:
    agents = ["financial_accounting_asset"]
    if tool_name in TAX_MANAGEMENT_CALCULATORS:
        agents.append("business_management")
    if tool_name in TAX_ECONOMIST_CALCULATORS:
        agents.append("economist")
    if tool_name in TAX_LEGAL_CALCULATORS:
        agents.append("legal_advisor")
    return tuple(agents)


def _real_estate_calculator_agents(tool_name: str) -> tuple[str, ...]:
    agents = ["financial_accounting_asset"]
    if tool_name in REAL_ESTATE_MARKET_CALCULATORS:
        agents.append("market_analysis")
    if tool_name in REAL_ESTATE_MANAGEMENT_CALCULATORS:
        agents.append("business_management")
    if tool_name in REAL_ESTATE_STRATEGY_CALCULATORS:
        agents.append("business_strategy")
    return tuple(agents)


def _personal_finance_calculator_agents(tool_name: str) -> tuple[str, ...]:
    agents = ["financial_accounting_asset"]
    if tool_name in PERSONAL_MANAGEMENT_CALCULATORS:
        agents.append("business_management")
    if tool_name in PERSONAL_ECONOMIST_CALCULATORS:
        agents.append("economist")
    if tool_name in PERSONAL_LEGAL_CALCULATORS:
        agents.append("legal_advisor")
    return tuple(agents)


def _debt_management_calculator_agents(tool_name: str) -> tuple[str, ...]:
    agents = ["financial_accounting_asset"]
    if tool_name in DEBT_MANAGEMENT_BUSINESS_CALCULATORS:
        agents.append("business_management")
    if tool_name in DEBT_MANAGEMENT_STRATEGY_CALCULATORS:
        agents.append("business_strategy")
    if tool_name in DEBT_MANAGEMENT_LEGAL_CALCULATORS:
        agents.append("legal_advisor")
    return tuple(agents)


CALCULATOR_DEFINITIONS = tuple(
    ToolDefinition(
        calculator,
        _calculator_agents(calculator.name),
        "finance_calculator",
        "Local deterministic standard finance formula",
    )
    for calculator in FINANCE_CALCULATOR_TOOLS
)

EQUITY_CALCULATOR_DEFINITIONS = tuple(
    ToolDefinition(
        calculator,
        _equity_calculator_agents(calculator.name),
        "equity_calculator",
        "Local deterministic equity finance formula",
    )
    for calculator in EQUITY_CALCULATOR_TOOLS
)

DEBT_CALCULATOR_DEFINITIONS = tuple(
    ToolDefinition(
        calculator,
        _debt_calculator_agents(calculator.name),
        "debt_calculator",
        "Local deterministic debt and fixed-income formula",
    )
    for calculator in DEBT_CALCULATOR_TOOLS
)

TAX_SALARY_CALCULATOR_DEFINITIONS = tuple(
    ToolDefinition(
        calculator,
        _tax_calculator_agents(calculator.name),
        "tax_salary_calculator",
        "Local deterministic tax, payroll, or salary formula",
    )
    for calculator in TAX_SALARY_CALCULATOR_TOOLS
)

REAL_ESTATE_CALCULATOR_DEFINITIONS = tuple(
    ToolDefinition(
        calculator,
        _real_estate_calculator_agents(calculator.name),
        "real_estate_calculator",
        "Local deterministic mortgage or real-estate formula",
    )
    for calculator in REAL_ESTATE_CALCULATOR_TOOLS
)

PERSONAL_FINANCE_CALCULATOR_DEFINITIONS = tuple(
    ToolDefinition(
        calculator,
        _personal_finance_calculator_agents(calculator.name),
        "personal_finance_calculator",
        "Local deterministic personal-finance formula",
    )
    for calculator in PERSONAL_FINANCE_CALCULATOR_TOOLS
)

DEBT_MANAGEMENT_CALCULATOR_DEFINITIONS = tuple(
    ToolDefinition(
        calculator,
        _debt_management_calculator_agents(calculator.name),
        "debt_management_calculator",
        "Local deterministic consumer debt-management formula",
    )
    for calculator in DEBT_MANAGEMENT_CALCULATOR_TOOLS
)

RETIREMENT_CALCULATOR_DEFINITIONS = tuple(
    ToolDefinition(
        calculator,
        ("financial_accounting_asset", "business_strategy"),
        "retirement_calculator",
        "Local deterministic retirement or annuity formula",
    )
    for calculator in RETIREMENT_CALCULATOR_TOOLS
)

SALES_CALCULATOR_DEFINITIONS = tuple(
    ToolDefinition(
        calculator,
        (
            "financial_accounting_asset",
            "market_analysis",
            "business_management",
            "business_strategy",
        ),
        "sales_calculator",
        "Local deterministic sales, margin, pricing, or discount formula",
    )
    for calculator in SALES_CALCULATOR_TOOLS
)

MICROECONOMICS_CALCULATOR_DEFINITIONS = tuple(
    ToolDefinition(
        calculator,
        (
            "financial_accounting_asset",
            "economist",
            "business_management",
            "business_strategy",
        ),
        "microeconomics_calculator",
        "Local deterministic microeconomics or operating formula",
    )
    for calculator in MICROECONOMICS_CALCULATOR_TOOLS
)

MACROECONOMICS_CALCULATOR_DEFINITIONS = tuple(
    ToolDefinition(
        calculator,
        (
            "economist",
            "business_strategy",
            "market_analysis",
            "financial_accounting_asset",
        ),
        "macroeconomics_calculator",
        "Local deterministic macroeconomics or banking-liquidity formula",
    )
    for calculator in MACROECONOMICS_CALCULATOR_TOOLS
)

INDIAN_POLICY_CALCULATORS = {
    "atal_pension_yojana_calculator",
    "elss_calculator",
    "epf_calculator",
    "hra_exemption_calculator",
    "nps_india_calculator",
    "post_office_monthly_income_scheme_calculator",
    "ppf_calculator",
    "sukanya_samriddhi_yojana_calculator",
    "tds_interest_calculator",
}

INDIAN_STRATEGY_CALCULATORS = {
    "atal_pension_yojana_calculator",
    "elss_calculator",
    "epf_calculator",
    "lumpsum_calculator",
    "nps_india_calculator",
    "ppf_calculator",
    "sip_calculator",
    "sip_plus_lumpsum_calculator",
    "sukanya_samriddhi_yojana_calculator",
    "systematic_withdrawal_plan_calculator",
}


def _indian_calculator_agents(tool_name: str) -> tuple[str, ...]:
    agents = ["financial_accounting_asset"]
    if tool_name in INDIAN_POLICY_CALCULATORS:
        agents.extend(("economist", "legal_advisor"))
    if tool_name in INDIAN_STRATEGY_CALCULATORS:
        agents.append("business_strategy")
    return tuple(dict.fromkeys(agents))


INDIAN_FINANCE_CALCULATOR_DEFINITIONS = tuple(
    ToolDefinition(
        calculator,
        _indian_calculator_agents(calculator.name),
        "indian_finance_calculator",
        "Local deterministic Indian finance or policy-sensitive formula",
    )
    for calculator in INDIAN_FINANCE_CALCULATOR_TOOLS
)

ASTROLOGY_API_DEFINITIONS = tuple(
    ToolDefinition(
        astrology_tool,
        ("astrologer_future",),
        "astrology",
        "Free Astrology API",
        required_env=("FREE_ASTROLOGY_API_KEY",),
    )
    for astrology_tool in FREE_ASTROLOGY_API_TOOLS
)

DEFINITIONS = (
    *CORE_DEFINITIONS,
    *CALCULATOR_DEFINITIONS,
    *EQUITY_CALCULATOR_DEFINITIONS,
    *DEBT_CALCULATOR_DEFINITIONS,
    *TAX_SALARY_CALCULATOR_DEFINITIONS,
    *REAL_ESTATE_CALCULATOR_DEFINITIONS,
    *PERSONAL_FINANCE_CALCULATOR_DEFINITIONS,
    *DEBT_MANAGEMENT_CALCULATOR_DEFINITIONS,
    *RETIREMENT_CALCULATOR_DEFINITIONS,
    *SALES_CALCULATOR_DEFINITIONS,
    *MICROECONOMICS_CALCULATOR_DEFINITIONS,
    *MACROECONOMICS_CALCULATOR_DEFINITIONS,
    *INDIAN_FINANCE_CALCULATOR_DEFINITIONS,
    *ASTROLOGY_API_DEFINITIONS,
)

TOOL_REGISTRY = {definition.tool.name: definition for definition in DEFINITIONS}


def get_tool_definitions_for_agent(agent_key: str) -> list[ToolDefinition]:
    return [
        definition
        for definition in DEFINITIONS
        if agent_key in definition.agents
    ]


def get_tools_for_agent(agent_key: str) -> list[BaseTool]:
    return [
        definition.tool
        for definition in get_tool_definitions_for_agent(agent_key)
    ]


def list_tool_metadata(agent_key: str | None = None) -> list[dict]:
    definitions: Iterable[ToolDefinition] = (
        get_tool_definitions_for_agent(agent_key)
        if agent_key
        else DEFINITIONS
    )
    return [definition.metadata() for definition in definitions]


def get_tool(name: str) -> BaseTool:
    try:
        return TOOL_REGISTRY[name].tool
    except KeyError as exc:
        raise KeyError(f"Unknown tool: {name}") from exc

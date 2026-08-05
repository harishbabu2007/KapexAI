"""Deterministic debt-investment and fixed-income calculator tools."""

import math

from langchain.tools import tool

from kapexai.tools.finance_calculators import _nonnegative, _positive


def _ratio(numerator: float, denominator: float, name: str) -> float:
    if denominator == 0:
        raise ValueError(f"{name} denominator cannot be zero")
    return numerator / denominator


def _bond_periods(years_to_maturity: float, payments_per_year: int) -> int:
    _positive(years_to_maturity, "years_to_maturity")
    if payments_per_year < 1:
        raise ValueError("payments_per_year must be at least 1")
    periods = years_to_maturity * payments_per_year
    rounded = round(periods)
    if not math.isclose(periods, rounded, abs_tol=1e-9):
        raise ValueError("maturity must produce a whole coupon period")
    return rounded


def _bond_cash_flows(
    face_value: float,
    annual_coupon_rate: float,
    years_to_maturity: float,
    payments_per_year: int,
) -> list[float]:
    _positive(face_value, "face_value")
    periods = _bond_periods(years_to_maturity, payments_per_year)
    coupon = face_value * annual_coupon_rate / payments_per_year
    cash_flows = [coupon] * periods
    cash_flows[-1] += face_value
    return cash_flows


def _bond_price(
    face_value: float,
    annual_coupon_rate: float,
    annual_yield_to_maturity: float,
    years_to_maturity: float,
    payments_per_year: int,
) -> float:
    periodic_yield = annual_yield_to_maturity / payments_per_year
    if periodic_yield <= -1:
        raise ValueError("yield per coupon period must exceed -100%")
    cash_flows = _bond_cash_flows(
        face_value,
        annual_coupon_rate,
        years_to_maturity,
        payments_per_year,
    )
    return sum(
        cash_flow / ((1 + periodic_yield) ** period)
        for period, cash_flow in enumerate(cash_flows, start=1)
    )


def _solve_ytm(
    market_price: float,
    face_value: float,
    annual_coupon_rate: float,
    years_to_maturity: float,
    payments_per_year: int,
) -> float:
    _positive(market_price, "market_price")
    lower = -0.999 * payments_per_year
    upper = 1.0
    lower_price = _bond_price(
        face_value,
        annual_coupon_rate,
        lower,
        years_to_maturity,
        payments_per_year,
    )
    if lower_price < market_price:
        raise ValueError("market price is outside the supported yield range")
    upper_price = _bond_price(
        face_value,
        annual_coupon_rate,
        upper,
        years_to_maturity,
        payments_per_year,
    )
    while upper_price > market_price and upper < 1000:
        upper = upper * 2 + 0.1
        upper_price = _bond_price(
            face_value,
            annual_coupon_rate,
            upper,
            years_to_maturity,
            payments_per_year,
        )
    if upper_price > market_price:
        raise ValueError("could not bracket a yield to maturity")
    for _ in range(200):
        midpoint = (lower + upper) / 2
        price = _bond_price(
            face_value,
            annual_coupon_rate,
            midpoint,
            years_to_maturity,
            payments_per_year,
        )
        if abs(price - market_price) < 1e-10:
            return midpoint
        if price > market_price:
            lower = midpoint
        else:
            upper = midpoint
    return (lower + upper) / 2


def _ytm_result(
    market_price: float,
    face_value: float,
    annual_coupon_rate: float,
    years_to_maturity: float,
    payments_per_year: int,
) -> dict:
    ytm = _solve_ytm(
        market_price,
        face_value,
        annual_coupon_rate,
        years_to_maturity,
        payments_per_year,
    )
    return {
        "annual_yield_to_maturity": ytm,
        "yield_to_maturity_percent": ytm * 100,
        "recalculated_price": _bond_price(
            face_value,
            annual_coupon_rate,
            ytm,
            years_to_maturity,
            payments_per_year,
        ),
    }


@tool
def after_tax_cost_of_debt_calculator(
    pre_tax_cost_of_debt: float, marginal_tax_rate: float
) -> dict:
    """Calculate tax-adjusted cost of debt."""
    if not 0 <= marginal_tax_rate <= 1:
        raise ValueError("marginal_tax_rate must be between 0 and 1")
    return {
        "after_tax_cost_of_debt": pre_tax_cost_of_debt
        * (1 - marginal_tax_rate),
        "tax_shield_rate": pre_tax_cost_of_debt * marginal_tax_rate,
    }


@tool
def altman_z_score_calculator(
    working_capital: float,
    retained_earnings: float,
    ebit: float,
    market_value_equity: float,
    sales: float,
    total_assets: float,
    total_liabilities: float,
) -> dict:
    """Calculate the original Altman Z-score for public manufacturers."""
    _positive(total_assets, "total_assets")
    _positive(total_liabilities, "total_liabilities")
    score = (
        1.2 * working_capital / total_assets
        + 1.4 * retained_earnings / total_assets
        + 3.3 * ebit / total_assets
        + 0.6 * market_value_equity / total_liabilities
        + sales / total_assets
    )
    if score > 2.99:
        zone = "safe"
    elif score < 1.81:
        zone = "distress"
    else:
        zone = "grey"
    return {
        "altman_z_score": score,
        "zone": zone,
        "model": "Original public manufacturing company model",
    }


@tool
def bond_convexity_calculator(
    face_value: float,
    annual_coupon_rate: float,
    annual_yield_to_maturity: float,
    years_to_maturity: float,
    payments_per_year: int = 2,
) -> dict:
    """Calculate annualized discrete bond convexity."""
    cash_flows = _bond_cash_flows(
        face_value,
        annual_coupon_rate,
        years_to_maturity,
        payments_per_year,
    )
    periodic_yield = annual_yield_to_maturity / payments_per_year
    if periodic_yield <= -1:
        raise ValueError("yield per coupon period must exceed -100%")
    price = sum(
        cash_flow / ((1 + periodic_yield) ** period)
        for period, cash_flow in enumerate(cash_flows, start=1)
    )
    convexity = sum(
        cash_flow
        * period
        * (period + 1)
        / ((1 + periodic_yield) ** (period + 2))
        for period, cash_flow in enumerate(cash_flows, start=1)
    ) / (price * payments_per_year ** 2)
    return {"bond_price": price, "convexity": convexity}


@tool
def bond_current_yield_calculator(
    face_value: float, annual_coupon_rate: float, market_price: float
) -> dict:
    """Calculate current yield as annual coupon divided by market price."""
    _positive(market_price, "market_price")
    annual_coupon = face_value * annual_coupon_rate
    return {
        "annual_coupon": annual_coupon,
        "current_yield": annual_coupon / market_price,
    }


@tool
def bond_equivalent_yield_calculator(
    purchase_price: float,
    redemption_value: float,
    days_to_maturity: int,
) -> dict:
    """Annualize a short-term holding-period yield on a 365-day basis."""
    _positive(purchase_price, "purchase_price")
    _positive(redemption_value, "redemption_value")
    if days_to_maturity < 1:
        raise ValueError("days_to_maturity must be at least 1")
    holding_period_yield = (redemption_value - purchase_price) / purchase_price
    return {
        "holding_period_yield": holding_period_yield,
        "bond_equivalent_yield": holding_period_yield
        * 365
        / days_to_maturity,
    }


@tool
def bond_price_calculator(
    face_value: float,
    annual_coupon_rate: float,
    annual_yield_to_maturity: float,
    years_to_maturity: float,
    payments_per_year: int = 2,
) -> dict:
    """Price a fixed-rate bond from discounted coupon and principal cash flows."""
    price = _bond_price(
        face_value,
        annual_coupon_rate,
        annual_yield_to_maturity,
        years_to_maturity,
        payments_per_year,
    )
    return {
        "bond_price": price,
        "premium_or_discount": price - face_value,
    }


@tool
def bond_yield_calculator(
    face_value: float,
    annual_coupon_rate: float,
    market_price: float,
    years_to_maturity: float,
) -> dict:
    """Estimate annual bond yield with the approximate YTM formula."""
    _positive(market_price, "market_price")
    _positive(years_to_maturity, "years_to_maturity")
    annual_coupon = face_value * annual_coupon_rate
    approximate_yield = (
        annual_coupon + (face_value - market_price) / years_to_maturity
    ) / ((face_value + market_price) / 2)
    return {
        "approximate_annual_yield": approximate_yield,
        "current_yield": annual_coupon / market_price,
    }


@tool
def bond_ytm_calculator(
    market_price: float,
    face_value: float,
    annual_coupon_rate: float,
    years_to_maturity: float,
    payments_per_year: int = 2,
) -> dict:
    """Solve a fixed-rate bond's nominal annual yield to maturity."""
    return _ytm_result(
        market_price,
        face_value,
        annual_coupon_rate,
        years_to_maturity,
        payments_per_year,
    )


@tool
def coupon_payment_calculator(
    face_value: float,
    annual_coupon_rate: float,
    payments_per_year: int = 2,
) -> dict:
    """Calculate annual and per-period coupon payments."""
    _positive(face_value, "face_value")
    if payments_per_year < 1:
        raise ValueError("payments_per_year must be at least 1")
    annual_coupon = face_value * annual_coupon_rate
    return {
        "annual_coupon_payment": annual_coupon,
        "coupon_payment_per_period": annual_coupon / payments_per_year,
    }


@tool
def coupon_rate_calculator(
    annual_coupon_payment: float, face_value: float
) -> dict:
    """Calculate a bond's stated annual coupon rate."""
    _positive(face_value, "face_value")
    return {"annual_coupon_rate": annual_coupon_payment / face_value}


@tool
def credit_spread_calculator(
    risky_bond_yield: float, benchmark_yield: float
) -> dict:
    """Calculate credit spread over a benchmark yield."""
    spread = risky_bond_yield - benchmark_yield
    return {
        "credit_spread": spread,
        "credit_spread_basis_points": spread * 10000,
    }


@tool
def debt_service_coverage_ratio_calculator(
    net_operating_income: float, total_debt_service: float
) -> dict:
    """Calculate debt service coverage ratio."""
    return {
        "debt_service_coverage_ratio": _ratio(
            net_operating_income, total_debt_service, "DSCR"
        )
    }


@tool
def debt_to_asset_ratio_calculator(
    total_debt: float, total_assets: float
) -> dict:
    """Calculate total debt as a proportion of total assets."""
    return {
        "debt_to_asset_ratio": _ratio(
            total_debt, total_assets, "debt to asset ratio"
        )
    }


@tool
def debt_to_capital_ratio_calculator(
    total_debt: float, total_equity: float
) -> dict:
    """Calculate debt as a proportion of debt plus equity capital."""
    return {
        "debt_to_capital_ratio": _ratio(
            total_debt,
            total_debt + total_equity,
            "debt to capital ratio",
        )
    }


@tool
def debt_to_equity_calculator(
    total_debt: float, total_equity: float
) -> dict:
    """Calculate total debt to shareholders' equity."""
    return {
        "debt_to_equity": _ratio(
            total_debt, total_equity, "debt to equity ratio"
        )
    }


@tool
def defensive_interval_ratio_calculator(
    cash_and_equivalents: float,
    marketable_securities: float,
    accounts_receivable: float,
    annual_cash_operating_expenses: float,
) -> dict:
    """Estimate how many days liquid defensive assets can fund operations."""
    _positive(
        annual_cash_operating_expenses,
        "annual_cash_operating_expenses",
    )
    defensive_assets = (
        cash_and_equivalents + marketable_securities + accounts_receivable
    )
    daily_expenses = annual_cash_operating_expenses / 365
    return {
        "defensive_assets": defensive_assets,
        "defensive_interval_days": defensive_assets / daily_expenses,
    }


@tool
def effective_duration_calculator(
    current_price: float,
    price_if_yield_decreases: float,
    price_if_yield_increases: float,
    yield_change: float,
) -> dict:
    """Calculate effective duration from prices under symmetric yield shocks."""
    _positive(current_price, "current_price")
    _nonnegative(price_if_yield_decreases, "price_if_yield_decreases")
    _nonnegative(price_if_yield_increases, "price_if_yield_increases")
    _positive(yield_change, "yield_change")
    duration = (
        price_if_yield_decreases - price_if_yield_increases
    ) / (2 * current_price * yield_change)
    return {"effective_duration": duration}


@tool
def interest_coverage_ratio_calculator(
    ebit: float, interest_expense: float
) -> dict:
    """Calculate EBIT interest coverage."""
    return {
        "interest_coverage_ratio": _ratio(
            ebit, interest_expense, "interest coverage ratio"
        )
    }


@tool
def lgd_calculator(
    exposure_at_default: float, recovered_amount: float
) -> dict:
    """Calculate loss given default from exposure and recoveries."""
    _positive(exposure_at_default, "exposure_at_default")
    if not 0 <= recovered_amount <= exposure_at_default:
        raise ValueError(
            "recovered_amount must be between zero and exposure_at_default"
        )
    recovery_rate = recovered_amount / exposure_at_default
    loss_given_default = 1 - recovery_rate
    return {
        "recovery_rate": recovery_rate,
        "loss_given_default": loss_given_default,
        "loss_amount": exposure_at_default - recovered_amount,
    }


@tool
def quick_ratio_calculator(
    cash_and_equivalents: float,
    marketable_securities: float,
    accounts_receivable: float,
    current_liabilities: float,
) -> dict:
    """Calculate the acid-test quick ratio."""
    quick_assets = (
        cash_and_equivalents + marketable_securities + accounts_receivable
    )
    return {
        "quick_assets": quick_assets,
        "quick_ratio": _ratio(
            quick_assets, current_liabilities, "quick ratio"
        ),
    }


@tool
def tax_equivalent_yield_calculator(
    tax_exempt_yield: float, marginal_tax_rate: float
) -> dict:
    """Convert a tax-exempt yield to its taxable-equivalent yield."""
    if not 0 <= marginal_tax_rate < 1:
        raise ValueError("marginal_tax_rate must be between 0 and 1")
    return {
        "tax_equivalent_yield": tax_exempt_yield
        / (1 - marginal_tax_rate)
    }


@tool
def times_interest_earned_ratio_calculator(
    earnings_before_interest_and_taxes: float,
    interest_expense: float,
) -> dict:
    """Calculate times interest earned."""
    return {
        "times_interest_earned": _ratio(
            earnings_before_interest_and_taxes,
            interest_expense,
            "times interest earned",
        )
    }


@tool
def yield_to_maturity_calculator(
    market_price: float,
    face_value: float,
    annual_coupon_rate: float,
    years_to_maturity: float,
    payments_per_year: int = 2,
) -> dict:
    """Solve nominal annual yield to maturity from a bond's market price."""
    return _ytm_result(
        market_price,
        face_value,
        annual_coupon_rate,
        years_to_maturity,
        payments_per_year,
    )


DEBT_CALCULATOR_TOOLS = (
    after_tax_cost_of_debt_calculator,
    altman_z_score_calculator,
    bond_convexity_calculator,
    bond_current_yield_calculator,
    bond_equivalent_yield_calculator,
    bond_price_calculator,
    bond_yield_calculator,
    bond_ytm_calculator,
    coupon_payment_calculator,
    coupon_rate_calculator,
    credit_spread_calculator,
    debt_service_coverage_ratio_calculator,
    debt_to_asset_ratio_calculator,
    debt_to_capital_ratio_calculator,
    debt_to_equity_calculator,
    defensive_interval_ratio_calculator,
    effective_duration_calculator,
    interest_coverage_ratio_calculator,
    lgd_calculator,
    quick_ratio_calculator,
    tax_equivalent_yield_calculator,
    times_interest_earned_ratio_calculator,
    yield_to_maturity_calculator,
)

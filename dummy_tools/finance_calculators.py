"""Deterministic LangChain tools for common finance calculations."""

import math
from statistics import NormalDist, mean, pstdev
from typing import Literal

from langchain.tools import tool


def _positive(value: float, name: str) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")


def _nonnegative(value: float, name: str) -> None:
    if value < 0:
        raise ValueError(f"{name} must be zero or greater")


def _period_count(years: float, periods_per_year: int) -> int:
    _positive(years, "years")
    if periods_per_year < 1:
        raise ValueError("periods_per_year must be at least 1")
    periods = years * periods_per_year
    rounded = round(periods)
    if not math.isclose(periods, rounded, rel_tol=0, abs_tol=1e-9):
        raise ValueError("years must produce a whole number of periods")
    return rounded


def _future_value(
    principal: float,
    annual_rate: float,
    years: float,
    compounds_per_year: int,
    periodic_contribution: float = 0.0,
    contribution_at_beginning: bool = False,
) -> float:
    periods = _period_count(years, compounds_per_year)
    periodic_rate = annual_rate / compounds_per_year
    if periodic_rate <= -1:
        raise ValueError("rate per compounding period must exceed -100%")
    growth = (1 + periodic_rate) ** periods
    if periodic_rate == 0:
        contribution_value = periodic_contribution * periods
    else:
        contribution_value = (
            periodic_contribution * (growth - 1) / periodic_rate
        )
        if contribution_at_beginning:
            contribution_value *= 1 + periodic_rate
    return principal * growth + contribution_value


def _present_value(
    future_value: float,
    annual_rate: float,
    years: float,
    compounds_per_year: int,
) -> float:
    periods = _period_count(years, compounds_per_year)
    periodic_rate = annual_rate / compounds_per_year
    if periodic_rate <= -1:
        raise ValueError("rate per compounding period must exceed -100%")
    return future_value / ((1 + periodic_rate) ** periods)


def _effective_annual_rate(
    nominal_annual_rate: float, compounds_per_year: int
) -> float:
    if compounds_per_year < 1:
        raise ValueError("compounds_per_year must be at least 1")
    periodic_rate = nominal_annual_rate / compounds_per_year
    if periodic_rate <= -1:
        raise ValueError("rate per compounding period must exceed -100%")
    return (1 + periodic_rate) ** compounds_per_year - 1


def _compound_rates(
    principal: float,
    ending_value: float,
    years: float,
    compounds_per_year: int,
) -> dict:
    _positive(principal, "principal")
    _positive(ending_value, "ending_value")
    periods = _period_count(years, compounds_per_year)
    periodic_rate = (ending_value / principal) ** (1 / periods) - 1
    nominal_rate = periodic_rate * compounds_per_year
    return {
        "periodic_rate": periodic_rate,
        "nominal_annual_rate": nominal_rate,
        "effective_annual_rate": (
            (1 + periodic_rate) ** compounds_per_year - 1
        ),
    }


def _npv(rate: float, cash_flows: list[float]) -> float:
    if rate <= -1:
        raise ValueError("discount rate must exceed -100%")
    return sum(
        cash_flow / ((1 + rate) ** period)
        for period, cash_flow in enumerate(cash_flows)
    )


def _irr(cash_flows: list[float], guess: float = 0.1) -> float:
    if len(cash_flows) < 2:
        raise ValueError("At least two cash flows are required")
    if not any(value < 0 for value in cash_flows) or not any(
        value > 0 for value in cash_flows
    ):
        raise ValueError("Cash flows must contain at least one inflow and outflow")

    rate = max(guess, -0.9)
    for _ in range(100):
        value = _npv(rate, cash_flows)
        derivative = sum(
            -period
            * cash_flow
            / ((1 + rate) ** (period + 1))
            for period, cash_flow in enumerate(cash_flows)
            if period
        )
        if abs(value) < 1e-10:
            return rate
        if derivative == 0:
            break
        candidate = rate - value / derivative
        if not math.isfinite(candidate) or candidate <= -1:
            break
        rate = candidate

    grid = [
        -0.9999,
        *[-0.99 + index * 0.01 for index in range(100)],
        *[index * 0.05 for index in range(1, 201)],
        20.0,
        50.0,
        100.0,
        1000.0,
    ]
    lower = grid[0]
    lower_value = _npv(lower, cash_flows)
    for upper in grid[1:]:
        upper_value = _npv(upper, cash_flows)
        if lower_value == 0:
            return lower
        if lower_value * upper_value < 0:
            for _ in range(200):
                midpoint = (lower + upper) / 2
                midpoint_value = _npv(midpoint, cash_flows)
                if abs(midpoint_value) < 1e-10:
                    return midpoint
                if lower_value * midpoint_value <= 0:
                    upper = midpoint
                else:
                    lower = midpoint
                    lower_value = midpoint_value
            return (lower + upper) / 2
        lower = upper
        lower_value = upper_value
    raise ValueError("No IRR root was found for the supplied cash flows")


def _portfolio_drawdown(values: list[float]) -> dict:
    if not values:
        raise ValueError("At least one portfolio value is required")
    if any(value <= 0 for value in values):
        raise ValueError("Portfolio values must be greater than zero")
    peak = values[0]
    peak_index = 0
    maximum = 0.0
    maximum_peak = 0
    maximum_trough = 0
    drawdowns = []
    for index, value in enumerate(values):
        if value > peak:
            peak = value
            peak_index = index
        drawdown = value / peak - 1
        drawdowns.append(drawdown)
        if drawdown < maximum:
            maximum = drawdown
            maximum_peak = peak_index
            maximum_trough = index
    return {
        "maximum_drawdown": maximum,
        "maximum_drawdown_percent": maximum * 100,
        "peak_index": maximum_peak,
        "trough_index": maximum_trough,
        "drawdown_series": drawdowns,
    }


def _validate_weights(values: list[float], weights: list[float]) -> None:
    if not values or len(values) != len(weights):
        raise ValueError("values and weights must be non-empty and equal length")
    if any(weight < 0 for weight in weights):
        raise ValueError("weights cannot be negative")
    if not math.isclose(sum(weights), 1.0, rel_tol=1e-7, abs_tol=1e-7):
        raise ValueError("weights must sum to 1")


@tool
def annualized_rate_of_return_calculator(
    initial_value: float, ending_value: float, years: float
) -> dict:
    """Calculate geometric annualized return between two portfolio values."""
    _positive(initial_value, "initial_value")
    _positive(ending_value, "ending_value")
    _positive(years, "years")
    rate = (ending_value / initial_value) ** (1 / years) - 1
    return {"annualized_rate": rate, "annualized_percent": rate * 100}


@tool
def appreciation_calculator(original_value: float, current_value: float) -> dict:
    """Calculate absolute and percentage appreciation or depreciation."""
    _positive(original_value, "original_value")
    change = current_value - original_value
    rate = change / original_value
    return {"change": change, "appreciation_rate": rate, "percent": rate * 100}


@tool
def apy_calculator(
    nominal_annual_rate: float, compounds_per_year: int = 12
) -> dict:
    """Convert a nominal annual rate to annual percentage yield."""
    apy = _effective_annual_rate(
        nominal_annual_rate, compounds_per_year
    )
    return {"apy": apy, "apy_percent": apy * 100}


@tool
def basis_point_calculator(start_rate: float, end_rate: float) -> dict:
    """Calculate a rate change in decimal, percentage-point, and basis-point form."""
    change = end_rate - start_rate
    return {
        "rate_change": change,
        "percentage_point_change": change * 100,
        "basis_point_change": change * 10000,
    }


@tool
def bitcoin_etf_calculator(
    investment: float,
    bitcoin_start_price: float,
    bitcoin_end_price: float,
    annual_expense_ratio: float,
    years: float,
    premium_discount_change: float = 0.0,
) -> dict:
    """Estimate a spot Bitcoin ETF investment after price movement and annual fees."""
    _nonnegative(investment, "investment")
    _positive(bitcoin_start_price, "bitcoin_start_price")
    _positive(bitcoin_end_price, "bitcoin_end_price")
    _positive(years, "years")
    if not 0 <= annual_expense_ratio < 1:
        raise ValueError("annual_expense_ratio must be between 0 and 1")
    gross_value = investment * bitcoin_end_price / bitcoin_start_price
    fee_adjusted = gross_value * ((1 - annual_expense_ratio) ** years)
    ending_value = fee_adjusted * (1 + premium_discount_change)
    return {
        "gross_value": gross_value,
        "ending_value": ending_value,
        "gain": ending_value - investment,
        "total_return": ending_value / investment - 1 if investment else None,
        "estimated_fee_drag": gross_value - fee_adjusted,
    }


@tool
def cagr_calculator(
    beginning_value: float, ending_value: float, years: float
) -> dict:
    """Calculate compound annual growth rate."""
    _positive(beginning_value, "beginning_value")
    _positive(ending_value, "ending_value")
    _positive(years, "years")
    cagr = (ending_value / beginning_value) ** (1 / years) - 1
    return {"cagr": cagr, "cagr_percent": cagr * 100}


@tool
def capital_gains_yield_calculator(
    purchase_price: float, sale_price: float
) -> dict:
    """Calculate price-only capital gains yield, excluding income distributions."""
    _positive(purchase_price, "purchase_price")
    gain = sale_price - purchase_price
    yield_rate = gain / purchase_price
    return {"capital_gain": gain, "capital_gains_yield": yield_rate}


@tool
def cd_calculator(
    principal: float,
    annual_rate: float,
    years: float,
    compounds_per_year: int = 12,
) -> dict:
    """Calculate certificate-of-deposit maturity value with compound interest."""
    _nonnegative(principal, "principal")
    maturity = _future_value(
        principal, annual_rate, years, compounds_per_year
    )
    return {"maturity_value": maturity, "interest_earned": maturity - principal}


@tool
def compound_growth_calculator(
    initial_value: float, growth_rate: float, periods: int
) -> dict:
    """Calculate a value after a fixed compound growth rate."""
    _nonnegative(initial_value, "initial_value")
    if periods < 0:
        raise ValueError("periods cannot be negative")
    if growth_rate <= -1:
        raise ValueError("growth_rate must exceed -100%")
    ending = initial_value * ((1 + growth_rate) ** periods)
    return {"ending_value": ending, "total_growth": ending - initial_value}


@tool
def compound_interest_calculator(
    principal: float,
    annual_rate: float,
    years: float,
    compounds_per_year: int = 12,
    periodic_contribution: float = 0.0,
    contribution_at_beginning: bool = False,
) -> dict:
    """Calculate compound interest with optional recurring contributions."""
    _nonnegative(principal, "principal")
    ending = _future_value(
        principal,
        annual_rate,
        years,
        compounds_per_year,
        periodic_contribution,
        contribution_at_beginning,
    )
    periods = _period_count(years, compounds_per_year)
    contributed = principal + periodic_contribution * periods
    return {
        "ending_value": ending,
        "total_contributed": contributed,
        "interest_earned": ending - contributed,
    }


@tool
def compound_interest_rate_calculator(
    principal: float,
    ending_value: float,
    years: float,
    compounds_per_year: int = 12,
) -> dict:
    """Solve the nominal annual compound rate from principal and ending value."""
    return _compound_rates(
        principal, ending_value, years, compounds_per_year
    )


@tool
def continuous_compound_interest_calculator(
    principal: float, annual_rate: float, years: float
) -> dict:
    """Calculate continuously compounded future value."""
    _nonnegative(principal, "principal")
    _nonnegative(years, "years")
    ending = principal * math.exp(annual_rate * years)
    return {"ending_value": ending, "interest_earned": ending - principal}


@tool
def dcf_calculator(
    free_cash_flows: list[float],
    discount_rate: float,
    terminal_growth_rate: float,
    net_debt: float = 0.0,
    shares_outstanding: float | None = None,
) -> dict:
    """Calculate enterprise and equity value using a Gordon-growth DCF."""
    if not free_cash_flows:
        raise ValueError("At least one free cash flow is required")
    if discount_rate <= -1 or terminal_growth_rate <= -1:
        raise ValueError("rates must exceed -100%")
    if discount_rate <= terminal_growth_rate:
        raise ValueError("discount_rate must exceed terminal_growth_rate")
    present_values = [
        cash_flow / ((1 + discount_rate) ** year)
        for year, cash_flow in enumerate(free_cash_flows, start=1)
    ]
    terminal_value = (
        free_cash_flows[-1]
        * (1 + terminal_growth_rate)
        / (discount_rate - terminal_growth_rate)
    )
    terminal_present_value = terminal_value / (
        (1 + discount_rate) ** len(free_cash_flows)
    )
    enterprise_value = sum(present_values) + terminal_present_value
    equity_value = enterprise_value - net_debt
    return {
        "forecast_present_values": present_values,
        "terminal_value": terminal_value,
        "terminal_present_value": terminal_present_value,
        "enterprise_value": enterprise_value,
        "equity_value": equity_value,
        "value_per_share": (
            equity_value / shares_outstanding
            if shares_outstanding is not None and shares_outstanding > 0
            else None
        ),
    }


@tool
def discount_rate_calculator(
    present_value: float, future_value: float, years: float
) -> dict:
    """Solve an annual compound discount rate from present and future value."""
    _positive(present_value, "present_value")
    _positive(future_value, "future_value")
    _positive(years, "years")
    rate = (future_value / present_value) ** (1 / years) - 1
    return {"discount_rate": rate, "discount_rate_percent": rate * 100}


@tool
def ear_calculator(
    nominal_annual_rate: float, compounds_per_year: int = 12
) -> dict:
    """Calculate effective annual rate from a nominal annual rate."""
    rate = _effective_annual_rate(
        nominal_annual_rate, compounds_per_year
    )
    return {
        "effective_annual_rate": rate,
        "effective_annual_percent": rate * 100,
    }


@tool
def margin_interest_calculator(
    borrowed_amount: float,
    annual_margin_rate: float,
    days_borrowed: int,
    day_count_basis: Literal[360, 365] = 360,
) -> dict:
    """Estimate simple margin-loan interest for a stated number of days."""
    _nonnegative(borrowed_amount, "borrowed_amount")
    if days_borrowed < 0:
        raise ValueError("days_borrowed cannot be negative")
    interest = (
        borrowed_amount
        * annual_margin_rate
        * days_borrowed
        / day_count_basis
    )
    return {"interest": interest, "total_repayment": borrowed_amount + interest}


@tool
def mva_calculator(market_value: float, invested_capital: float) -> dict:
    """Calculate market value added as market value less invested capital."""
    mva = market_value - invested_capital
    return {"market_value_added": mva, "value_creation": mva >= 0}


@tool
def maximum_drawdown_calculator(portfolio_values: list[float]) -> dict:
    """Calculate maximum peak-to-trough drawdown from portfolio values."""
    return _portfolio_drawdown(portfolio_values)


@tool
def mirr_calculator(
    cash_flows: list[float],
    finance_rate: float,
    reinvestment_rate: float,
) -> dict:
    """Calculate modified internal rate of return."""
    if len(cash_flows) < 2:
        raise ValueError("At least two cash flows are required")
    periods = len(cash_flows) - 1
    negative_present_value = sum(
        cash_flow / ((1 + finance_rate) ** period)
        for period, cash_flow in enumerate(cash_flows)
        if cash_flow < 0
    )
    positive_future_value = sum(
        cash_flow * ((1 + reinvestment_rate) ** (periods - period))
        for period, cash_flow in enumerate(cash_flows)
        if cash_flow > 0
    )
    if negative_present_value == 0 or positive_future_value <= 0:
        raise ValueError("MIRR requires both negative and positive cash flows")
    mirr = (
        positive_future_value / abs(negative_present_value)
    ) ** (1 / periods) - 1
    return {"mirr": mirr, "mirr_percent": mirr * 100}


@tool
def money_factor_calculator(annual_percentage_rate: float) -> dict:
    """Convert a lease APR in decimal form to its approximate money factor."""
    money_factor = annual_percentage_rate / 24
    return {
        "money_factor": money_factor,
        "apr_percent": annual_percentage_rate * 100,
    }


@tool
def money_market_account_calculator(
    principal: float,
    annual_rate: float,
    years: float,
    compounds_per_year: int = 12,
    periodic_deposit: float = 0.0,
) -> dict:
    """Project a money-market account with compound interest and deposits."""
    ending = _future_value(
        principal,
        annual_rate,
        years,
        compounds_per_year,
        periodic_deposit,
    )
    periods = _period_count(years, compounds_per_year)
    deposits = principal + periodic_deposit * periods
    return {
        "ending_balance": ending,
        "total_deposits": deposits,
        "interest_earned": ending - deposits,
    }


@tool
def moving_average_calculator(
    values: list[float],
    window: int,
    method: Literal["simple", "exponential"] = "simple",
) -> dict:
    """Calculate simple or exponential moving-average values."""
    if not values:
        raise ValueError("At least one value is required")
    if window < 1 or window > len(values):
        raise ValueError("window must be between 1 and the number of values")
    if method == "simple":
        averages = [
            sum(values[index - window + 1:index + 1]) / window
            for index in range(window - 1, len(values))
        ]
        start_index = window - 1
    else:
        multiplier = 2 / (window + 1)
        seed = sum(values[:window]) / window
        averages = [seed]
        for value in values[window:]:
            averages.append(
                value * multiplier + averages[-1] * (1 - multiplier)
            )
        start_index = window - 1
    return {
        "method": method,
        "window": window,
        "start_index": start_index,
        "moving_averages": averages,
        "latest": averages[-1],
    }


@tool
def mutual_fund_calculator(
    initial_investment: float,
    annual_gross_return: float,
    annual_expense_ratio: float,
    years: float,
    monthly_contribution: float = 0.0,
    sales_load: float = 0.0,
) -> dict:
    """Project mutual-fund value after expenses, sales load, and contributions."""
    if not 0 <= sales_load < 1:
        raise ValueError("sales_load must be between 0 and 1")
    net_principal = initial_investment * (1 - sales_load)
    net_rate = annual_gross_return - annual_expense_ratio
    ending = _future_value(
        net_principal, net_rate, years, 12, monthly_contribution
    )
    periods = _period_count(years, 12)
    total_paid = initial_investment + monthly_contribution * periods
    return {
        "ending_value": ending,
        "total_paid": total_paid,
        "gain_after_fees": ending - total_paid,
        "initial_sales_load_cost": initial_investment * sales_load,
    }


@tool
def nopat_calculator(
    operating_income: float, effective_tax_rate: float
) -> dict:
    """Calculate net operating profit after tax."""
    if not 0 <= effective_tax_rate <= 1:
        raise ValueError("effective_tax_rate must be between 0 and 1")
    nopat = operating_income * (1 - effective_tax_rate)
    return {"nopat": nopat, "cash_tax_on_operating_income": operating_income - nopat}


@tool
def npv_calculator(discount_rate: float, cash_flows: list[float]) -> dict:
    """Calculate net present value where the first cash flow occurs at time zero."""
    if not cash_flows:
        raise ValueError("At least one cash flow is required")
    if discount_rate <= -1:
        raise ValueError("discount_rate must exceed -100%")
    present_values = [
        value / ((1 + discount_rate) ** period)
        for period, value in enumerate(cash_flows)
    ]
    return {"npv": sum(present_values), "present_values": present_values}


@tool
def opportunity_cost_calculator(
    chosen_value: float, best_alternative_value: float
) -> dict:
    """Calculate the value forgone by choosing one option over the best alternative."""
    return {
        "opportunity_cost": best_alternative_value - chosen_value,
        "chosen_value": chosen_value,
        "best_alternative_value": best_alternative_value,
    }


@tool
def optimal_hedge_ratio_calculator(
    correlation: float,
    spot_volatility: float,
    futures_volatility: float,
) -> dict:
    """Calculate the minimum-variance hedge ratio."""
    if not -1 <= correlation <= 1:
        raise ValueError("correlation must be between -1 and 1")
    _nonnegative(spot_volatility, "spot_volatility")
    _positive(futures_volatility, "futures_volatility")
    ratio = correlation * spot_volatility / futures_volatility
    return {"optimal_hedge_ratio": ratio}


@tool
def percentage_return_calculator(
    initial_value: float, ending_value: float, income: float = 0.0
) -> dict:
    """Calculate total percentage return including optional income."""
    _positive(initial_value, "initial_value")
    gain = ending_value + income - initial_value
    rate = gain / initial_value
    return {"gain": gain, "return_rate": rate, "return_percent": rate * 100}


@tool
def perpetuity_calculator(
    periodic_cash_flow: float,
    discount_rate: float,
    growth_rate: float = 0.0,
) -> dict:
    """Calculate present value of a level or growing perpetuity."""
    if discount_rate <= growth_rate:
        raise ValueError("discount_rate must exceed growth_rate")
    value = periodic_cash_flow / (discount_rate - growth_rate)
    return {"present_value": value}


@tool
def present_value_calculator(
    future_value: float,
    annual_rate: float,
    years: float,
    compounds_per_year: int = 1,
) -> dict:
    """Discount a future lump sum to present value."""
    value = _present_value(
        future_value, annual_rate, years, compounds_per_year
    )
    return {"present_value": value, "discount": future_value - value}


@tool
def effective_annual_yield_calculator(
    nominal_annual_rate: float, compounds_per_year: int = 12
) -> dict:
    """Calculate effective annual yield from a nominal rate."""
    return {
        "effective_annual_yield": _effective_annual_rate(
            nominal_annual_rate, compounds_per_year
        )
    }


@tool
def effective_interest_rate_calculator(
    nominal_annual_rate: float, compounds_per_year: int = 12
) -> dict:
    """Calculate the effective annual interest rate."""
    return {
        "effective_interest_rate": _effective_annual_rate(
            nominal_annual_rate, compounds_per_year
        )
    }


@tool
def equivalent_rate_aer_calculator(
    nominal_annual_rate: float,
    source_compounds_per_year: int,
    target_compounds_per_year: int,
) -> dict:
    """Convert a nominal rate to an equivalent nominal rate at another frequency."""
    if source_compounds_per_year < 1 or target_compounds_per_year < 1:
        raise ValueError("compounding frequencies must be at least 1")
    aer = (
        1 + nominal_annual_rate / source_compounds_per_year
    ) ** source_compounds_per_year - 1
    target_periodic = (1 + aer) ** (1 / target_compounds_per_year) - 1
    return {
        "annual_equivalent_rate": aer,
        "target_periodic_rate": target_periodic,
        "target_nominal_annual_rate": target_periodic
        * target_compounds_per_year,
    }


@tool
def expected_return_calculator(
    scenario_returns: list[float], probabilities: list[float]
) -> dict:
    """Calculate probability-weighted expected return and standard deviation."""
    _validate_weights(scenario_returns, probabilities)
    expected = sum(
        value * probability
        for value, probability in zip(scenario_returns, probabilities)
    )
    variance = sum(
        probability * ((value - expected) ** 2)
        for value, probability in zip(scenario_returns, probabilities)
    )
    return {
        "expected_return": expected,
        "standard_deviation": math.sqrt(variance),
    }


@tool
def expected_utility_calculator(
    wealth_outcomes: list[float],
    probabilities: list[float],
    utility: Literal["linear", "log", "crra"] = "crra",
    risk_aversion: float = 2.0,
) -> dict:
    """Calculate expected utility and certainty equivalent for wealth outcomes."""
    _validate_weights(wealth_outcomes, probabilities)
    if utility in {"log", "crra"} and any(
        wealth <= 0 for wealth in wealth_outcomes
    ):
        raise ValueError("wealth outcomes must be positive for log or CRRA utility")
    if utility == "linear":
        utilities = wealth_outcomes
        certainty_equivalent = sum(
            wealth * probability
            for wealth, probability in zip(wealth_outcomes, probabilities)
        )
    elif utility == "log" or math.isclose(risk_aversion, 1.0):
        utilities = [math.log(wealth) for wealth in wealth_outcomes]
        expected_utility = sum(
            value * probability
            for value, probability in zip(utilities, probabilities)
        )
        certainty_equivalent = math.exp(expected_utility)
    else:
        utilities = [
            (wealth ** (1 - risk_aversion) - 1) / (1 - risk_aversion)
            for wealth in wealth_outcomes
        ]
        expected_utility = sum(
            value * probability
            for value, probability in zip(utilities, probabilities)
        )
        base = expected_utility * (1 - risk_aversion) + 1
        if base <= 0:
            certainty_equivalent = None
        else:
            certainty_equivalent = base ** (1 / (1 - risk_aversion))
    expected_utility = sum(
        value * probability
        for value, probability in zip(utilities, probabilities)
    )
    return {
        "expected_utility": expected_utility,
        "certainty_equivalent": certainty_equivalent,
        "utility": utility,
    }


@tool
def expense_ratio_calculator(
    annual_fund_expenses: float,
    average_net_assets: float,
    investor_balance: float | None = None,
) -> dict:
    """Calculate a fund expense ratio and optional annual investor cost."""
    _positive(average_net_assets, "average_net_assets")
    ratio = annual_fund_expenses / average_net_assets
    return {
        "expense_ratio": ratio,
        "expense_ratio_percent": ratio * 100,
        "estimated_investor_cost": (
            investor_balance * ratio if investor_balance is not None else None
        ),
    }


@tool
def fixed_deposit_calculator(
    principal: float,
    annual_rate: float,
    years: float,
    compounds_per_year: int = 4,
) -> dict:
    """Calculate fixed-deposit maturity value and interest earned."""
    ending = _future_value(
        principal, annual_rate, years, compounds_per_year
    )
    return {"maturity_value": ending, "interest_earned": ending - principal}


@tool
def future_value_calculator(
    present_value: float,
    annual_rate: float,
    years: float,
    compounds_per_year: int = 1,
) -> dict:
    """Calculate the future value of a lump sum."""
    value = _future_value(
        present_value, annual_rate, years, compounds_per_year
    )
    return {"future_value": value, "growth": value - present_value}


@tool
def hedge_ratio_calculator(
    exposure_value: float,
    hedge_instrument_value: float,
    contract_size: float | None = None,
) -> dict:
    """Calculate hedge ratio and optional number of hedge contracts."""
    _positive(exposure_value, "exposure_value")
    ratio = hedge_instrument_value / exposure_value
    contracts = None
    if contract_size is not None:
        _positive(contract_size, "contract_size")
        contracts = hedge_instrument_value / contract_size
    return {"hedge_ratio": ratio, "contracts": contracts}


@tool
def holding_period_return_calculator(
    beginning_value: float, ending_value: float, income: float = 0.0
) -> dict:
    """Calculate holding-period return including dividends or other income."""
    _positive(beginning_value, "beginning_value")
    return {
        "holding_period_return": (
            ending_value - beginning_value + income
        ) / beginning_value
    }


@tool
def information_ratio_calculator(
    portfolio_returns: list[float],
    benchmark_returns: list[float],
    periods_per_year: int = 12,
) -> dict:
    """Calculate annualized information ratio from portfolio and benchmark returns."""
    if len(portfolio_returns) < 2 or len(portfolio_returns) != len(
        benchmark_returns
    ):
        raise ValueError("return series must be equal length with at least two values")
    active = [
        portfolio - benchmark
        for portfolio, benchmark in zip(portfolio_returns, benchmark_returns)
    ]
    tracking_error = pstdev(active) * math.sqrt(periods_per_year)
    annualized_active_return = mean(active) * periods_per_year
    return {
        "information_ratio": (
            annualized_active_return / tracking_error
            if tracking_error
            else None
        ),
        "annualized_active_return": annualized_active_return,
        "tracking_error": tracking_error,
    }


@tool
def interest_rate_calculator(
    principal: float, interest_earned: float, years: float
) -> dict:
    """Solve the annual simple-interest rate."""
    _positive(principal, "principal")
    _positive(years, "years")
    rate = interest_earned / (principal * years)
    return {"annual_interest_rate": rate}


@tool
def investment_calculator(
    initial_investment: float,
    annual_return: float,
    years: float,
    monthly_contribution: float = 0.0,
) -> dict:
    """Project an investment with monthly compounding and contributions."""
    ending = _future_value(
        initial_investment,
        annual_return,
        years,
        12,
        monthly_contribution,
    )
    periods = _period_count(years, 12)
    contributed = initial_investment + monthly_contribution * periods
    return {
        "ending_value": ending,
        "total_contributed": contributed,
        "investment_gain": ending - contributed,
    }


@tool
def investment_fee_calculator(
    initial_investment: float,
    annual_gross_return: float,
    annual_fee_rate: float,
    years: float,
    monthly_contribution: float = 0.0,
    upfront_fee_rate: float = 0.0,
) -> dict:
    """Estimate investment value and cumulative drag from recurring and upfront fees."""
    if not 0 <= upfront_fee_rate < 1:
        raise ValueError("upfront_fee_rate must be between 0 and 1")
    gross = _future_value(
        initial_investment,
        annual_gross_return,
        years,
        12,
        monthly_contribution,
    )
    net = _future_value(
        initial_investment * (1 - upfront_fee_rate),
        annual_gross_return - annual_fee_rate,
        years,
        12,
        monthly_contribution,
    )
    return {
        "gross_value_without_fees": gross,
        "net_value_after_fees": net,
        "estimated_fee_drag": gross - net,
    }


@tool
def irr_calculator(cash_flows: list[float], guess: float = 0.1) -> dict:
    """Calculate internal rate of return for periodic cash flows."""
    rate = _irr(cash_flows, guess)
    return {
        "irr": rate,
        "irr_percent": rate * 100,
        "npv_at_irr": _npv(rate, cash_flows),
        "caution": "Non-conventional cash flows can have multiple IRRs.",
    }


@tool
def pvifa_calculator(rate_per_period: float, periods: int) -> dict:
    """Calculate the present value interest factor of an ordinary annuity."""
    if periods < 1:
        raise ValueError("periods must be at least 1")
    if rate_per_period <= -1:
        raise ValueError("rate_per_period must exceed -100%")
    factor = (
        periods
        if rate_per_period == 0
        else (1 - (1 + rate_per_period) ** -periods) / rate_per_period
    )
    return {"pvifa": factor}


@tool
def rate_of_return_calculator(
    amount_invested: float, amount_returned: float
) -> dict:
    """Calculate gain and simple rate of return on invested capital."""
    _positive(amount_invested, "amount_invested")
    gain = amount_returned - amount_invested
    rate = gain / amount_invested
    return {"gain": gain, "rate_of_return": rate, "return_percent": rate * 100}


@tool
def real_rate_of_return_calculator(
    nominal_return: float, inflation_rate: float
) -> dict:
    """Calculate exact real return using the Fisher relationship."""
    if inflation_rate <= -1:
        raise ValueError("inflation_rate must exceed -100%")
    real = (1 + nominal_return) / (1 + inflation_rate) - 1
    return {"real_rate_of_return": real, "real_return_percent": real * 100}


@tool
def roce_calculator(ebit: float, capital_employed: float) -> dict:
    """Calculate return on capital employed."""
    _positive(capital_employed, "capital_employed")
    roce = ebit / capital_employed
    return {"roce": roce, "roce_percent": roce * 100}


@tool
def roi_calculator(investment_cost: float, investment_gain: float) -> dict:
    """Calculate return on investment from cost and total proceeds."""
    _positive(investment_cost, "investment_cost")
    net_profit = investment_gain - investment_cost
    roi = net_profit / investment_cost
    return {"net_profit": net_profit, "roi": roi, "roi_percent": roi * 100}


@tool
def savings_interest_rate_calculator(
    initial_balance: float,
    ending_balance: float,
    years: float,
    compounds_per_year: int = 12,
) -> dict:
    """Solve the nominal and effective savings rate without additional deposits."""
    return _compound_rates(
        initial_balance,
        ending_balance,
        years,
        compounds_per_year,
    )


@tool
def sharpe_ratio_calculator(
    periodic_returns: list[float],
    annual_risk_free_rate: float = 0.0,
    periods_per_year: int = 12,
) -> dict:
    """Calculate annualized Sharpe ratio from periodic total returns."""
    if len(periodic_returns) < 2:
        raise ValueError("At least two returns are required")
    annualized_return = mean(periodic_returns) * periods_per_year
    volatility = pstdev(periodic_returns) * math.sqrt(periods_per_year)
    return {
        "sharpe_ratio": (
            (annualized_return - annual_risk_free_rate) / volatility
            if volatility
            else None
        ),
        "annualized_return": annualized_return,
        "annualized_volatility": volatility,
    }


@tool
def simple_interest_calculator(
    principal: float, annual_rate: float, years: float
) -> dict:
    """Calculate simple interest and ending balance."""
    _nonnegative(principal, "principal")
    _nonnegative(years, "years")
    interest = principal * annual_rate * years
    return {"interest": interest, "ending_balance": principal + interest}


@tool
def sinking_fund_calculator(
    target_amount: float,
    rate_per_period: float,
    periods: int,
    deposit_at_beginning: bool = False,
) -> dict:
    """Calculate the periodic deposit needed to reach a sinking-fund target."""
    _nonnegative(target_amount, "target_amount")
    if periods < 1:
        raise ValueError("periods must be at least 1")
    if rate_per_period <= -1:
        raise ValueError("rate_per_period must exceed -100%")
    if rate_per_period == 0:
        deposit = target_amount / periods
    else:
        factor = ((1 + rate_per_period) ** periods - 1) / rate_per_period
        if deposit_at_beginning:
            factor *= 1 + rate_per_period
        deposit = target_amount / factor
    return {"periodic_deposit": deposit, "total_deposits": deposit * periods}


@tool
def sortino_ratio_calculator(
    periodic_returns: list[float],
    annual_target_return: float = 0.0,
    periods_per_year: int = 12,
) -> dict:
    """Calculate annualized Sortino ratio using downside deviation."""
    if len(periodic_returns) < 2:
        raise ValueError("At least two returns are required")
    target_per_period = annual_target_return / periods_per_year
    downside_squared = [
        min(0.0, value - target_per_period) ** 2
        for value in periodic_returns
    ]
    downside_deviation = math.sqrt(
        sum(downside_squared) / len(periodic_returns)
    ) * math.sqrt(periods_per_year)
    annualized_excess = (
        mean(periodic_returns) * periods_per_year - annual_target_return
    )
    return {
        "sortino_ratio": (
            annualized_excess / downside_deviation
            if downside_deviation
            else None
        ),
        "annualized_excess_return": annualized_excess,
        "annualized_downside_deviation": downside_deviation,
    }


@tool
def time_value_of_money_calculator(
    present_value: float,
    annual_rate: float,
    years: float,
    compounds_per_year: int = 1,
    periodic_payment: float = 0.0,
    payment_at_beginning: bool = False,
) -> dict:
    """Calculate future value for a lump sum plus periodic payments."""
    future = _future_value(
        present_value,
        annual_rate,
        years,
        compounds_per_year,
        periodic_payment,
        payment_at_beginning,
    )
    periods = _period_count(years, compounds_per_year)
    contributed = present_value + periodic_payment * periods
    return {
        "future_value": future,
        "total_contributed": contributed,
        "time_value_gain": future - contributed,
    }


@tool
def treynor_ratio_calculator(
    portfolio_return: float,
    risk_free_rate: float,
    portfolio_beta: float,
) -> dict:
    """Calculate the Treynor ratio using portfolio beta as systematic risk."""
    if portfolio_beta == 0:
        raise ValueError("portfolio_beta cannot be zero")
    return {
        "treynor_ratio": (
            portfolio_return - risk_free_rate
        ) / portfolio_beta
    }


@tool
def ttm_calculator(
    period_values: list[float], periods_in_ttm: int = 4
) -> dict:
    """Calculate a trailing-twelve-month total from quarterly or monthly values."""
    if periods_in_ttm < 1:
        raise ValueError("periods_in_ttm must be at least 1")
    if len(period_values) < periods_in_ttm:
        raise ValueError("Not enough period values for the requested TTM window")
    selected = period_values[-periods_in_ttm:]
    return {"ttm_value": sum(selected), "included_values": selected}


@tool
def value_at_risk_calculator(
    periodic_returns: list[float],
    portfolio_value: float,
    confidence_level: float = 0.95,
    method: Literal["historical", "parametric"] = "historical",
) -> dict:
    """Estimate one-period Value at Risk using historical or normal parametric VaR."""
    if len(periodic_returns) < 2:
        raise ValueError("At least two returns are required")
    _nonnegative(portfolio_value, "portfolio_value")
    if not 0.5 < confidence_level < 1:
        raise ValueError("confidence_level must be between 0.5 and 1")
    if method == "historical":
        sorted_returns = sorted(periodic_returns)
        tail_count = max(
            1,
            math.ceil(
                (1 - confidence_level) * len(sorted_returns) - 1e-12
            ),
        )
        index = max(
            0,
            min(
                len(sorted_returns) - 1,
                tail_count - 1,
            ),
        )
        cutoff_return = sorted_returns[index]
    else:
        z_score = NormalDist().inv_cdf(confidence_level)
        cutoff_return = mean(periodic_returns) - z_score * pstdev(
            periodic_returns
        )
    var_rate = max(0.0, -cutoff_return)
    return {
        "value_at_risk": portfolio_value * var_rate,
        "var_rate": var_rate,
        "cutoff_return": cutoff_return,
        "confidence_level": confidence_level,
        "method": method,
    }


@tool
def week_over_week_calculator(
    previous_week_value: float, current_week_value: float
) -> dict:
    """Calculate absolute and percentage week-over-week change."""
    if previous_week_value == 0:
        raise ValueError("previous_week_value cannot be zero")
    change = current_week_value - previous_week_value
    rate = change / abs(previous_week_value)
    return {
        "absolute_change": change,
        "week_over_week_rate": rate,
        "week_over_week_percent": rate * 100,
    }


FINANCE_CALCULATOR_TOOLS = (
    annualized_rate_of_return_calculator,
    appreciation_calculator,
    apy_calculator,
    basis_point_calculator,
    bitcoin_etf_calculator,
    cagr_calculator,
    capital_gains_yield_calculator,
    cd_calculator,
    compound_growth_calculator,
    compound_interest_calculator,
    compound_interest_rate_calculator,
    continuous_compound_interest_calculator,
    dcf_calculator,
    discount_rate_calculator,
    ear_calculator,
    margin_interest_calculator,
    mva_calculator,
    maximum_drawdown_calculator,
    mirr_calculator,
    money_factor_calculator,
    money_market_account_calculator,
    moving_average_calculator,
    mutual_fund_calculator,
    nopat_calculator,
    npv_calculator,
    opportunity_cost_calculator,
    optimal_hedge_ratio_calculator,
    percentage_return_calculator,
    perpetuity_calculator,
    present_value_calculator,
    effective_annual_yield_calculator,
    effective_interest_rate_calculator,
    equivalent_rate_aer_calculator,
    expected_return_calculator,
    expected_utility_calculator,
    expense_ratio_calculator,
    fixed_deposit_calculator,
    future_value_calculator,
    hedge_ratio_calculator,
    holding_period_return_calculator,
    information_ratio_calculator,
    interest_rate_calculator,
    investment_calculator,
    investment_fee_calculator,
    irr_calculator,
    pvifa_calculator,
    rate_of_return_calculator,
    real_rate_of_return_calculator,
    roce_calculator,
    roi_calculator,
    savings_interest_rate_calculator,
    sharpe_ratio_calculator,
    simple_interest_calculator,
    sinking_fund_calculator,
    sortino_ratio_calculator,
    time_value_of_money_calculator,
    treynor_ratio_calculator,
    ttm_calculator,
    value_at_risk_calculator,
    week_over_week_calculator,
)

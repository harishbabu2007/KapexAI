"""Deterministic equity-investment calculator tools."""

import math
from statistics import mean

from langchain.tools import tool

from kapexai.tools.finance_calculators import (
    _future_value,
    _nonnegative,
    _positive,
)


def _ratio(numerator: float, denominator: float, name: str) -> float:
    if denominator == 0:
        raise ValueError(f"{name} denominator cannot be zero")
    return numerator / denominator


def _beta(asset_returns: list[float], market_returns: list[float]) -> float:
    if len(asset_returns) < 2 or len(asset_returns) != len(market_returns):
        raise ValueError("return series must be equal length with at least two values")
    asset_mean = mean(asset_returns)
    market_mean = mean(market_returns)
    covariance = sum(
        (asset - asset_mean) * (market - market_mean)
        for asset, market in zip(asset_returns, market_returns)
    ) / len(asset_returns)
    market_variance = sum(
        (market - market_mean) ** 2 for market in market_returns
    ) / len(market_returns)
    if market_variance == 0:
        raise ValueError("market return variance cannot be zero")
    return covariance / market_variance


def _wacc(
    equity_value: float,
    debt_value: float,
    cost_of_equity: float,
    pre_tax_cost_of_debt: float,
    tax_rate: float,
    preferred_value: float = 0.0,
    cost_of_preferred: float = 0.0,
) -> dict:
    if any(value < 0 for value in (equity_value, debt_value, preferred_value)):
        raise ValueError("capital market values cannot be negative")
    if not 0 <= tax_rate <= 1:
        raise ValueError("tax_rate must be between 0 and 1")
    total_capital = equity_value + debt_value + preferred_value
    _positive(total_capital, "total capital")
    equity_weight = equity_value / total_capital
    debt_weight = debt_value / total_capital
    preferred_weight = preferred_value / total_capital
    after_tax_debt_cost = pre_tax_cost_of_debt * (1 - tax_rate)
    rate = (
        equity_weight * cost_of_equity
        + debt_weight * after_tax_debt_cost
        + preferred_weight * cost_of_preferred
    )
    return {
        "weighted_average_cost_of_capital": rate,
        "equity_weight": equity_weight,
        "debt_weight": debt_weight,
        "preferred_weight": preferred_weight,
        "after_tax_cost_of_debt": after_tax_debt_cost,
    }


@tool
def beta_stock_calculator(
    stock_returns: list[float], market_returns: list[float]
) -> dict:
    """Calculate stock beta as covariance with the market divided by market variance."""
    beta = _beta(stock_returns, market_returns)
    return {"stock_beta": beta}


@tool
def capm_calculator(
    risk_free_rate: float,
    beta: float,
    expected_market_return: float,
    country_risk_premium: float = 0.0,
) -> dict:
    """Calculate expected return using the Capital Asset Pricing Model."""
    market_risk_premium = expected_market_return - risk_free_rate
    expected_return = (
        risk_free_rate + beta * market_risk_premium + country_risk_premium
    )
    return {
        "expected_return": expected_return,
        "market_risk_premium": market_risk_premium,
    }


@tool
def carried_interest_calculator(
    invested_capital: float,
    exit_value: float,
    carry_rate: float = 0.20,
    hurdle_rate: float = 0.0,
    years: float = 1.0,
) -> dict:
    """Estimate carried interest after returning capital and a compounded hurdle."""
    _nonnegative(invested_capital, "invested_capital")
    _nonnegative(exit_value, "exit_value")
    _positive(years, "years")
    if hurdle_rate <= -1:
        raise ValueError("hurdle_rate must exceed -100%")
    if not 0 <= carry_rate <= 1:
        raise ValueError("carry_rate must be between 0 and 1")
    preferred_profit = invested_capital * ((1 + hurdle_rate) ** years - 1)
    total_profit = exit_value - invested_capital
    carry_eligible_profit = max(0.0, total_profit - preferred_profit)
    carried_interest = carry_eligible_profit * carry_rate
    return {
        "total_profit": total_profit,
        "preferred_profit": preferred_profit,
        "carry_eligible_profit": carry_eligible_profit,
        "carried_interest": carried_interest,
        "limited_partner_distribution": exit_value - carried_interest,
    }


@tool
def cost_of_capital_calculator(
    equity_value: float,
    debt_value: float,
    cost_of_equity: float,
    pre_tax_cost_of_debt: float,
    tax_rate: float,
    preferred_value: float = 0.0,
    cost_of_preferred: float = 0.0,
) -> dict:
    """Calculate market-value weighted cost of capital."""
    return _wacc(
        equity_value,
        debt_value,
        cost_of_equity,
        pre_tax_cost_of_debt,
        tax_rate,
        preferred_value,
        cost_of_preferred,
    )


@tool
def cost_of_equity_calculator(
    risk_free_rate: float,
    beta: float,
    expected_market_return: float,
    country_risk_premium: float = 0.0,
) -> dict:
    """Calculate cost of equity using CAPM plus optional country risk premium."""
    market_premium = expected_market_return - risk_free_rate
    cost = risk_free_rate + beta * market_premium + country_risk_premium
    return {"cost_of_equity": cost, "market_risk_premium": market_premium}


@tool
def dividend_calculator(
    shares_owned: float,
    dividend_per_share: float,
    payments_per_year: int = 1,
    dividend_tax_rate: float = 0.0,
) -> dict:
    """Calculate gross and after-tax annual dividends for a shareholding."""
    _nonnegative(shares_owned, "shares_owned")
    if payments_per_year < 1:
        raise ValueError("payments_per_year must be at least 1")
    if not 0 <= dividend_tax_rate <= 1:
        raise ValueError("dividend_tax_rate must be between 0 and 1")
    payment = shares_owned * dividend_per_share
    annual = payment * payments_per_year
    return {
        "dividend_per_payment": payment,
        "annual_gross_dividend": annual,
        "annual_after_tax_dividend": annual * (1 - dividend_tax_rate),
    }


@tool
def dividend_discount_model_calculator(
    next_period_dividend: float,
    required_return: float,
    perpetual_growth_rate: float,
) -> dict:
    """Value equity with the Gordon-growth dividend discount model."""
    if required_return <= perpetual_growth_rate:
        raise ValueError("required_return must exceed perpetual_growth_rate")
    intrinsic_value = next_period_dividend / (
        required_return - perpetual_growth_rate
    )
    return {"intrinsic_value": intrinsic_value}


@tool
def dividend_payout_ratio_calculator(
    common_dividends: float, net_income_available_to_common: float
) -> dict:
    """Calculate the proportion of common earnings paid as dividends."""
    payout = _ratio(
        common_dividends,
        net_income_available_to_common,
        "dividend payout ratio",
    )
    return {"dividend_payout_ratio": payout}


@tool
def dividend_yield_calculator(
    annual_dividend_per_share: float, market_price_per_share: float
) -> dict:
    """Calculate annual dividend yield."""
    _positive(market_price_per_share, "market_price_per_share")
    dividend_yield = annual_dividend_per_share / market_price_per_share
    return {"dividend_yield": dividend_yield}


@tool
def dupont_analysis_calculator(
    net_income: float,
    revenue: float,
    average_total_assets: float,
    average_shareholders_equity: float,
) -> dict:
    """Calculate three-step DuPont ROE decomposition."""
    net_margin = _ratio(net_income, revenue, "net margin")
    asset_turnover = _ratio(
        revenue, average_total_assets, "asset turnover"
    )
    equity_multiplier = _ratio(
        average_total_assets,
        average_shareholders_equity,
        "equity multiplier",
    )
    return {
        "net_profit_margin": net_margin,
        "asset_turnover": asset_turnover,
        "equity_multiplier": equity_multiplier,
        "return_on_equity": net_margin * asset_turnover * equity_multiplier,
    }


@tool
def earnings_per_share_calculator(
    net_income: float,
    preferred_dividends: float,
    weighted_average_common_shares: float,
) -> dict:
    """Calculate basic earnings per common share."""
    _positive(weighted_average_common_shares, "weighted_average_common_shares")
    earnings = net_income - preferred_dividends
    return {"earnings_available_to_common": earnings, "earnings_per_share": earnings / weighted_average_common_shares}


@tool
def earnings_per_share_growth_calculator(
    prior_eps: float, current_eps: float
) -> dict:
    """Calculate period-over-period EPS growth."""
    if prior_eps == 0:
        raise ValueError("prior_eps cannot be zero")
    growth = (current_eps - prior_eps) / abs(prior_eps)
    return {"eps_growth_rate": growth, "eps_growth_percent": growth * 100}


@tool
def ebitda_multiple_calculator(
    enterprise_value: float, ebitda: float
) -> dict:
    """Calculate the enterprise-value-to-EBITDA multiple."""
    multiple = _ratio(enterprise_value, ebitda, "EBITDA multiple")
    return {"ev_to_ebitda": multiple}


@tool
def economic_value_added_calculator(
    nopat: float, invested_capital: float, weighted_average_cost_of_capital: float
) -> dict:
    """Calculate economic value added after the capital charge."""
    capital_charge = invested_capital * weighted_average_cost_of_capital
    return {
        "economic_value_added": nopat - capital_charge,
        "capital_charge": capital_charge,
    }


@tool
def enterprise_value_calculator(
    market_capitalization: float,
    total_debt: float,
    cash_and_equivalents: float,
    preferred_stock: float = 0.0,
    noncontrolling_interest: float = 0.0,
) -> dict:
    """Calculate enterprise value from equity value and net financial claims."""
    enterprise_value = (
        market_capitalization
        + total_debt
        + preferred_stock
        + noncontrolling_interest
        - cash_and_equivalents
    )
    return {"enterprise_value": enterprise_value}


@tool
def ev_to_sales_calculator(enterprise_value: float, revenue: float) -> dict:
    """Calculate enterprise value to sales."""
    return {
        "ev_to_sales": _ratio(enterprise_value, revenue, "EV to sales")
    }


@tool
def free_float_calculator(
    total_outstanding_shares: float,
    restricted_and_strategic_shares: float,
) -> dict:
    """Calculate freely tradable shares and free-float percentage."""
    _positive(total_outstanding_shares, "total_outstanding_shares")
    if not 0 <= restricted_and_strategic_shares <= total_outstanding_shares:
        raise ValueError("restricted shares must be between zero and total shares")
    free_float = total_outstanding_shares - restricted_and_strategic_shares
    return {
        "free_float_shares": free_float,
        "free_float_percent": free_float / total_outstanding_shares * 100,
    }


@tool
def graham_number_calculator(
    earnings_per_share: float, book_value_per_share: float
) -> dict:
    """Calculate the Graham Number using sqrt(22.5 times EPS times BVPS)."""
    if earnings_per_share < 0 or book_value_per_share < 0:
        raise ValueError("EPS and book value per share cannot be negative")
    return {
        "graham_number": math.sqrt(
            22.5 * earnings_per_share * book_value_per_share
        )
    }


@tool
def intrinsic_value_calculator(
    earnings_per_share: float,
    expected_growth_percent: float,
    aaa_corporate_bond_yield_percent: float,
    graham_base_yield_percent: float = 4.4,
) -> dict:
    """Estimate Benjamin Graham intrinsic value using growth and bond yields."""
    _positive(
        aaa_corporate_bond_yield_percent,
        "aaa_corporate_bond_yield_percent",
    )
    value = (
        earnings_per_share
        * (8.5 + 2 * expected_growth_percent)
        * graham_base_yield_percent
        / aaa_corporate_bond_yield_percent
    )
    return {
        "intrinsic_value": value,
        "caution": "The Graham formula is a heuristic, not a complete valuation.",
    }


@tool
def margin_of_safety_calculator(
    intrinsic_value: float, market_price: float
) -> dict:
    """Calculate valuation margin of safety relative to intrinsic value."""
    _positive(intrinsic_value, "intrinsic_value")
    margin = (intrinsic_value - market_price) / intrinsic_value
    return {
        "margin_of_safety": margin,
        "margin_of_safety_percent": margin * 100,
    }


@tool
def market_capitalization_calculator(
    share_price: float, shares_outstanding: float
) -> dict:
    """Calculate equity market capitalization."""
    _nonnegative(share_price, "share_price")
    _nonnegative(shares_outstanding, "shares_outstanding")
    return {"market_capitalization": share_price * shares_outstanding}


@tool
def maturity_value_calculator(
    principal: float,
    annual_rate: float,
    years: float,
    compounds_per_year: int = 1,
) -> dict:
    """Calculate investment maturity value with compound interest."""
    _nonnegative(principal, "principal")
    maturity = _future_value(
        principal, annual_rate, years, compounds_per_year
    )
    return {"maturity_value": maturity, "interest_earned": maturity - principal}


@tool
def nav_calculator(
    total_assets: float,
    total_liabilities: float,
    shares_or_units_outstanding: float,
) -> dict:
    """Calculate net asset value in total and per share or fund unit."""
    _positive(shares_or_units_outstanding, "shares_or_units_outstanding")
    net_assets = total_assets - total_liabilities
    return {
        "net_asset_value": net_assets,
        "nav_per_share": net_assets / shares_or_units_outstanding,
    }


@tool
def operating_cash_flow_ratio_calculator(
    operating_cash_flow: float, current_liabilities: float
) -> dict:
    """Calculate operating cash flow coverage of current liabilities."""
    return {
        "operating_cash_flow_ratio": _ratio(
            operating_cash_flow,
            current_liabilities,
            "operating cash flow ratio",
        )
    }


@tool
def peg_ratio_calculator(
    price_to_earnings_ratio: float, annual_eps_growth_percent: float
) -> dict:
    """Calculate PEG using P/E divided by EPS growth expressed as a percent."""
    return {
        "peg_ratio": _ratio(
            price_to_earnings_ratio,
            annual_eps_growth_percent,
            "PEG ratio",
        )
    }


@tool
def portfolio_beta_calculator(
    asset_betas: list[float], portfolio_weights: list[float]
) -> dict:
    """Calculate portfolio beta from asset betas and market-value weights."""
    if not asset_betas or len(asset_betas) != len(portfolio_weights):
        raise ValueError("betas and weights must be non-empty and equal length")
    if any(weight < 0 for weight in portfolio_weights):
        raise ValueError("portfolio_weights cannot be negative")
    if not math.isclose(sum(portfolio_weights), 1.0, abs_tol=1e-7):
        raise ValueError("portfolio_weights must sum to 1")
    return {
        "portfolio_beta": sum(
            beta * weight
            for beta, weight in zip(asset_betas, portfolio_weights)
        )
    }


@tool
def price_to_earnings_ratio_calculator(
    market_price_per_share: float, earnings_per_share: float
) -> dict:
    """Calculate the price-to-earnings ratio."""
    return {
        "price_to_earnings_ratio": _ratio(
            market_price_per_share, earnings_per_share, "P/E ratio"
        )
    }


@tool
def price_to_book_ratio_calculator(
    market_price_per_share: float, book_value_per_share: float
) -> dict:
    """Calculate the price-to-book ratio."""
    return {
        "price_to_book_ratio": _ratio(
            market_price_per_share, book_value_per_share, "P/B ratio"
        )
    }


@tool
def price_to_cash_flow_ratio_calculator(
    market_capitalization: float, operating_cash_flow: float
) -> dict:
    """Calculate price-to-cash-flow using market capitalization."""
    return {
        "price_to_cash_flow_ratio": _ratio(
            market_capitalization, operating_cash_flow, "P/CF ratio"
        )
    }


@tool
def price_to_sales_ratio_calculator(
    market_capitalization: float, revenue: float
) -> dict:
    """Calculate price-to-sales using market capitalization."""
    return {
        "price_to_sales_ratio": _ratio(
            market_capitalization, revenue, "P/S ratio"
        )
    }


@tool
def quiz_dividend_calculator(
    earnings_per_share: float,
    dividend_payout_ratio: float,
    shares_owned: float = 1.0,
) -> dict:
    """Calculate dividend per share and investor dividends from EPS and payout ratio."""
    if not 0 <= dividend_payout_ratio <= 1:
        raise ValueError("dividend_payout_ratio must be between 0 and 1")
    _nonnegative(shares_owned, "shares_owned")
    dividend_per_share = earnings_per_share * dividend_payout_ratio
    return {
        "dividend_per_share": dividend_per_share,
        "total_dividend": dividend_per_share * shares_owned,
    }


@tool
def residual_income_calculator(
    net_income: float,
    beginning_common_equity: float,
    cost_of_equity: float,
) -> dict:
    """Calculate residual income after the required common-equity charge."""
    equity_charge = beginning_common_equity * cost_of_equity
    return {
        "residual_income": net_income - equity_charge,
        "equity_charge": equity_charge,
    }


@tool
def retention_ratio_calculator(
    net_income: float, common_dividends: float
) -> dict:
    """Calculate the proportion of earnings retained in the business."""
    retention = _ratio(
        net_income - common_dividends, net_income, "retention ratio"
    )
    return {"retention_ratio": retention}


@tool
def return_on_equity_calculator(
    net_income: float, average_shareholders_equity: float
) -> dict:
    """Calculate return on average shareholders' equity."""
    return {
        "return_on_equity": _ratio(
            net_income, average_shareholders_equity, "return on equity"
        )
    }


@tool
def roic_calculator(nopat: float, average_invested_capital: float) -> dict:
    """Calculate return on invested capital."""
    return {
        "return_on_invested_capital": _ratio(
            nopat, average_invested_capital, "ROIC"
        )
    }


@tool
def return_on_sales_calculator(
    operating_profit: float, net_sales: float
) -> dict:
    """Calculate operating return on sales."""
    return {
        "return_on_sales": _ratio(
            operating_profit, net_sales, "return on sales"
        )
    }


@tool
def return_on_assets_calculator(
    net_income: float, average_total_assets: float
) -> dict:
    """Calculate return on average total assets."""
    return {
        "return_on_assets": _ratio(
            net_income, average_total_assets, "return on assets"
        )
    }


@tool
def stock_calculator(
    shares: float,
    purchase_price_per_share: float,
    current_price_per_share: float,
    dividends_per_share: float = 0.0,
) -> dict:
    """Calculate a stock position's value, gain, and total return."""
    _nonnegative(shares, "shares")
    cost_basis = shares * purchase_price_per_share
    market_value = shares * current_price_per_share
    dividends = shares * dividends_per_share
    gain = market_value + dividends - cost_basis
    return {
        "cost_basis": cost_basis,
        "market_value": market_value,
        "dividends": dividends,
        "total_gain": gain,
        "total_return": gain / cost_basis if cost_basis else None,
    }


@tool
def stock_average_calculator(
    purchase_prices: list[float], shares_purchased: list[float]
) -> dict:
    """Calculate weighted-average stock cost basis across purchases."""
    if not purchase_prices or len(purchase_prices) != len(shares_purchased):
        raise ValueError("prices and share quantities must be non-empty and equal length")
    if any(shares < 0 for shares in shares_purchased):
        raise ValueError("share quantities cannot be negative")
    total_shares = sum(shares_purchased)
    _positive(total_shares, "total shares")
    total_cost = sum(
        price * shares
        for price, shares in zip(purchase_prices, shares_purchased)
    )
    return {
        "total_shares": total_shares,
        "total_cost": total_cost,
        "average_cost_per_share": total_cost / total_shares,
    }


@tool
def stock_split_calculator(
    shares_before_split: float,
    price_before_split: float,
    new_shares_for_each_old_share: float,
) -> dict:
    """Calculate post-split shares and theoretical price."""
    _nonnegative(shares_before_split, "shares_before_split")
    _nonnegative(price_before_split, "price_before_split")
    _positive(new_shares_for_each_old_share, "split ratio")
    shares_after = shares_before_split * new_shares_for_each_old_share
    price_after = price_before_split / new_shares_for_each_old_share
    return {
        "shares_after_split": shares_after,
        "theoretical_price_after_split": price_after,
        "position_value_before": shares_before_split * price_before_split,
        "position_value_after": shares_after * price_after,
    }


@tool
def sustainable_growth_rate_calculator(
    return_on_equity: float, retention_ratio: float
) -> dict:
    """Calculate sustainable growth as ROE multiplied by retention ratio."""
    return {
        "sustainable_growth_rate": return_on_equity * retention_ratio
    }


@tool
def unlevered_beta_calculator(
    levered_beta: float,
    debt_value: float,
    equity_value: float,
    tax_rate: float,
) -> dict:
    """Remove financial leverage from observed equity beta."""
    _positive(equity_value, "equity_value")
    if not 0 <= tax_rate <= 1:
        raise ValueError("tax_rate must be between 0 and 1")
    unlevered = levered_beta / (
        1 + (1 - tax_rate) * debt_value / equity_value
    )
    return {"unlevered_beta": unlevered}


@tool
def wacc_calculator(
    equity_value: float,
    debt_value: float,
    cost_of_equity: float,
    pre_tax_cost_of_debt: float,
    tax_rate: float,
    preferred_value: float = 0.0,
    cost_of_preferred: float = 0.0,
) -> dict:
    """Calculate weighted average cost of capital using market values."""
    return _wacc(
        equity_value,
        debt_value,
        cost_of_equity,
        pre_tax_cost_of_debt,
        tax_rate,
        preferred_value,
        cost_of_preferred,
    )


EQUITY_CALCULATOR_TOOLS = (
    beta_stock_calculator,
    capm_calculator,
    carried_interest_calculator,
    cost_of_capital_calculator,
    cost_of_equity_calculator,
    dividend_calculator,
    dividend_discount_model_calculator,
    dividend_payout_ratio_calculator,
    dividend_yield_calculator,
    dupont_analysis_calculator,
    earnings_per_share_calculator,
    earnings_per_share_growth_calculator,
    ebitda_multiple_calculator,
    economic_value_added_calculator,
    enterprise_value_calculator,
    ev_to_sales_calculator,
    free_float_calculator,
    graham_number_calculator,
    intrinsic_value_calculator,
    margin_of_safety_calculator,
    market_capitalization_calculator,
    maturity_value_calculator,
    nav_calculator,
    operating_cash_flow_ratio_calculator,
    peg_ratio_calculator,
    portfolio_beta_calculator,
    price_to_earnings_ratio_calculator,
    price_to_book_ratio_calculator,
    price_to_cash_flow_ratio_calculator,
    price_to_sales_ratio_calculator,
    quiz_dividend_calculator,
    residual_income_calculator,
    retention_ratio_calculator,
    return_on_equity_calculator,
    roic_calculator,
    return_on_sales_calculator,
    return_on_assets_calculator,
    stock_calculator,
    stock_average_calculator,
    stock_split_calculator,
    sustainable_growth_rate_calculator,
    unlevered_beta_calculator,
    wacc_calculator,
)

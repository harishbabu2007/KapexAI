"""Deterministic retirement and annuity calculator tools."""

import math

from langchain.tools import tool

from kapexai.tools.finance_calculators import _future_value


def _annuity_fv(payment: float, rate: float, periods: int, due: bool = False) -> float:
    value = payment * periods if rate == 0 else payment * ((1 + rate) ** periods - 1) / rate
    return value * (1 + rate) if due else value


def _annuity_pv(payment: float, rate: float, periods: int, due: bool = False) -> float:
    value = payment * periods if rate == 0 else payment * (1 - (1 + rate) ** -periods) / rate
    return value * (1 + rate) if due else value


def _withdrawal(balance: float, annual_return: float, annual_withdrawal: float, years: int) -> dict:
    values = []
    for year in range(1, years + 1):
        balance = balance * (1 + annual_return) - annual_withdrawal
        values.append({"year": year, "ending_balance": max(0.0, balance)})
        if balance <= 0:
            return {"ending_balance": 0.0, "depleted_in_year": year, "annual_values": values}
    return {"ending_balance": balance, "depleted_in_year": None, "annual_values": values}


@tool
def retirement_401k_calculator(current_balance: float, annual_salary: float, employee_contribution_rate: float, employer_match_rate: float, employer_match_limit: float, annual_return: float, years: int, employee_limit: float = 24500.0) -> dict:
    """Project a 401(k), applying configurable 2026 employee contribution limits."""
    employee = min(annual_salary * employee_contribution_rate, employee_limit)
    employer = annual_salary * min(employee_contribution_rate, employer_match_limit) * employer_match_rate
    ending = _future_value(current_balance, annual_return, years, 1, employee + employer)
    return {"ending_balance": ending, "annual_employee_contribution": employee, "annual_employer_match": employer, "assumption_year": 2026}


@tool
def annuity_calculator(principal: float, annual_rate: float, years: float, compounds_per_year: int = 12) -> dict:
    """Calculate accumulated value of an annuity investment principal."""
    ending = principal * (1 + annual_rate / compounds_per_year) ** round(years * compounds_per_year)
    return {"future_value": ending, "growth": ending - principal}


@tool
def annuity_payout_calculator(principal: float, annual_rate: float, payout_years: float, payments_per_year: int = 12, payment_at_beginning: bool = False) -> dict:
    """Calculate periodic payout that amortizes an annuity balance."""
    periods = round(payout_years * payments_per_year)
    rate = annual_rate / payments_per_year
    factor = _annuity_pv(1.0, rate, periods, payment_at_beginning)
    payment = principal / factor
    return {"periodic_payout": payment, "total_nominal_payout": payment * periods}


@tool
def deferred_annuity_calculator(principal: float, annual_return: float, deferral_years: float, payout_years: float, payments_per_year: int = 12) -> dict:
    """Calculate deferred annuity value and subsequent level payout."""
    deferred_value = principal * (1 + annual_return) ** deferral_years
    rate = annual_return / payments_per_year
    payout = deferred_value / _annuity_pv(1.0, rate, round(payout_years * payments_per_year))
    return {"value_at_payout_start": deferred_value, "periodic_payout": payout}


@tool
def early_retirement_calculator(annual_retirement_spending: float, safe_withdrawal_rate: float, current_investments: float, annual_contribution: float, annual_return: float) -> dict:
    """Estimate early-retirement target and years required to reach it."""
    target = annual_retirement_spending / safe_withdrawal_rate
    balance, years = current_investments, 0
    while balance < target and years < 100:
        balance = balance * (1 + annual_return) + annual_contribution
        years += 1
    return {"retirement_target": target, "years_to_target": years if balance >= target else None}


@tool
def future_value_of_annuity_calculator(periodic_payment: float, rate_per_period: float, periods: int, payment_at_beginning: bool = False) -> dict:
    """Calculate future value of an ordinary annuity or annuity due."""
    return {"future_value": _annuity_fv(periodic_payment, rate_per_period, periods, payment_at_beginning)}


@tool
def growing_annuity_calculator(first_payment: float, discount_rate: float, growth_rate: float, periods: int) -> dict:
    """Calculate present value of a finite growing annuity."""
    if discount_rate == growth_rate:
        value = first_payment * periods / (1 + discount_rate)
    else:
        value = first_payment / (discount_rate - growth_rate) * (1 - ((1 + growth_rate) / (1 + discount_rate)) ** periods)
    return {"present_value": value}


@tool
def immediate_annuity_calculator(principal: float, annual_rate: float, payout_years: float, payments_per_year: int = 12) -> dict:
    """Calculate level immediate-annuity payments beginning one period from now."""
    periods = round(payout_years * payments_per_year)
    payment = principal / _annuity_pv(1.0, annual_rate / payments_per_year, periods)
    return {"periodic_payout": payment}


@tool
def ira_calculator(current_balance: float, annual_contribution: float, annual_return: float, years: int, contribution_limit: float = 7500.0, catch_up_contribution: float = 0.0) -> dict:
    """Project an IRA using configurable 2026 contribution limits."""
    contribution = min(annual_contribution, contribution_limit + catch_up_contribution)
    ending = _future_value(current_balance, annual_return, years, 1, contribution)
    return {"ending_balance": ending, "annual_contribution_used": contribution, "assumption_year": 2026}


@tool
def present_value_of_annuity_calculator(periodic_payment: float, rate_per_period: float, periods: int, payment_at_beginning: bool = False) -> dict:
    """Calculate present value of an ordinary annuity or annuity due."""
    return {"present_value": _annuity_pv(periodic_payment, rate_per_period, periods, payment_at_beginning)}


@tool
def retirement_calculator(current_age: int, retirement_age: int, current_savings: float, annual_contribution: float, annual_return: float, annual_retirement_spending: float, safe_withdrawal_rate: float = 0.04) -> dict:
    """Project retirement savings and compare them with a spending target."""
    years = retirement_age - current_age
    if years < 0:
        raise ValueError("retirement_age must not precede current_age")
    projected = (
        current_savings
        if years == 0
        else _future_value(
            current_savings, annual_return, years, 1, annual_contribution
        )
    )
    target = annual_retirement_spending / safe_withdrawal_rate
    return {"projected_savings": projected, "retirement_target": target, "surplus_or_gap": projected - target}


@tool
def retirement_withdrawal_calculator(retirement_balance: float, annual_return: float, annual_withdrawal: float, retirement_years: int) -> dict:
    """Simulate fixed annual retirement withdrawals."""
    return _withdrawal(retirement_balance, annual_return, annual_withdrawal, retirement_years)


@tool
def roth_ira_calculator(current_balance: float, annual_contribution: float, annual_return: float, years: int, contribution_limit: float = 7500.0, current_marginal_tax_rate: float = 0.0) -> dict:
    """Project Roth IRA balance and current tax cost of after-tax contributions."""
    contribution = min(annual_contribution, contribution_limit)
    ending = _future_value(current_balance, annual_return, years, 1, contribution)
    return {"projected_tax_free_balance": ending, "annual_after_tax_contribution": contribution, "estimated_current_tax_on_earnings_used": contribution * current_marginal_tax_rate}


@tool
def rule_of_72_calculator(annual_return_percent: float) -> dict:
    """Estimate years required for an investment to double using the Rule of 72."""
    if annual_return_percent <= 0:
        raise ValueError("annual_return_percent must be positive")
    return {"estimated_doubling_years": 72 / annual_return_percent}


@tool
def savings_withdrawal_calculator(starting_balance: float, annual_return: float, periodic_withdrawal: float, periods_per_year: int, years: int) -> dict:
    """Simulate recurring withdrawals from savings."""
    balance = starting_balance
    rate = annual_return / periods_per_year
    periods = years * periods_per_year
    for period in range(1, periods + 1):
        balance = balance * (1 + rate) - periodic_withdrawal
        if balance <= 0:
            return {"ending_balance": 0.0, "depleted_in_period": period}
    return {"ending_balance": balance, "depleted_in_period": None}


@tool
def variable_annuity_calculator(principal: float, annual_gross_return: float, annual_expense_rate: float, annual_rider_fee_rate: float, years: float, surrender_charge: float = 0.0) -> dict:
    """Project variable-annuity account value after recurring fees."""
    net_rate = annual_gross_return - annual_expense_rate - annual_rider_fee_rate
    value = principal * (1 + net_rate) ** years
    return {"account_value": value, "value_after_surrender_charge": value - surrender_charge}


RETIREMENT_CALCULATOR_TOOLS = (
    retirement_401k_calculator, annuity_calculator, annuity_payout_calculator,
    deferred_annuity_calculator, early_retirement_calculator,
    future_value_of_annuity_calculator, growing_annuity_calculator,
    immediate_annuity_calculator, ira_calculator,
    present_value_of_annuity_calculator, retirement_calculator,
    retirement_withdrawal_calculator, roth_ira_calculator,
    rule_of_72_calculator, savings_withdrawal_calculator,
    variable_annuity_calculator,
)

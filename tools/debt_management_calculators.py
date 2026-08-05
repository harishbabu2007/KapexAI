"""Deterministic consumer debt-management calculator tools."""

import math
from typing import Any, Literal

from langchain.tools import tool

from kapexai.tools.finance_calculators import _irr
from kapexai.tools.real_estate_calculators import (
    _balance_after_payments,
    _mortgage_summary,
    _payment,
    _simulate_payoff,
)


def _positive(value: float, name: str) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")


def _consumer_loan(
    principal: float,
    annual_rate: float,
    term_months: int,
    fees: float = 0.0,
) -> dict:
    financed = principal + fees
    result = _mortgage_summary(financed, annual_rate, term_months / 12)
    return {
        "amount_financed": financed,
        "monthly_payment": result["periodic_payment"],
        "total_interest": result["total_interest"],
        "total_paid": result["total_paid"],
    }


def _credit_card_payoff(
    balance: float,
    annual_rate: float,
    monthly_payment: float,
    monthly_new_charges: float = 0.0,
) -> dict:
    monthly_rate = annual_rate / 12
    months = 0
    total_interest = 0.0
    current = balance
    while current > 1e-8 and months < 1200:
        interest = current * monthly_rate
        effective_payment = monthly_payment - monthly_new_charges
        principal_paid = effective_payment - interest
        if principal_paid <= 0:
            raise ValueError("payment does not exceed interest and new charges")
        current = max(0.0, current - principal_paid)
        total_interest += interest
        months += 1
    return {
        "months_to_payoff": months if current <= 1e-8 else None,
        "years_to_payoff": months / 12 if current <= 1e-8 else None,
        "total_interest": total_interest,
        "total_payments": balance + total_interest,
    }


def _debt_strategy(
    debts: list[dict[str, Any]],
    extra_monthly_payment: float,
    method: Literal["avalanche", "snowball"],
) -> dict:
    if not debts:
        raise ValueError("At least one debt is required")
    states = [
        {
            "name": str(item.get("name", f"Debt {index + 1}")),
            "balance": float(item["balance"]),
            "annual_rate": float(item["annual_rate"]),
            "minimum_payment": float(item["minimum_payment"]),
        }
        for index, item in enumerate(debts)
    ]
    total_interest = 0.0
    months = 0
    payoff_order = []
    monthly_budget = (
        sum(item["minimum_payment"] for item in states)
        + extra_monthly_payment
    )
    while any(item["balance"] > 1e-8 for item in states) and months < 1200:
        active = [item for item in states if item["balance"] > 1e-8]
        for item in active:
            interest = item["balance"] * item["annual_rate"] / 12
            total_interest += interest
            item["balance"] += interest
        paid_this_month = 0.0
        for item in active:
            base_payment = min(item["balance"], item["minimum_payment"])
            item["balance"] -= base_payment
            paid_this_month += base_payment
        rollover = max(0.0, monthly_budget - paid_this_month)
        remaining = [item for item in active if item["balance"] > 1e-8]
        if method == "avalanche":
            remaining.sort(
                key=lambda item: (item["annual_rate"], item["balance"]),
                reverse=True,
            )
        else:
            remaining.sort(
                key=lambda item: (item["balance"], -item["annual_rate"])
            )
        for target in remaining:
            target_payment = min(target["balance"], rollover)
            target["balance"] -= target_payment
            rollover -= target_payment
            if rollover <= 1e-8:
                break
        newly_paid = [
            item["name"]
            for item in active
            if item["balance"] <= 1e-8 and item["name"] not in payoff_order
        ]
        payoff_order.extend(newly_paid)
        months += 1
    return {
        "method": method,
        "months_to_payoff": months,
        "total_interest": total_interest,
        "payoff_order": payoff_order,
    }


@tool
def ten_one_arm_calculator(
    loan_amount: float,
    initial_annual_rate: float,
    total_term_years: float,
    first_adjusted_annual_rate: float,
) -> dict:
    """Calculate initial and first adjusted payments for a 10/1 ARM."""
    initial_months = 120
    total_months = round(total_term_years * 12)
    initial_payment = _payment(loan_amount, initial_annual_rate, total_months)
    balance = _balance_after_payments(
        loan_amount, initial_annual_rate, initial_payment, initial_months
    )
    adjusted_payment = _payment(
        balance, first_adjusted_annual_rate, total_months - initial_months
    )
    return {
        "initial_monthly_payment": initial_payment,
        "balance_after_10_years": balance,
        "first_adjusted_monthly_payment": adjusted_payment,
    }


@tool
def twenty_eight_thirty_six_rule_calculator(
    gross_monthly_income: float, monthly_nonhousing_debt: float
) -> dict:
    """Calculate 28% front-end and 36% back-end housing limits."""
    front_end = gross_monthly_income * 0.28
    back_end = gross_monthly_income * 0.36 - monthly_nonhousing_debt
    return {
        "front_end_housing_limit": front_end,
        "back_end_housing_limit": back_end,
        "recommended_maximum_housing_payment": max(0.0, min(front_end, back_end)),
    }


@tool
def amortization_calculator(
    principal: float,
    annual_rate: float,
    term_months: int,
    preview_months: int = 12,
) -> dict:
    """Calculate loan payment and an amortization schedule preview."""
    payment = _payment(principal, annual_rate, term_months)
    balance = principal
    monthly_rate = annual_rate / 12
    rows = []
    for month in range(1, min(term_months, preview_months) + 1):
        interest = balance * monthly_rate
        principal_paid = payment - interest
        balance = max(0.0, balance - principal_paid)
        rows.append(
            {
                "month": month,
                "payment": payment,
                "principal": principal_paid,
                "interest": interest,
                "balance": balance,
            }
        )
    return {"monthly_payment": payment, "schedule_preview": rows}


@tool
def apr_calculator(
    amount_received: float,
    monthly_payment: float,
    term_months: int,
) -> dict:
    """Calculate effective APR from net loan proceeds and periodic payments."""
    _positive(amount_received, "amount_received")
    cash_flows = [amount_received] + [-monthly_payment] * term_months
    monthly_irr = _irr(cash_flows)
    return {
        "monthly_rate": monthly_irr,
        "nominal_apr": monthly_irr * 12,
        "effective_annual_rate": (1 + monthly_irr) ** 12 - 1,
    }


@tool
def balance_transfer_calculator(
    transferred_balance: float,
    transfer_fee_rate: float,
    promotional_annual_rate: float,
    promotional_months: int,
    monthly_payment: float,
    post_promotional_annual_rate: float,
) -> dict:
    """Estimate payoff cost for a credit-card balance transfer."""
    starting = transferred_balance * (1 + transfer_fee_rate)
    balance = starting
    interest = 0.0
    for month in range(1200):
        rate = (
            promotional_annual_rate
            if month < promotional_months
            else post_promotional_annual_rate
        ) / 12
        charge = balance * rate
        interest += charge
        balance += charge
        balance -= min(balance, monthly_payment)
        if balance <= 1e-8:
            return {
                "starting_balance_with_fee": starting,
                "months_to_payoff": month + 1,
                "total_interest": interest,
                "transfer_fee": transferred_balance * transfer_fee_rate,
            }
    return {"months_to_payoff": None, "remaining_balance": balance}


@tool
def balloon_payment_calculator(
    principal: float,
    annual_rate: float,
    amortization_term_months: int,
    balloon_due_month: int,
) -> dict:
    """Calculate periodic payment and remaining balloon balance."""
    payment = _payment(principal, annual_rate, amortization_term_months)
    balance = _balance_after_payments(
        principal, annual_rate, payment, balloon_due_month
    )
    return {"monthly_payment": payment, "balloon_payment": balance}


@tool
def blended_rate_calculator(
    balances: list[float], annual_rates: list[float]
) -> dict:
    """Calculate a balance-weighted blended annual interest rate."""
    if not balances or len(balances) != len(annual_rates):
        raise ValueError("balances and rates must be non-empty and equal length")
    total = sum(balances)
    _positive(total, "total balance")
    blended = sum(
        balance * rate for balance, rate in zip(balances, annual_rates)
    ) / total
    return {"total_balance": total, "blended_annual_rate": blended}


@tool
def car_refinance_calculator(
    current_balance: float,
    current_annual_rate: float,
    current_remaining_months: int,
    new_annual_rate: float,
    new_term_months: int,
    refinance_fees: float = 0.0,
) -> dict:
    """Compare current auto loan with a refinance offer."""
    current = _consumer_loan(
        current_balance, current_annual_rate, current_remaining_months
    )
    new = _consumer_loan(
        current_balance, new_annual_rate, new_term_months, refinance_fees
    )
    return {
        "current": current,
        "refinance": new,
        "monthly_payment_change": new["monthly_payment"]
        - current["monthly_payment"],
        "total_cost_savings": current["total_paid"] - new["total_paid"],
    }


@tool
def cash_out_refinance_calculator(
    home_value: float,
    current_mortgage_balance: float,
    maximum_ltv: float,
    new_annual_rate: float,
    new_term_years: float,
    closing_costs: float = 0.0,
) -> dict:
    """Estimate maximum cash proceeds and payment from a cash-out refinance."""
    maximum_new_loan = home_value * maximum_ltv
    cash_out = maximum_new_loan - current_mortgage_balance - closing_costs
    loan = _mortgage_summary(
        maximum_new_loan, new_annual_rate, new_term_years
    )
    return {
        "maximum_new_loan": maximum_new_loan,
        "estimated_cash_out": max(0.0, cash_out),
        "new_monthly_payment": loan["periodic_payment"],
    }


@tool
def credit_card_calculator(
    balance: float,
    annual_rate: float,
    monthly_payment: float,
    monthly_new_charges: float = 0.0,
) -> dict:
    """Calculate credit-card payoff time and interest."""
    return _credit_card_payoff(
        balance, annual_rate, monthly_payment, monthly_new_charges
    )


@tool
def credit_card_interest_calculator(
    average_daily_balance: float,
    annual_rate: float,
    billing_cycle_days: int,
) -> dict:
    """Estimate credit-card interest using average daily balance."""
    daily_rate = annual_rate / 365
    charge = average_daily_balance * daily_rate * billing_cycle_days
    return {"daily_periodic_rate": daily_rate, "finance_charge": charge}


@tool
def credit_card_minimum_payment_calculator(
    statement_balance: float,
    percentage_of_balance: float = 0.02,
    interest_and_fees: float = 0.0,
    minimum_floor: float = 25.0,
) -> dict:
    """Estimate a credit-card minimum payment."""
    calculated = max(
        statement_balance * percentage_of_balance,
        interest_and_fees + statement_balance * 0.01,
        minimum_floor,
    )
    return {"minimum_payment": min(statement_balance + interest_and_fees, calculated)}


@tool
def credit_card_payment_calculator(
    balance: float,
    annual_rate: float,
    payoff_months: int,
) -> dict:
    """Calculate monthly payment required to clear a card balance."""
    payment = _payment(balance, annual_rate, payoff_months)
    return {
        "required_monthly_payment": payment,
        "total_interest": payment * payoff_months - balance,
    }


@tool
def credit_card_payoff_calculator(
    balance: float,
    annual_rate: float,
    monthly_payment: float,
) -> dict:
    """Calculate credit-card payoff period and total interest."""
    return _credit_card_payoff(balance, annual_rate, monthly_payment)


@tool
def home_improvement_loan_calculator(
    project_cost: float,
    down_payment: float,
    annual_rate: float,
    term_months: int,
) -> dict:
    """Calculate a home-improvement loan payment."""
    return _consumer_loan(
        project_cost - down_payment, annual_rate, term_months
    )


@tool
def home_loan_calculator(
    principal: float, annual_rate: float, term_years: float
) -> dict:
    """Calculate home-loan payment and total interest."""
    return _mortgage_summary(principal, annual_rate, term_years)


@tool
def land_loan_calculator(
    land_price: float,
    down_payment: float,
    annual_rate: float,
    term_years: float,
) -> dict:
    """Calculate land-loan payment from price and down payment."""
    return _mortgage_summary(
        land_price - down_payment, annual_rate, term_years
    )


@tool
def lease_calculator(
    asset_price: float,
    residual_value: float,
    lease_months: int,
    money_factor: float,
    upfront_payment: float = 0.0,
    fees: float = 0.0,
) -> dict:
    """Calculate a generic asset lease payment."""
    adjusted_cost = asset_price + fees - upfront_payment
    depreciation = (adjusted_cost - residual_value) / lease_months
    finance = (adjusted_cost + residual_value) * money_factor
    return {
        "monthly_payment": depreciation + finance,
        "monthly_depreciation": depreciation,
        "monthly_finance_charge": finance,
    }


@tool
def lease_mileage_calculator(
    allowed_miles_per_year: float,
    lease_years: float,
    actual_or_expected_miles: float,
    excess_mileage_charge: float,
) -> dict:
    """Calculate vehicle lease excess-mileage charges."""
    allowance = allowed_miles_per_year * lease_years
    excess = max(0.0, actual_or_expected_miles - allowance)
    return {
        "total_mileage_allowance": allowance,
        "excess_miles": excess,
        "excess_mileage_charge": excess * excess_mileage_charge,
    }


@tool
def loan_calculator(
    principal: float, annual_rate: float, term_months: int, fees: float = 0.0
) -> dict:
    """Calculate a general amortizing loan."""
    return _consumer_loan(principal, annual_rate, term_months, fees)


@tool
def loan_balance_calculator(
    original_principal: float,
    annual_rate: float,
    original_term_months: int,
    payments_made: int,
) -> dict:
    """Calculate remaining balance after a number of scheduled payments."""
    payment = _payment(
        original_principal, annual_rate, original_term_months
    )
    balance = _balance_after_payments(
        original_principal, annual_rate, payment, payments_made
    )
    return {"scheduled_payment": payment, "remaining_balance": balance}


@tool
def loan_comparison_calculator(
    principal: float,
    option_a_rate: float,
    option_a_months: int,
    option_a_fees: float,
    option_b_rate: float,
    option_b_months: int,
    option_b_fees: float,
) -> dict:
    """Compare payments and total costs of two loans."""
    a = _consumer_loan(principal, option_a_rate, option_a_months, option_a_fees)
    b = _consumer_loan(principal, option_b_rate, option_b_months, option_b_fees)
    return {
        "option_a": a,
        "option_b": b,
        "lower_total_cost_option": "A" if a["total_paid"] < b["total_paid"] else "B",
    }


@tool
def loan_interest_calculator(
    principal: float,
    annual_rate: float,
    term_months: int,
) -> dict:
    """Calculate total interest on an amortizing loan."""
    result = _consumer_loan(principal, annual_rate, term_months)
    return {"total_interest": result["total_interest"]}


@tool
def loan_payment_calculator(
    principal: float,
    annual_rate: float,
    term_months: int,
) -> dict:
    """Calculate required monthly loan payment."""
    return {"monthly_payment": _payment(principal, annual_rate, term_months)}


@tool
def loan_repayment_payoff_calculator(
    balance: float,
    annual_rate: float,
    monthly_payment: float,
    extra_monthly_payment: float = 0.0,
) -> dict:
    """Calculate loan payoff with optional extra monthly payments."""
    return _simulate_payoff(
        balance,
        annual_rate,
        monthly_payment,
        extra_monthly_payment,
    )


@tool
def mortgage_interest_calculator(
    principal: float,
    annual_rate: float,
    term_years: float,
) -> dict:
    """Calculate total mortgage interest over the scheduled term."""
    result = _mortgage_summary(principal, annual_rate, term_years)
    return {
        "monthly_payment": result["periodic_payment"],
        "total_interest": result["total_interest"],
    }


@tool
def partially_amortized_loan_calculator(
    principal: float,
    annual_rate: float,
    amortization_months: int,
    maturity_months: int,
) -> dict:
    """Calculate payment and balloon balance for a partially amortized loan."""
    payment = _payment(principal, annual_rate, amortization_months)
    balloon = _balance_after_payments(
        principal, annual_rate, payment, maturity_months
    )
    return {"monthly_payment": payment, "balloon_balance": balloon}


@tool
def paycheck_protection_program_loan_calculator(
    average_monthly_payroll: float,
    payroll_multiplier: float = 2.5,
    loan_cap: float = 10000000.0,
    eligible_forgiveness_costs: float = 0.0,
    payroll_cost_share: float = 0.60,
) -> dict:
    """Estimate historical PPP loan size and forgiveness from supplied costs."""
    loan_amount = min(average_monthly_payroll * payroll_multiplier, loan_cap)
    maximum_forgiveness = min(loan_amount, eligible_forgiveness_costs)
    return {
        "estimated_loan_amount": loan_amount,
        "maximum_forgiveness_before_other_reductions": maximum_forgiveness,
        "required_payroll_cost_share": payroll_cost_share,
        "historical_program": "PPP ended May 31, 2021",
    }


@tool
def credit_utilization_calculator(
    card_balances: list[float], credit_limits: list[float]
) -> dict:
    """Calculate aggregate and per-card credit utilization."""
    if not card_balances or len(card_balances) != len(credit_limits):
        raise ValueError("balances and limits must be non-empty and equal length")
    total_balance = sum(card_balances)
    total_limit = sum(credit_limits)
    _positive(total_limit, "total credit limit")
    return {
        "aggregate_utilization": total_balance / total_limit,
        "per_card_utilization": [
            balance / limit if limit else None
            for balance, limit in zip(card_balances, credit_limits)
        ],
    }


@tool
def debt_calculator(debts: list[dict[str, Any]]) -> dict:
    """Summarize balances, payments, and blended rate across debts."""
    total_balance = sum(item["balance"] for item in debts)
    total_payment = sum(item["minimum_payment"] for item in debts)
    blended = (
        sum(item["balance"] * item["annual_rate"] for item in debts)
        / total_balance
        if total_balance
        else 0.0
    )
    return {
        "total_debt": total_balance,
        "total_minimum_payment": total_payment,
        "blended_annual_rate": blended,
    }


@tool
def debt_avalanche_calculator(
    debts: list[dict[str, Any]], extra_monthly_payment: float
) -> dict:
    """Model highest-interest-first debt payoff."""
    return _debt_strategy(debts, extra_monthly_payment, "avalanche")


@tool
def debt_consolidation_calculator(
    debts: list[dict[str, Any]],
    consolidation_annual_rate: float,
    consolidation_term_months: int,
    consolidation_fees: float = 0.0,
) -> dict:
    """Compare current debt payment totals with a consolidation loan."""
    summary = debt_calculator.invoke({"debts": debts})
    consolidated = _consumer_loan(
        summary["total_debt"],
        consolidation_annual_rate,
        consolidation_term_months,
        consolidation_fees,
    )
    return {
        "current": summary,
        "consolidation": consolidated,
        "monthly_payment_change": consolidated["monthly_payment"]
        - summary["total_minimum_payment"],
    }


@tool
def debt_payoff_calculator(
    total_balance: float,
    blended_annual_rate: float,
    monthly_payment: float,
) -> dict:
    """Calculate payoff time for an aggregate debt balance."""
    return _simulate_payoff(
        total_balance, blended_annual_rate, monthly_payment
    )


@tool
def debt_snowball_calculator(
    debts: list[dict[str, Any]], extra_monthly_payment: float
) -> dict:
    """Model smallest-balance-first debt payoff."""
    return _debt_strategy(debts, extra_monthly_payment, "snowball")


@tool
def debt_to_income_ratio_calculator(
    monthly_debt_payments: float, gross_monthly_income: float
) -> dict:
    """Calculate monthly debt-to-income ratio."""
    _positive(gross_monthly_income, "gross_monthly_income")
    ratio = monthly_debt_payments / gross_monthly_income
    return {"debt_to_income_ratio": ratio, "debt_to_income_percent": ratio * 100}


@tool
def deferred_payment_loan_calculator(
    principal: float,
    annual_rate: float,
    deferral_months: int,
    repayment_months: int,
    interest_accrues_during_deferral: bool = True,
) -> dict:
    """Calculate balance after payment deferral and later monthly payment."""
    balance = (
        principal * (1 + annual_rate / 12) ** deferral_months
        if interest_accrues_during_deferral
        else principal
    )
    payment = _payment(balance, annual_rate, repayment_months)
    return {
        "balance_after_deferral": balance,
        "monthly_payment_after_deferral": payment,
    }


@tool
def eidl_emergency_advance_calculator(
    eligible_employees: int,
    advance_per_employee: float = 1000.0,
    maximum_advance: float = 10000.0,
) -> dict:
    """Estimate historical EIDL Emergency Advance amount."""
    return {
        "estimated_advance": min(
            eligible_employees * advance_per_employee, maximum_advance
        ),
        "historical_program": True,
    }


@tool
def finance_charge_calculator(
    principal_or_balance: float,
    annual_rate: float,
    days: int,
    fees: float = 0.0,
    day_count_basis: int = 365,
) -> dict:
    """Calculate simple-period finance charge plus fees."""
    interest = principal_or_balance * annual_rate * days / day_count_basis
    return {"interest": interest, "fees": fees, "finance_charge": interest + fees}


@tool
def heloc_calculator(
    credit_line: float,
    amount_drawn: float,
    annual_rate: float,
    interest_only_draw_months: int,
    repayment_months: int,
) -> dict:
    """Calculate HELOC draw-period interest payment and later repayment payment."""
    interest_only_payment = amount_drawn * annual_rate / 12
    repayment_payment = _payment(
        amount_drawn, annual_rate, repayment_months
    )
    return {
        "available_credit": credit_line - amount_drawn,
        "interest_only_monthly_payment": interest_only_payment,
        "repayment_monthly_payment": repayment_payment,
        "draw_period_interest": interest_only_payment
        * interest_only_draw_months,
    }


@tool
def payday_loan_calculator(
    amount_borrowed: float,
    finance_fee: float,
    loan_days: int,
) -> dict:
    """Calculate payday-loan cost and effective APR."""
    _positive(amount_borrowed, "amount_borrowed")
    _positive(loan_days, "loan_days")
    apr = finance_fee / amount_borrowed * 365 / loan_days
    return {
        "repayment_amount": amount_borrowed + finance_fee,
        "effective_apr": apr,
        "effective_apr_percent": apr * 100,
    }


@tool
def personal_loan_calculator(
    principal: float, annual_rate: float, term_months: int, origination_fee: float = 0.0
) -> dict:
    """Calculate personal-loan payment and total cost."""
    return _consumer_loan(principal, annual_rate, term_months, origination_fee)


@tool
def piti_calculator(
    principal_and_interest: float,
    annual_property_tax: float,
    annual_homeowners_insurance: float,
    monthly_mortgage_insurance: float = 0.0,
    monthly_hoa: float = 0.0,
) -> dict:
    """Calculate total monthly principal, interest, taxes, and insurance."""
    total = (
        principal_and_interest
        + annual_property_tax / 12
        + annual_homeowners_insurance / 12
        + monthly_mortgage_insurance
        + monthly_hoa
    )
    return {"monthly_piti_and_fees": total}


@tool
def post_judgment_interest_calculator(
    judgment_amount: float,
    annual_interest_rate: float,
    days_outstanding: int,
    payments_or_credits: float = 0.0,
) -> dict:
    """Estimate simple post-judgment interest using a supplied legal rate."""
    interest = judgment_amount * annual_interest_rate * days_outstanding / 365
    return {
        "accrued_interest": interest,
        "estimated_balance": judgment_amount + interest - payments_or_credits,
        "caution": "Compounding, rate changes, and court rules vary by jurisdiction.",
    }


@tool
def quiz_loan_balance_calculator(
    original_principal: float,
    annual_rate: float,
    original_term_months: int,
    payments_made: int,
) -> dict:
    """Calculate the scheduled remaining loan balance."""
    payment = _payment(
        original_principal, annual_rate, original_term_months
    )
    return {
        "remaining_balance": _balance_after_payments(
            original_principal, annual_rate, payment, payments_made
        )
    }


@tool
def refinance_calculator(
    current_balance: float,
    current_annual_rate: float,
    current_remaining_months: int,
    new_annual_rate: float,
    new_term_months: int,
    refinance_costs: float,
) -> dict:
    """Compare current debt with a refinance option."""
    current = _consumer_loan(
        current_balance, current_annual_rate, current_remaining_months
    )
    new = _consumer_loan(
        current_balance, new_annual_rate, new_term_months, refinance_costs
    )
    savings = current["monthly_payment"] - new["monthly_payment"]
    return {
        "current": current,
        "refinance": new,
        "monthly_savings": savings,
        "break_even_months": refinance_costs / savings if savings > 0 else None,
    }


@tool
def refinance_break_even_calculator(
    refinance_costs: float, monthly_payment_savings: float
) -> dict:
    """Calculate refinance break-even time."""
    if monthly_payment_savings <= 0:
        return {"break_even_months": None}
    return {
        "break_even_months": refinance_costs / monthly_payment_savings,
        "break_even_years": refinance_costs / monthly_payment_savings / 12,
    }


@tool
def rv_loan_calculator(
    rv_price: float,
    down_payment: float,
    annual_rate: float,
    term_months: int,
    fees: float = 0.0,
) -> dict:
    """Calculate recreational-vehicle loan payment and total interest."""
    return _consumer_loan(
        rv_price - down_payment, annual_rate, term_months, fees
    )


@tool
def student_loan_calculator(
    loan_balance: float,
    annual_rate: float,
    term_years: float,
) -> dict:
    """Calculate standard student-loan payment and total interest."""
    return _consumer_loan(
        loan_balance, annual_rate, round(term_years * 12)
    )


@tool
def student_loan_forgiveness_calculator(
    current_balance: float,
    annual_rate: float,
    monthly_payment: float,
    qualifying_payments_required: int,
    qualifying_payments_already_made: int = 0,
) -> dict:
    """Estimate remaining balance potentially forgiven after qualifying payments."""
    remaining_payments = max(
        0, qualifying_payments_required - qualifying_payments_already_made
    )
    balance = current_balance
    for _ in range(remaining_payments):
        balance = max(
            0.0,
            balance * (1 + annual_rate / 12) - monthly_payment,
        )
    return {
        "remaining_qualifying_payments": remaining_payments,
        "estimated_balance_at_forgiveness": balance,
        "caution": "Eligibility and qualifying-payment rules require current Federal Student Aid verification.",
    }


@tool
def student_loan_payment_calculator(
    loan_balance: float,
    annual_rate: float,
    repayment_months: int,
) -> dict:
    """Calculate required monthly student-loan payment."""
    return {
        "monthly_payment": _payment(
            loan_balance, annual_rate, repayment_months
        )
    }


@tool
def student_loan_repayment_covid19_calculator(
    balance_at_pause_start: float,
    paused_months: int,
    regular_annual_rate: float,
    payment_during_pause: float = 0.0,
    pause_interest_rate: float = 0.0,
) -> dict:
    """Model the historical COVID-19 federal student-loan payment pause."""
    balance = balance_at_pause_start
    for _ in range(paused_months):
        balance = max(
            0.0,
            balance * (1 + pause_interest_rate / 12)
            - payment_during_pause,
        )
    avoided_interest = (
        balance_at_pause_start
        * regular_annual_rate
        / 12
        * paused_months
    )
    return {
        "balance_after_pause": balance,
        "estimated_interest_avoided": avoided_interest,
        "historical_program": True,
    }


DEBT_MANAGEMENT_CALCULATOR_TOOLS = (
    ten_one_arm_calculator,
    twenty_eight_thirty_six_rule_calculator,
    amortization_calculator,
    apr_calculator,
    balance_transfer_calculator,
    balloon_payment_calculator,
    blended_rate_calculator,
    car_refinance_calculator,
    cash_out_refinance_calculator,
    credit_card_calculator,
    credit_card_interest_calculator,
    credit_card_minimum_payment_calculator,
    credit_card_payment_calculator,
    credit_card_payoff_calculator,
    home_improvement_loan_calculator,
    home_loan_calculator,
    land_loan_calculator,
    lease_calculator,
    lease_mileage_calculator,
    loan_calculator,
    loan_balance_calculator,
    loan_comparison_calculator,
    loan_interest_calculator,
    loan_payment_calculator,
    loan_repayment_payoff_calculator,
    mortgage_interest_calculator,
    partially_amortized_loan_calculator,
    paycheck_protection_program_loan_calculator,
    credit_utilization_calculator,
    debt_calculator,
    debt_avalanche_calculator,
    debt_consolidation_calculator,
    debt_payoff_calculator,
    debt_snowball_calculator,
    debt_to_income_ratio_calculator,
    deferred_payment_loan_calculator,
    eidl_emergency_advance_calculator,
    finance_charge_calculator,
    heloc_calculator,
    payday_loan_calculator,
    personal_loan_calculator,
    piti_calculator,
    post_judgment_interest_calculator,
    quiz_loan_balance_calculator,
    refinance_calculator,
    refinance_break_even_calculator,
    rv_loan_calculator,
    student_loan_calculator,
    student_loan_forgiveness_calculator,
    student_loan_payment_calculator,
    student_loan_repayment_covid19_calculator,
)

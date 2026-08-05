"""Deterministic personal-finance calculator tools."""

import math
from typing import Any

from langchain.tools import tool

from kapexai.tools.finance_calculators import _future_value
from kapexai.tools.real_estate_calculators import _mortgage_summary


def _nonnegative(value: float, name: str) -> None:
    if value < 0:
        raise ValueError(f"{name} must be zero or greater")


def _positive(value: float, name: str) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")


def _loan(
    purchase_price: float,
    down_payment: float,
    trade_in_or_credit: float,
    annual_rate: float,
    term_months: int,
    fees: float = 0.0,
) -> dict:
    principal = purchase_price + fees - down_payment - trade_in_or_credit
    result = _mortgage_summary(
        principal, annual_rate, term_months / 12
    )
    return {
        "amount_financed": principal,
        "monthly_payment": result["periodic_payment"],
        "total_interest": result["total_interest"],
        "total_paid": result["total_paid"] + down_payment,
    }


def _relief_payment(
    adjusted_gross_income: float,
    base_payment: float,
    dependent_count: int,
    dependent_payment: float,
    phaseout_start: float,
    phaseout_rate: float,
    income_cap: float | None = None,
) -> dict:
    if income_cap is not None and adjusted_gross_income > income_cap:
        payment = 0.0
    else:
        gross = base_payment + dependent_count * dependent_payment
        reduction = max(0.0, adjusted_gross_income - phaseout_start) * phaseout_rate
        payment = max(0.0, gross - reduction)
    return {
        "estimated_payment": payment,
        "historical_policy_scenario": True,
    }


def _income_percentile(
    annual_income: float,
    percentile_thresholds: list[dict[str, float]],
) -> dict:
    if not percentile_thresholds:
        raise ValueError("percentile_thresholds cannot be empty")
    ordered = sorted(percentile_thresholds, key=lambda item: item["income"])
    percentile = 0.0
    for item in ordered:
        if annual_income >= item["income"]:
            percentile = item["percentile"]
        else:
            break
    return {
        "estimated_percentile": percentile,
        "income": annual_income,
        "caution": "Percentile quality depends on the supplied dataset and year.",
    }


def _metal_value(
    weight: float,
    purity: float,
    spot_price_per_unit: float,
    dealer_discount_rate: float = 0.0,
) -> dict:
    pure_weight = weight * purity
    melt_value = pure_weight * spot_price_per_unit
    return {
        "pure_metal_weight": pure_weight,
        "melt_value": melt_value,
        "estimated_dealer_payout": melt_value * (1 - dealer_discount_rate),
    }


@tool
def retirement_403b_calculator(
    current_balance: float,
    annual_employee_contribution: float,
    annual_employer_contribution: float,
    annual_return: float,
    years: int,
    annual_contribution_limit: float = 24500.0,
) -> dict:
    """Project a 403(b) balance using configurable 2026 contribution limits."""
    employee = min(annual_employee_contribution, annual_contribution_limit)
    annual_contribution = employee + annual_employer_contribution
    ending = _future_value(
        current_balance, annual_return, years, 1, annual_contribution
    )
    return {
        "ending_balance": ending,
        "employee_contribution_used": employee,
        "annual_total_contribution": annual_contribution,
        "assumption_year": 2026,
    }


@tool
def fifty_thirty_twenty_rule_calculator(
    monthly_after_tax_income: float
) -> dict:
    """Allocate after-tax income under the 50/30/20 budget rule."""
    return {
        "needs": monthly_after_tax_income * 0.50,
        "wants": monthly_after_tax_income * 0.30,
        "savings_and_debt": monthly_after_tax_income * 0.20,
    }


@tool
def education_529_calculator(
    current_balance: float,
    monthly_contribution: float,
    annual_return: float,
    years_until_college: float,
    current_annual_college_cost: float,
    annual_education_inflation: float,
    years_of_college: int = 4,
) -> dict:
    """Project a 529 balance and compare it with inflation-adjusted college cost."""
    balance = _future_value(
        current_balance,
        annual_return,
        years_until_college,
        12,
        monthly_contribution,
    )
    first_year_cost = current_annual_college_cost * (
        1 + annual_education_inflation
    ) ** years_until_college
    total_cost = sum(
        first_year_cost * (1 + annual_education_inflation) ** year
        for year in range(years_of_college)
    )
    return {
        "projected_529_balance": balance,
        "projected_college_cost": total_cost,
        "funding_gap_or_surplus": balance - total_cost,
    }


@tool
def seventy_twenty_ten_rule_money_calculator(
    monthly_after_tax_income: float
) -> dict:
    """Allocate income under the 70/20/10 spending, saving, and giving rule."""
    return {
        "living_expenses": monthly_after_tax_income * 0.70,
        "savings_and_debt": monthly_after_tax_income * 0.20,
        "giving_or_investing": monthly_after_tax_income * 0.10,
    }


@tool
def apc_calculator(consumption: float, disposable_income: float) -> dict:
    """Calculate average propensity to consume."""
    _positive(disposable_income, "disposable_income")
    return {
        "average_propensity_to_consume": consumption / disposable_income,
        "average_propensity_to_save": 1 - consumption / disposable_income,
    }


@tool
def auto_loan_calculator(
    vehicle_price: float,
    down_payment: float,
    trade_in_value: float,
    annual_interest_rate: float,
    term_months: int,
    taxes_and_fees: float = 0.0,
) -> dict:
    """Calculate automobile loan payment and total financing cost."""
    return _loan(
        vehicle_price,
        down_payment,
        trade_in_value,
        annual_interest_rate,
        term_months,
        taxes_and_fees,
    )


@tool
def bank_reconciliation_calculator(
    bank_statement_balance: float,
    deposits_in_transit: float,
    outstanding_checks: float,
    bank_errors: float,
    book_balance: float,
    bank_fees: float,
    interest_earned: float,
    book_errors: float,
) -> dict:
    """Reconcile bank statement and book cash balances."""
    adjusted_bank = (
        bank_statement_balance
        + deposits_in_transit
        - outstanding_checks
        + bank_errors
    )
    adjusted_book = book_balance - bank_fees + interest_earned + book_errors
    return {
        "adjusted_bank_balance": adjusted_bank,
        "adjusted_book_balance": adjusted_book,
        "difference": adjusted_bank - adjusted_book,
        "reconciled": math.isclose(adjusted_bank, adjusted_book, abs_tol=0.01),
    }


@tool
def boat_loan_calculator(
    boat_price: float,
    down_payment: float,
    annual_interest_rate: float,
    term_months: int,
    fees: float = 0.0,
) -> dict:
    """Calculate boat loan payment and total interest."""
    return _loan(
        boat_price, down_payment, 0.0, annual_interest_rate, term_months, fees
    )


@tool
def budget_calculator(
    monthly_income: float,
    expense_categories: dict[str, float],
    savings_target: float = 0.0,
) -> dict:
    """Calculate monthly budget surplus and category shares."""
    expenses = sum(expense_categories.values())
    surplus = monthly_income - expenses - savings_target
    return {
        "total_expenses": expenses,
        "savings_target": savings_target,
        "surplus_or_shortfall": surplus,
        "expense_shares": {
            category: amount / monthly_income if monthly_income else None
            for category, amount in expense_categories.items()
        },
    }


@tool
def car_affordability_calculator(
    monthly_after_tax_income: float,
    monthly_debt_payments: float,
    down_payment: float,
    annual_interest_rate: float,
    term_months: int,
    maximum_transportation_share: float = 0.15,
    monthly_insurance_and_fuel: float = 0.0,
) -> dict:
    """Estimate affordable vehicle price from a monthly transportation budget."""
    payment_budget = (
        monthly_after_tax_income * maximum_transportation_share
        - monthly_debt_payments
        - monthly_insurance_and_fuel
    )
    if payment_budget <= 0:
        return {"affordable_vehicle_price": 0.0, "monthly_loan_budget": 0.0}
    monthly_rate = annual_interest_rate / 12
    if monthly_rate == 0:
        loan = payment_budget * term_months
    else:
        loan = payment_budget * (
            1 - (1 + monthly_rate) ** -term_months
        ) / monthly_rate
    return {
        "monthly_loan_budget": payment_budget,
        "affordable_loan_amount": loan,
        "affordable_vehicle_price": loan + down_payment,
    }


@tool
def car_depreciation_calculator(
    purchase_price: float,
    first_year_depreciation_rate: float,
    later_annual_depreciation_rate: float,
    years: int,
) -> dict:
    """Project vehicle value using first-year and later depreciation rates."""
    value = purchase_price
    values = []
    for year in range(1, years + 1):
        rate = (
            first_year_depreciation_rate
            if year == 1
            else later_annual_depreciation_rate
        )
        value *= 1 - rate
        values.append({"year": year, "value": value})
    return {
        "estimated_value": value,
        "total_depreciation": purchase_price - value,
        "annual_values": values,
    }


@tool
def car_lease_calculator(
    msrp: float,
    negotiated_price: float,
    residual_rate: float,
    money_factor: float,
    lease_months: int,
    down_payment: float = 0.0,
    fees: float = 0.0,
    sales_tax_rate: float = 0.0,
) -> dict:
    """Calculate an estimated vehicle lease payment."""
    residual_value = msrp * residual_rate
    adjusted_cap_cost = negotiated_price + fees - down_payment
    depreciation_charge = (
        adjusted_cap_cost - residual_value
    ) / lease_months
    finance_charge = (adjusted_cap_cost + residual_value) * money_factor
    pretax_payment = depreciation_charge + finance_charge
    return {
        "residual_value": residual_value,
        "depreciation_charge": depreciation_charge,
        "finance_charge": finance_charge,
        "monthly_payment": pretax_payment * (1 + sales_tax_rate),
    }


@tool
def second_stimulus_cash_act_calculator(
    adjusted_gross_income: float,
    dependents: int = 0,
    base_payment: float = 2000.0,
    dependent_payment: float = 2000.0,
    phaseout_start: float = 75000.0,
    phaseout_rate: float = 0.05,
) -> dict:
    """Estimate the historical proposed CASH Act second-stimulus scenario."""
    return _relief_payment(
        adjusted_gross_income,
        base_payment,
        dependents,
        dependent_payment,
        phaseout_start,
        phaseout_rate,
    )


@tool
def cell_phone_plan_calculator(
    monthly_base_cost: float,
    lines: int,
    per_line_cost: float,
    device_payments: float = 0.0,
    taxes_and_fees: float = 0.0,
    data_overage: float = 0.0,
) -> dict:
    """Calculate monthly and annual mobile-phone plan cost."""
    monthly = (
        monthly_base_cost
        + lines * per_line_cost
        + device_payments
        + taxes_and_fees
        + data_overage
    )
    return {"monthly_cost": monthly, "annual_cost": monthly * 12}


@tool
def quiz_car_depreciation_calculator(
    purchase_price: float, current_value: float, years: float
) -> dict:
    """Calculate total and annualized vehicle depreciation."""
    _positive(purchase_price, "purchase_price")
    rate = 1 - current_value / purchase_price
    annualized = 1 - (current_value / purchase_price) ** (1 / years)
    return {
        "total_depreciation": purchase_price - current_value,
        "total_depreciation_rate": rate,
        "annualized_depreciation_rate": annualized,
    }


@tool
def quiz_us_income_percentile_calculator(
    annual_income: float,
    percentile_thresholds: list[dict[str, float]],
) -> dict:
    """Estimate U.S. income percentile from a supplied year-specific threshold table."""
    return _income_percentile(annual_income, percentile_thresholds)


@tool
def sabbatical_calculator(
    monthly_expenses: float,
    sabbatical_months: int,
    one_time_costs: float = 0.0,
    income_during_sabbatical: float = 0.0,
    contingency_rate: float = 0.10,
) -> dict:
    """Calculate savings needed to fund a sabbatical."""
    base_need = (
        monthly_expenses * sabbatical_months
        + one_time_costs
        - income_during_sabbatical
    )
    return {
        "base_funding_need": base_need,
        "recommended_funding_with_contingency": base_need
        * (1 + contingency_rate),
    }


@tool
def savings_calculator(
    initial_savings: float,
    monthly_contribution: float,
    annual_interest_rate: float,
    years: float,
) -> dict:
    """Project savings with monthly compounding and contributions."""
    ending = _future_value(
        initial_savings,
        annual_interest_rate,
        years,
        12,
        monthly_contribution,
    )
    contributed = initial_savings + monthly_contribution * round(years * 12)
    return {
        "ending_balance": ending,
        "total_contributed": contributed,
        "interest_earned": ending - contributed,
    }


@tool
def savings_goal_calculator(
    target_amount: float,
    current_savings: float,
    annual_interest_rate: float,
    years: float,
) -> dict:
    """Calculate the monthly contribution needed to reach a savings goal."""
    periods = round(years * 12)
    monthly_rate = annual_interest_rate / 12
    future_current = current_savings * (1 + monthly_rate) ** periods
    remaining = max(0.0, target_amount - future_current)
    if monthly_rate == 0:
        contribution = remaining / periods
    else:
        contribution = remaining * monthly_rate / (
            (1 + monthly_rate) ** periods - 1
        )
    return {
        "required_monthly_contribution": contribution,
        "projected_current_savings": future_current,
    }


@tool
def savings_plan_calculator(
    target_amount: float,
    current_savings: float,
    monthly_contribution: float,
    annual_interest_rate: float,
) -> dict:
    """Estimate months required to reach a savings target."""
    balance = current_savings
    monthly_rate = annual_interest_rate / 12
    months = 0
    while balance < target_amount and months < 1200:
        balance = balance * (1 + monthly_rate) + monthly_contribution
        months += 1
    return {
        "months_to_goal": months if balance >= target_amount else None,
        "years_to_goal": months / 12 if balance >= target_amount else None,
        "ending_balance": balance,
    }


@tool
def scrap_gold_calculator(
    weight: float,
    karat: float,
    spot_price_per_weight_unit: float,
    dealer_discount_rate: float = 0.0,
) -> dict:
    """Calculate scrap-gold melt value from karat purity."""
    return _metal_value(
        weight,
        karat / 24,
        spot_price_per_weight_unit,
        dealer_discount_rate,
    )


@tool
def scrap_silver_calculator(
    weight: float,
    purity: float,
    spot_price_per_weight_unit: float,
    dealer_discount_rate: float = 0.0,
) -> dict:
    """Calculate scrap-silver value from weight, purity, and spot price."""
    return _metal_value(
        weight, purity, spot_price_per_weight_unit, dealer_discount_rate
    )


@tool
def second_stimulus_900_billion_bill_calculator(
    adjusted_gross_income: float,
    dependents: int = 0,
    base_payment: float = 600.0,
    dependent_payment: float = 600.0,
    phaseout_start: float = 75000.0,
    phaseout_rate: float = 0.05,
) -> dict:
    """Estimate the historical December 2020 second-stimulus payment."""
    return _relief_payment(
        adjusted_gross_income,
        base_payment,
        dependents,
        dependent_payment,
        phaseout_start,
        phaseout_rate,
    )


@tool
def second_stimulus_heroes_act_calculator(
    adjusted_gross_income: float,
    dependents: int = 0,
    base_payment: float = 1200.0,
    dependent_payment: float = 1200.0,
    maximum_dependents: int = 3,
    phaseout_start: float = 75000.0,
    phaseout_rate: float = 0.05,
) -> dict:
    """Estimate the historical proposed HEROES Act stimulus scenario."""
    return _relief_payment(
        adjusted_gross_income,
        base_payment,
        min(dependents, maximum_dependents),
        dependent_payment,
        phaseout_start,
        phaseout_rate,
    )


@tool
def silver_melt_calculator(
    weight: float,
    purity: float,
    spot_price_per_weight_unit: float,
) -> dict:
    """Calculate silver melt value."""
    return _metal_value(weight, purity, spot_price_per_weight_unit)


@tool
def simple_savings_calculator(
    initial_savings: float,
    monthly_deposit: float,
    months: int,
) -> dict:
    """Calculate savings accumulation without interest."""
    return {
        "ending_savings": initial_savings + monthly_deposit * months,
        "total_deposits": monthly_deposit * months,
    }


@tool
def stimulus_check_40k_cap_calculator(
    adjusted_gross_income: float,
    dependents: int = 0,
    base_payment: float = 1200.0,
    dependent_payment: float = 500.0,
    income_cap: float = 40000.0,
) -> dict:
    """Estimate a historical proposed stimulus scenario with a $40,000 cap."""
    return _relief_payment(
        adjusted_gross_income,
        base_payment,
        dependents,
        dependent_payment,
        income_cap,
        0.0,
        income_cap,
    )


@tool
def third_stimulus_american_rescue_plan_calculator(
    adjusted_gross_income: float,
    dependents: int = 0,
    base_payment: float = 1400.0,
    dependent_payment: float = 1400.0,
    phaseout_start: float = 75000.0,
    phaseout_end: float = 80000.0,
) -> dict:
    """Estimate the historical 2021 American Rescue Plan payment."""
    gross = base_payment + dependents * dependent_payment
    if adjusted_gross_income <= phaseout_start:
        payment = gross
    elif adjusted_gross_income >= phaseout_end:
        payment = 0.0
    else:
        payment = gross * (
            phaseout_end - adjusted_gross_income
        ) / (phaseout_end - phaseout_start)
    return {"estimated_payment": payment, "historical_policy_scenario": True}


@tool
def dream_come_true_calculator(
    dream_cost: float,
    current_savings: float,
    monthly_contribution: float,
    annual_return: float = 0.0,
) -> dict:
    """Estimate how long regular saving will take to fund a major goal."""
    result = savings_plan_calculator.invoke(
        {
            "target_amount": dream_cost,
            "current_savings": current_savings,
            "monthly_contribution": monthly_contribution,
            "annual_interest_rate": annual_return,
        }
    )
    return result


@tool
def emergency_fund_calculator(
    essential_monthly_expenses: float,
    target_months: float = 6.0,
    current_emergency_savings: float = 0.0,
) -> dict:
    """Calculate an emergency-fund target and funding gap."""
    target = essential_monthly_expenses * target_months
    return {
        "target_emergency_fund": target,
        "current_emergency_savings": current_emergency_savings,
        "funding_gap": max(0.0, target - current_emergency_savings),
    }


@tool
def fire_calculator(
    annual_spending: float,
    safe_withdrawal_rate: float = 0.04,
    current_investments: float = 0.0,
    annual_contribution: float = 0.0,
    annual_return: float = 0.07,
) -> dict:
    """Calculate a FIRE target and estimated years to financial independence."""
    _positive(safe_withdrawal_rate, "safe_withdrawal_rate")
    target = annual_spending / safe_withdrawal_rate
    balance = current_investments
    years = 0
    while balance < target and years < 100:
        balance = balance * (1 + annual_return) + annual_contribution
        years += 1
    return {
        "fire_number": target,
        "funding_gap": max(0.0, target - current_investments),
        "estimated_years_to_fire": years if balance >= target else None,
    }


@tool
def gold_melt_calculator(
    weight: float,
    purity: float,
    spot_price_per_weight_unit: float,
) -> dict:
    """Calculate gold melt value from weight, purity, and spot price."""
    return _metal_value(weight, purity, spot_price_per_weight_unit)


@tool
def pakistan_income_tax_calculator(
    taxable_income_pkr: float,
    brackets: list[dict[str, Any]],
    tax_year: str,
) -> dict:
    """Calculate Pakistan income tax from a supplied tax-year bracket schedule."""
    ordered = sorted(brackets, key=lambda item: math.inf if item.get("upper") is None else item["upper"])
    tax = 0.0
    lower = 0.0
    for item in ordered:
        upper = math.inf if item.get("upper") is None else float(item["upper"])
        amount = max(0.0, min(taxable_income_pkr, upper) - lower)
        tax += amount * float(item["rate"])
        if taxable_income_pkr <= upper:
            break
        lower = upper
    return {"estimated_tax": tax, "tax_year": tax_year}


@tool
def lifetime_earnings_calculator(
    current_annual_income: float,
    annual_income_growth: float,
    working_years: int,
    employment_gap_years: int = 0,
) -> dict:
    """Project nominal lifetime earnings with annual income growth."""
    paid_years = max(0, working_years - employment_gap_years)
    earnings = sum(
        current_annual_income * (1 + annual_income_growth) ** year
        for year in range(paid_years)
    )
    return {"projected_lifetime_earnings": earnings, "paid_years": paid_years}


@tool
def long_term_care_calculator(
    current_annual_care_cost: float,
    annual_care_inflation: float,
    years_until_care: int,
    years_of_care: int,
    insurance_benefits: float = 0.0,
) -> dict:
    """Project future long-term-care costs and remaining funding need."""
    first_year = current_annual_care_cost * (
        1 + annual_care_inflation
    ) ** years_until_care
    total = sum(
        first_year * (1 + annual_care_inflation) ** year
        for year in range(years_of_care)
    )
    return {
        "projected_total_care_cost": total,
        "insurance_benefits": insurance_benefits,
        "funding_need": max(0.0, total - insurance_benefits),
    }


@tool
def lottery_annuity_calculator(
    first_annual_payment: float,
    annual_payment_growth: float,
    payment_years: int,
    discount_rate: float,
) -> dict:
    """Calculate nominal and present value of an escalating lottery annuity."""
    payments = [
        first_annual_payment * (1 + annual_payment_growth) ** year
        for year in range(payment_years)
    ]
    present_value = sum(
        payment / (1 + discount_rate) ** (year + 1)
        for year, payment in enumerate(payments)
    )
    return {
        "nominal_total_payments": sum(payments),
        "present_value": present_value,
        "payments": payments,
    }


@tool
def mega_millions_payout_calculator(
    advertised_jackpot: float,
    cash_option_rate: float,
    federal_tax_rate: float,
    state_tax_rate: float = 0.0,
) -> dict:
    """Estimate Mega Millions cash option and after-tax payout."""
    cash = advertised_jackpot * cash_option_rate
    taxes = cash * (federal_tax_rate + state_tax_rate)
    return {
        "estimated_cash_option": cash,
        "estimated_taxes": taxes,
        "estimated_after_tax_cash": cash - taxes,
        "caution": "Lottery cash-option ratios and final taxes vary by drawing and residence.",
    }


@tool
def millionaire_calculator(
    current_net_worth: float,
    monthly_investment: float,
    annual_return: float,
    target_net_worth: float = 1000000.0,
) -> dict:
    """Estimate time to reach a target net worth."""
    balance = current_net_worth
    monthly_rate = annual_return / 12
    months = 0
    while balance < target_net_worth and months < 2400:
        balance = balance * (1 + monthly_rate) + monthly_investment
        months += 1
    return {
        "months_to_target": months if balance >= target_net_worth else None,
        "years_to_target": months / 12 if balance >= target_net_worth else None,
    }


@tool
def net_worth_calculator(
    assets: dict[str, float], liabilities: dict[str, float]
) -> dict:
    """Calculate total assets, liabilities, and net worth."""
    total_assets = sum(assets.values())
    total_liabilities = sum(liabilities.values())
    return {
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "net_worth": total_assets - total_liabilities,
    }


@tool
def powerball_calculator(
    advertised_jackpot: float,
    cash_option_rate: float,
    federal_tax_rate: float,
    state_tax_rate: float = 0.0,
) -> dict:
    """Estimate Powerball cash option and after-tax payout."""
    cash = advertised_jackpot * cash_option_rate
    taxes = cash * (federal_tax_rate + state_tax_rate)
    return {
        "estimated_cash_option": cash,
        "estimated_taxes": taxes,
        "estimated_after_tax_cash": cash - taxes,
        "caution": "Lottery payout and tax assumptions require drawing-specific verification.",
    }


@tool
def stimulus_caaf_vs_heals_vs_heroes_calculator(
    adjusted_gross_income: float,
    dependents: int,
    caaf_parameters: dict[str, float],
    heals_parameters: dict[str, float],
    heroes_parameters: dict[str, float],
) -> dict:
    """Compare three historical proposed stimulus scenarios."""
    def scenario(params: dict[str, float]) -> float:
        return _relief_payment(
            adjusted_gross_income,
            params["base_payment"],
            dependents,
            params["dependent_payment"],
            params["phaseout_start"],
            params.get("phaseout_rate", 0.05),
            params.get("income_cap"),
        )["estimated_payment"]

    return {
        "caaf": scenario(caaf_parameters),
        "heals": scenario(heals_parameters),
        "heroes": scenario(heroes_parameters),
        "historical_policy_scenario": True,
    }


@tool
def second_stimulus_heals_act_calculator(
    adjusted_gross_income: float,
    dependents: int = 0,
    base_payment: float = 1200.0,
    dependent_payment: float = 500.0,
    phaseout_start: float = 75000.0,
    phaseout_rate: float = 0.05,
) -> dict:
    """Estimate the historical proposed HEALS Act stimulus payment."""
    return _relief_payment(
        adjusted_gross_income,
        base_payment,
        dependents,
        dependent_payment,
        phaseout_start,
        phaseout_rate,
    )


@tool
def stimulus_check_calculator(
    adjusted_gross_income: float,
    dependents: int,
    base_payment: float,
    dependent_payment: float,
    phaseout_start: float,
    phaseout_rate: float,
    income_cap: float | None = None,
) -> dict:
    """Calculate a configurable stimulus or relief-payment scenario."""
    return _relief_payment(
        adjusted_gross_income,
        base_payment,
        dependents,
        dependent_payment,
        phaseout_start,
        phaseout_rate,
        income_cap,
    )


@tool
def subscription_waste_calculator(
    subscriptions: list[dict[str, Any]],
) -> dict:
    """Calculate annual cost of unused or underused subscriptions."""
    total_monthly = sum(float(item["monthly_cost"]) for item in subscriptions)
    wasted_monthly = sum(
        float(item["monthly_cost"])
        * (1 - float(item.get("utilization_rate", 0.0)))
        for item in subscriptions
    )
    return {
        "monthly_subscription_cost": total_monthly,
        "annual_subscription_cost": total_monthly * 12,
        "estimated_monthly_waste": wasted_monthly,
        "estimated_annual_waste": wasted_monthly * 12,
    }


@tool
def unemployment_benefit_cares_act_calculator(
    state_weekly_benefit: float,
    eligible_weeks: int,
    federal_weekly_supplement: float = 600.0,
) -> dict:
    """Estimate historical CARES Act unemployment benefits."""
    weekly = state_weekly_benefit + federal_weekly_supplement
    return {
        "weekly_benefit": weekly,
        "total_benefit": weekly * eligible_weeks,
        "historical_policy_scenario": True,
    }


@tool
def unemployment_benefit_heals_vs_heroes_calculator(
    state_weekly_benefit: float,
    eligible_weeks: int,
    heals_weekly_supplement: float,
    heroes_weekly_supplement: float,
) -> dict:
    """Compare historical proposed HEALS and HEROES unemployment supplements."""
    return {
        "heals_total": (
            state_weekly_benefit + heals_weekly_supplement
        ) * eligible_weeks,
        "heroes_total": (
            state_weekly_benefit + heroes_weekly_supplement
        ) * eligible_weeks,
        "historical_policy_scenario": True,
    }


@tool
def unemployment_benefit_lwa_calculator(
    state_weekly_benefit: float,
    eligible_weeks: int,
    federal_lwa_supplement: float = 300.0,
    state_lwa_supplement: float = 0.0,
) -> dict:
    """Estimate historical Lost Wages Assistance benefits."""
    weekly = (
        state_weekly_benefit
        + federal_lwa_supplement
        + state_lwa_supplement
    )
    return {
        "weekly_benefit": weekly,
        "total_benefit": weekly * eligible_weeks,
        "historical_policy_scenario": True,
    }


@tool
def unpaid_work_calculator(
    unpaid_hours_per_week: float,
    hourly_value: float,
    weeks_per_year: float = 52.0,
) -> dict:
    """Estimate annual economic value of unpaid work."""
    weekly = unpaid_hours_per_week * hourly_value
    return {"weekly_value": weekly, "annual_value": weekly * weeks_per_year}


@tool
def us_income_percentile_calculator(
    annual_income: float,
    percentile_thresholds: list[dict[str, float]],
) -> dict:
    """Estimate U.S. income percentile from supplied official or research thresholds."""
    return _income_percentile(annual_income, percentile_thresholds)


@tool
def wedding_budget_calculator(
    total_budget: float,
    category_percentages: dict[str, float],
    contingency_rate: float = 0.05,
) -> dict:
    """Allocate a wedding budget by category with a contingency reserve."""
    percentage_total = sum(category_percentages.values())
    if percentage_total > 1:
        raise ValueError("category percentages cannot sum above 1")
    contingency = total_budget * contingency_rate
    allocatable = total_budget - contingency
    return {
        "contingency": contingency,
        "category_budgets": {
            category: allocatable * percentage
            for category, percentage in category_percentages.items()
        },
        "unallocated": allocatable * (1 - percentage_total),
    }


@tool
def zakat_calculator(
    zakatable_assets: float,
    deductible_short_term_liabilities: float,
    nisab_threshold: float,
    zakat_rate: float = 0.025,
) -> dict:
    """Estimate zakat on net eligible assets above a supplied nisab threshold."""
    net_assets = max(0.0, zakatable_assets - deductible_short_term_liabilities)
    due = net_assets >= nisab_threshold
    return {
        "net_zakatable_assets": net_assets,
        "nisab_threshold": nisab_threshold,
        "zakat_due": due,
        "estimated_zakat": net_assets * zakat_rate if due else 0.0,
        "caution": "Asset eligibility and haul rules vary by scholarly interpretation.",
    }


PERSONAL_FINANCE_CALCULATOR_TOOLS = (
    retirement_403b_calculator,
    fifty_thirty_twenty_rule_calculator,
    education_529_calculator,
    seventy_twenty_ten_rule_money_calculator,
    apc_calculator,
    auto_loan_calculator,
    bank_reconciliation_calculator,
    boat_loan_calculator,
    budget_calculator,
    car_affordability_calculator,
    car_depreciation_calculator,
    car_lease_calculator,
    second_stimulus_cash_act_calculator,
    cell_phone_plan_calculator,
    quiz_car_depreciation_calculator,
    quiz_us_income_percentile_calculator,
    sabbatical_calculator,
    savings_calculator,
    savings_goal_calculator,
    savings_plan_calculator,
    scrap_gold_calculator,
    scrap_silver_calculator,
    second_stimulus_900_billion_bill_calculator,
    second_stimulus_heroes_act_calculator,
    silver_melt_calculator,
    simple_savings_calculator,
    stimulus_check_40k_cap_calculator,
    third_stimulus_american_rescue_plan_calculator,
    dream_come_true_calculator,
    emergency_fund_calculator,
    fire_calculator,
    gold_melt_calculator,
    pakistan_income_tax_calculator,
    lifetime_earnings_calculator,
    long_term_care_calculator,
    lottery_annuity_calculator,
    mega_millions_payout_calculator,
    millionaire_calculator,
    net_worth_calculator,
    powerball_calculator,
    stimulus_caaf_vs_heals_vs_heroes_calculator,
    second_stimulus_heals_act_calculator,
    stimulus_check_calculator,
    subscription_waste_calculator,
    unemployment_benefit_cares_act_calculator,
    unemployment_benefit_heals_vs_heroes_calculator,
    unemployment_benefit_lwa_calculator,
    unpaid_work_calculator,
    us_income_percentile_calculator,
    wedding_budget_calculator,
    zakat_calculator,
)

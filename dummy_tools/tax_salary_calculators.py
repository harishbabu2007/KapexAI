"""Deterministic tax, payroll, and salary calculator tools."""

import math
from typing import Any, Literal

from langchain.tools import tool


def _nonnegative(value: float, name: str) -> None:
    if value < 0:
        raise ValueError(f"{name} must be zero or greater")


def _positive(value: float, name: str) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")


def _rate(value: float, name: str) -> None:
    if not 0 <= value <= 1:
        raise ValueError(f"{name} must be between 0 and 1")


def _progressive_tax(
    taxable_income: float, brackets: list[dict[str, Any]]
) -> dict:
    _nonnegative(taxable_income, "taxable_income")
    if not brackets:
        raise ValueError("At least one tax bracket is required")
    ordered = sorted(
        brackets,
        key=lambda item: math.inf
        if item.get("upper") is None
        else float(item["upper"]),
    )
    tax = 0.0
    lower = 0.0
    details = []
    covered = False
    for item in ordered:
        rate = float(item["rate"])
        _rate(rate, "bracket rate")
        upper_raw = item.get("upper")
        upper = math.inf if upper_raw is None else float(upper_raw)
        if upper <= lower:
            raise ValueError("bracket upper limits must increase")
        amount = max(0.0, min(taxable_income, upper) - lower)
        bracket_tax = amount * rate
        tax += bracket_tax
        details.append(
            {
                "lower": lower,
                "upper": None if math.isinf(upper) else upper,
                "rate": rate,
                "taxable_amount": amount,
                "tax": bracket_tax,
            }
        )
        if taxable_income <= upper:
            covered = True
            break
        lower = upper
    if not covered:
        raise ValueError("brackets do not cover all taxable income")
    return {
        "tax": tax,
        "effective_rate": tax / taxable_income if taxable_income else 0.0,
        "bracket_details": details,
    }


def _flat_tax(
    taxable_income: float, rate: float, credits: float = 0.0
) -> dict:
    _nonnegative(taxable_income, "taxable_income")
    _rate(rate, "tax rate")
    gross_tax = taxable_income * rate
    tax = max(0.0, gross_tax - credits)
    return {
        "gross_tax": gross_tax,
        "credits": credits,
        "tax": tax,
        "effective_rate": tax / taxable_income if taxable_income else 0.0,
    }


def _sales_tax(
    purchase_amount: float, state_rate: float, local_rate: float = 0.0
) -> dict:
    _nonnegative(purchase_amount, "purchase_amount")
    _rate(state_rate, "state_rate")
    _rate(local_rate, "local_rate")
    combined_rate = state_rate + local_rate
    tax = purchase_amount * combined_rate
    return {
        "pre_tax_amount": purchase_amount,
        "state_rate": state_rate,
        "local_rate": local_rate,
        "combined_rate": combined_rate,
        "sales_tax": tax,
        "total": purchase_amount + tax,
    }


def _salary_from_period(
    pay_amount: float,
    periods_per_year: float,
) -> dict:
    _nonnegative(pay_amount, "pay_amount")
    _positive(periods_per_year, "periods_per_year")
    annual = pay_amount * periods_per_year
    return {
        "annual_income": annual,
        "monthly_income": annual / 12,
        "weekly_income": annual / 52,
        "hourly_equivalent_at_2080_hours": annual / 2080,
    }


def _policy_comparison(
    taxable_income: float,
    baseline_brackets: list[dict[str, Any]],
    proposal_brackets: list[dict[str, Any]],
    baseline_credits: float = 0.0,
    proposal_credits: float = 0.0,
) -> dict:
    baseline = _progressive_tax(taxable_income, baseline_brackets)
    proposal = _progressive_tax(taxable_income, proposal_brackets)
    baseline_tax = max(0.0, baseline["tax"] - baseline_credits)
    proposal_tax = max(0.0, proposal["tax"] - proposal_credits)
    return {
        "baseline_tax": baseline_tax,
        "proposal_tax": proposal_tax,
        "tax_change": proposal_tax - baseline_tax,
        "after_tax_income_change": baseline_tax - proposal_tax,
    }


@tool
def twelve_hour_shift_pay_calculator(
    hourly_rate: float,
    shifts: float,
    regular_hours_per_shift: float = 8.0,
    overtime_multiplier: float = 1.5,
) -> dict:
    """Calculate pay for 12-hour shifts with daily overtime after regular hours."""
    _nonnegative(hourly_rate, "hourly_rate")
    _nonnegative(shifts, "shifts")
    regular_hours = min(12.0, regular_hours_per_shift) * shifts
    overtime_hours = max(0.0, 12.0 - regular_hours_per_shift) * shifts
    regular_pay = regular_hours * hourly_rate
    overtime_pay = overtime_hours * hourly_rate * overtime_multiplier
    return {
        "regular_hours": regular_hours,
        "overtime_hours": overtime_hours,
        "regular_pay": regular_pay,
        "overtime_pay": overtime_pay,
        "gross_pay": regular_pay + overtime_pay,
    }


@tool
def adjusted_gross_income_calculator(
    gross_income: float, above_the_line_adjustments: list[float]
) -> dict:
    """Calculate U.S. adjusted gross income before standard or itemized deductions."""
    adjustments = sum(above_the_line_adjustments)
    return {
        "gross_income": gross_income,
        "adjustments": adjustments,
        "adjusted_gross_income": gross_income - adjustments,
    }


@tool
def alabama_tax_calculator(
    taxable_income: float,
    credits: float = 0.0,
) -> dict:
    """Estimate Alabama individual income tax using the 2%, 4%, and 5% schedule."""
    result = _progressive_tax(
        taxable_income,
        [
            {"upper": 500, "rate": 0.02},
            {"upper": 3000, "rate": 0.04},
            {"upper": None, "rate": 0.05},
        ],
    )
    result["tax"] = max(0.0, result["tax"] - credits)
    result["jurisdiction"] = "Alabama"
    result["caution"] = "Estimate excludes filing-status thresholds, deductions, and local tax."
    return result


@tool
def amt_calculator(
    alternative_minimum_taxable_income: float,
    exemption: float,
    exemption_phaseout_threshold: float,
    regular_tax: float,
    lower_rate: float = 0.26,
    upper_rate: float = 0.28,
    upper_rate_threshold: float = 239100.0,
) -> dict:
    """Estimate U.S. alternative minimum tax from supplied year-specific parameters."""
    phaseout = max(
        0.0,
        (alternative_minimum_taxable_income - exemption_phaseout_threshold)
        * 0.25,
    )
    allowed_exemption = max(0.0, exemption - phaseout)
    amt_base = max(0.0, alternative_minimum_taxable_income - allowed_exemption)
    tentative_minimum_tax = (
        min(amt_base, upper_rate_threshold) * lower_rate
        + max(0.0, amt_base - upper_rate_threshold) * upper_rate
    )
    return {
        "allowed_exemption": allowed_exemption,
        "amt_base": amt_base,
        "tentative_minimum_tax": tentative_minimum_tax,
        "alternative_minimum_tax": max(0.0, tentative_minimum_tax - regular_tax),
        "caution": "Use tax-year and filing-status-specific exemption and threshold inputs.",
    }


@tool
def annual_income_calculator(
    pay_amount: float, pay_frequency: Literal[
        "hourly", "daily", "weekly", "biweekly", "semimonthly", "monthly", "annual"
    ], hours_per_week: float = 40.0, days_per_week: float = 5.0
) -> dict:
    """Convert common pay frequencies into annual income."""
    factors = {
        "daily": days_per_week * 52,
        "weekly": 52,
        "biweekly": 26,
        "semimonthly": 24,
        "monthly": 12,
        "annual": 1,
    }
    periods = hours_per_week * 52 if pay_frequency == "hourly" else factors[pay_frequency]
    return _salary_from_period(pay_amount, periods)


@tool
def biden_tax_plan_calculator(
    taxable_income: float,
    current_law_brackets: list[dict[str, Any]],
    biden_plan_brackets: list[dict[str, Any]],
    current_law_credits: float = 0.0,
    biden_plan_credits: float = 0.0,
) -> dict:
    """Compare a user-supplied current-law schedule with a Biden policy scenario."""
    result = _policy_comparison(
        taxable_income,
        current_law_brackets,
        biden_plan_brackets,
        current_law_credits,
        biden_plan_credits,
    )
    result["policy_label"] = "Biden tax plan scenario"
    return result


@tool
def billable_hours_calculator(
    available_work_hours: float,
    nonbillable_hours: float,
    utilization_target: float | None = None,
) -> dict:
    """Calculate billable hours and utilization."""
    _positive(available_work_hours, "available_work_hours")
    billable = max(0.0, available_work_hours - nonbillable_hours)
    result = {
        "billable_hours": billable,
        "utilization_rate": billable / available_work_hours,
    }
    if utilization_target is not None:
        result["target_billable_hours"] = available_work_hours * utilization_target
        result["hours_to_target"] = max(
            0.0, available_work_hours * utilization_target - billable
        )
    return result


@tool
def bill_rate_calculator(
    annual_compensation: float,
    annual_overhead: float,
    annual_billable_hours: float,
    target_profit_margin: float,
) -> dict:
    """Calculate the hourly client bill rate needed for a target profit margin."""
    _positive(annual_billable_hours, "annual_billable_hours")
    if not 0 <= target_profit_margin < 1:
        raise ValueError("target_profit_margin must be between 0 and 1")
    cost_per_billable_hour = (
        annual_compensation + annual_overhead
    ) / annual_billable_hours
    return {
        "cost_per_billable_hour": cost_per_billable_hour,
        "required_bill_rate": cost_per_billable_hour
        / (1 - target_profit_margin),
    }


@tool
def build_back_better_calculator(
    taxable_income: float,
    baseline_brackets: list[dict[str, Any]],
    proposal_brackets: list[dict[str, Any]],
    baseline_credits: float = 0.0,
    proposal_credits: float = 0.0,
) -> dict:
    """Compare baseline tax with a user-supplied Build Back Better scenario."""
    result = _policy_comparison(
        taxable_income,
        baseline_brackets,
        proposal_brackets,
        baseline_credits,
        proposal_credits,
    )
    result["policy_label"] = "Build Back Better scenario"
    return result


@tool
def california_sales_tax_calculator(
    purchase_amount: float, local_rate: float = 0.0
) -> dict:
    """Estimate California sales tax using the 7.25% statewide base plus local rate."""
    result = _sales_tax(purchase_amount, 0.0725, local_rate)
    result["jurisdiction"] = "California"
    return result


@tool
def california_stimulus_check_ii_calculator(
    california_agi_2020: float,
    has_qualifying_dependent: bool,
    qualified_for_first_golden_state_stimulus: bool = False,
    valid_ssn_or_itin: bool = True,
    resident_more_than_half_year: bool = True,
    claimed_as_dependent: bool = False,
) -> dict:
    """Estimate historical 2021 Golden State Stimulus II eligibility and payment."""
    eligible = (
        1 <= california_agi_2020 <= 75000
        and valid_ssn_or_itin
        and resident_more_than_half_year
        and not claimed_as_dependent
    )
    base_payment = (
        0.0
        if qualified_for_first_golden_state_stimulus and not has_qualifying_dependent
        else 600.0
    )
    dependent_payment = 500.0 if has_qualifying_dependent else 0.0
    return {
        "eligible": eligible,
        "estimated_payment": base_payment + dependent_payment if eligible else 0.0,
        "program": "California Golden State Stimulus II (historical 2021 program)",
    }


@tool
def california_tax_calculator(
    taxable_income: float,
    brackets: list[dict[str, Any]],
    credits: float = 0.0,
    tax_year: int = 2026,
) -> dict:
    """Calculate California tax from supplied filing-status and tax-year brackets."""
    result = _progressive_tax(taxable_income, brackets)
    result["tax"] = max(0.0, result["tax"] - credits)
    result["jurisdiction"] = "California"
    result["tax_year"] = tax_year
    return result


@tool
def child_tax_credit_calculator(
    qualifying_children: int,
    modified_adjusted_gross_income: float,
    filing_status: Literal["single", "married_joint"],
    credit_per_child: float = 2200.0,
    phaseout_threshold_single: float = 200000.0,
    phaseout_threshold_married_joint: float = 400000.0,
) -> dict:
    """Estimate U.S. Child Tax Credit using supplied tax-year credit parameters."""
    if qualifying_children < 0:
        raise ValueError("qualifying_children cannot be negative")
    threshold = (
        phaseout_threshold_married_joint
        if filing_status == "married_joint"
        else phaseout_threshold_single
    )
    gross_credit = qualifying_children * credit_per_child
    excess = max(0.0, modified_adjusted_gross_income - threshold)
    reduction = math.ceil(excess / 1000) * 50 if excess else 0.0
    return {
        "gross_credit": gross_credit,
        "phaseout_reduction": reduction,
        "estimated_credit": max(0.0, gross_credit - reduction),
        "caution": "Refundability and qualifying-child rules require tax-year verification.",
    }


@tool
def fica_tax_calculator(
    wage_income: float,
    filing_status: Literal["single", "married_joint", "married_separate"] = "single",
    social_security_rate: float = 0.062,
    social_security_wage_base: float = 184500.0,
    medicare_rate: float = 0.0145,
    additional_medicare_rate: float = 0.009,
) -> dict:
    """Estimate employee U.S. FICA taxes using configurable 2026 defaults."""
    _nonnegative(wage_income, "wage_income")
    thresholds = {
        "single": 200000.0,
        "married_joint": 250000.0,
        "married_separate": 125000.0,
    }
    social_security = min(wage_income, social_security_wage_base) * social_security_rate
    medicare = wage_income * medicare_rate
    additional = max(0.0, wage_income - thresholds[filing_status]) * additional_medicare_rate
    return {
        "social_security_tax": social_security,
        "medicare_tax": medicare,
        "additional_medicare_tax": additional,
        "total_fica": social_security + medicare + additional,
        "assumption_year": 2026,
    }


@tool
def florida_sales_tax_calculator(
    purchase_amount: float, local_discretionary_rate: float = 0.0
) -> dict:
    """Estimate Florida sales tax using the 6% state rate plus local surtax."""
    result = _sales_tax(purchase_amount, 0.06, local_discretionary_rate)
    result["jurisdiction"] = "Florida"
    return result


@tool
def future_salary_calculator(
    current_salary: float,
    annual_raise_rate: float,
    years: int,
) -> dict:
    """Project salary after recurring annual raises."""
    if years < 0:
        raise ValueError("years cannot be negative")
    future = current_salary * ((1 + annual_raise_rate) ** years)
    return {
        "future_salary": future,
        "increase": future - current_salary,
    }


@tool
def gratuity_calculator(
    eligible_salary: float,
    years_of_service: float,
    days_wages_per_year: float = 15.0,
    days_in_salary_month: float = 26.0,
) -> dict:
    """Calculate statutory-style gratuity from salary and service years."""
    _nonnegative(eligible_salary, "eligible_salary")
    _nonnegative(years_of_service, "years_of_service")
    _positive(days_in_salary_month, "days_in_salary_month")
    gratuity = (
        eligible_salary
        * days_wages_per_year
        / days_in_salary_month
        * years_of_service
    )
    return {"gratuity": gratuity}


@tool
def gross_to_net_calculator(
    gross_pay: float,
    pre_tax_deductions: float = 0.0,
    income_tax_rate: float = 0.0,
    payroll_tax_rate: float = 0.0,
    post_tax_deductions: float = 0.0,
) -> dict:
    """Estimate net pay from gross pay and explicit deduction rates."""
    taxable = max(0.0, gross_pay - pre_tax_deductions)
    income_tax = taxable * income_tax_rate
    payroll_tax = taxable * payroll_tax_rate
    net = gross_pay - pre_tax_deductions - income_tax - payroll_tax - post_tax_deductions
    return {
        "taxable_pay": taxable,
        "income_tax": income_tax,
        "payroll_tax": payroll_tax,
        "net_pay": net,
    }


@tool
def gst_calculator(
    pre_tax_amount: float, gst_rate: float
) -> dict:
    """Calculate goods and services tax from a supplied jurisdictional rate."""
    return _sales_tax(pre_tax_amount, gst_rate)


@tool
def gst_qst_canada_calculator(
    pre_tax_amount: float,
    gst_rate: float = 0.05,
    qst_rate: float = 0.09975,
) -> dict:
    """Calculate Quebec GST and QST using configurable current rates."""
    gst = pre_tax_amount * gst_rate
    qst = pre_tax_amount * qst_rate
    return {
        "pre_tax_amount": pre_tax_amount,
        "gst": gst,
        "qst": qst,
        "total_tax": gst + qst,
        "total": pre_tax_amount + gst + qst,
    }


@tool
def hourly_to_salary_calculator(
    hourly_rate: float,
    hours_per_week: float = 40.0,
    weeks_per_year: float = 52.0,
) -> dict:
    """Convert an hourly wage to annual and periodic salary equivalents."""
    annual = hourly_rate * hours_per_week * weeks_per_year
    return {
        "annual_salary": annual,
        "monthly_salary": annual / 12,
        "biweekly_salary": annual / 26,
        "weekly_salary": annual / 52,
    }


@tool
def illinois_tax_calculator(
    taxable_income: float,
    credits: float = 0.0,
    flat_rate: float = 0.0495,
) -> dict:
    """Estimate Illinois individual income tax using its configurable flat rate."""
    result = _flat_tax(taxable_income, flat_rate, credits)
    result["jurisdiction"] = "Illinois"
    return result


@tool
def australia_income_tax_cuts_2020_21_calculator(
    taxable_income_aud: float,
    include_medicare_levy: bool = True,
) -> dict:
    """Calculate historical Australian resident income tax for 2020-21."""
    result = _progressive_tax(
        taxable_income_aud,
        [
            {"upper": 18200, "rate": 0.0},
            {"upper": 45000, "rate": 0.19},
            {"upper": 120000, "rate": 0.325},
            {"upper": 180000, "rate": 0.37},
            {"upper": None, "rate": 0.45},
        ],
    )
    medicare = taxable_income_aud * 0.02 if include_medicare_levy else 0.0
    result["medicare_levy_estimate"] = medicare
    result["total_tax"] = result["tax"] + medicare
    result["tax_year"] = "Australia 2020-21 historical"
    return result


@tool
def philippines_income_tax_calculator(
    annual_taxable_income_php: float,
) -> dict:
    """Calculate Philippine individual income tax under the 2023-onward TRAIN table."""
    result = _progressive_tax(
        annual_taxable_income_php,
        [
            {"upper": 250000, "rate": 0.0},
            {"upper": 400000, "rate": 0.15},
            {"upper": 800000, "rate": 0.20},
            {"upper": 2000000, "rate": 0.25},
            {"upper": 8000000, "rate": 0.30},
            {"upper": None, "rate": 0.35},
        ],
    )
    result["jurisdiction"] = "Philippines"
    result["schedule"] = "TRAIN 2023 onward"
    return result


@tool
def lottery_tax_calculator(
    gross_winnings: float,
    federal_tax_rate: float = 0.24,
    state_tax_rate: float = 0.0,
    local_tax_rate: float = 0.0,
) -> dict:
    """Estimate lottery withholding and net proceeds from explicit rates."""
    combined = federal_tax_rate + state_tax_rate + local_tax_rate
    taxes = gross_winnings * combined
    return {
        "federal_tax": gross_winnings * federal_tax_rate,
        "state_tax": gross_winnings * state_tax_rate,
        "local_tax": gross_winnings * local_tax_rate,
        "total_tax": taxes,
        "net_winnings": gross_winnings - taxes,
        "caution": "Withholding may differ from final income-tax liability.",
    }


@tool
def modified_adjusted_gross_income_calculator(
    adjusted_gross_income: float, addbacks: list[float]
) -> dict:
    """Calculate MAGI from AGI plus program-specific addbacks."""
    addback_total = sum(addbacks)
    return {
        "adjusted_gross_income": adjusted_gross_income,
        "addbacks": addback_total,
        "modified_adjusted_gross_income": adjusted_gross_income + addback_total,
    }


@tool
def mileage_reimbursement_calculator(
    business_miles: float,
    reimbursement_rate_per_mile: float = 0.725,
    tolls_and_parking: float = 0.0,
) -> dict:
    """Calculate mileage reimbursement using a configurable 2026 U.S. default rate."""
    _nonnegative(business_miles, "business_miles")
    mileage = business_miles * reimbursement_rate_per_mile
    return {
        "mileage_reimbursement": mileage,
        "tolls_and_parking": tolls_and_parking,
        "total_reimbursement": mileage + tolls_and_parking,
        "assumption_year": 2026,
    }


@tool
def missouri_sales_tax_calculator(
    purchase_amount: float, local_rate: float = 0.0
) -> dict:
    """Estimate Missouri sales tax using the 4.225% state rate plus local rate."""
    result = _sales_tax(purchase_amount, 0.04225, local_rate)
    result["jurisdiction"] = "Missouri"
    return result


@tool
def net_to_gross_calculator(
    desired_net_pay: float,
    combined_tax_rate: float,
    fixed_deductions: float = 0.0,
) -> dict:
    """Gross up a desired net payment using an explicit combined tax rate."""
    if not 0 <= combined_tax_rate < 1:
        raise ValueError("combined_tax_rate must be between 0 and 1")
    gross = (desired_net_pay + fixed_deductions) / (1 - combined_tax_rate)
    return {
        "required_gross_pay": gross,
        "estimated_tax": gross * combined_tax_rate,
    }


@tool
def new_jersey_sales_tax_calculator(
    purchase_amount: float, local_rate: float = 0.0
) -> dict:
    """Estimate New Jersey sales tax using the 6.625% state rate."""
    result = _sales_tax(purchase_amount, 0.06625, local_rate)
    result["jurisdiction"] = "New Jersey"
    return result


@tool
def new_york_tax_calculator(
    taxable_income: float,
    brackets: list[dict[str, Any]],
    credits: float = 0.0,
    local_tax_rate: float = 0.0,
    tax_year: int = 2026,
) -> dict:
    """Calculate New York state tax from supplied brackets plus optional local tax."""
    result = _progressive_tax(taxable_income, brackets)
    local_tax = taxable_income * local_tax_rate
    result["state_tax_before_credits"] = result["tax"]
    result["local_tax"] = local_tax
    result["tax"] = max(0.0, result["tax"] - credits) + local_tax
    result["jurisdiction"] = "New York"
    result["tax_year"] = tax_year
    return result


@tool
def ohio_sales_tax_calculator(
    purchase_amount: float, local_rate: float = 0.0
) -> dict:
    """Estimate Ohio sales tax using the 5.75% state rate plus local rate."""
    result = _sales_tax(purchase_amount, 0.0575, local_rate)
    result["jurisdiction"] = "Ohio"
    return result


@tool
def overtime_calculator(
    hourly_rate: float,
    regular_hours: float,
    overtime_hours: float,
    overtime_multiplier: float = 1.5,
) -> dict:
    """Calculate regular, overtime, and gross pay."""
    regular_pay = hourly_rate * regular_hours
    overtime_pay = hourly_rate * overtime_multiplier * overtime_hours
    return {
        "regular_pay": regular_pay,
        "overtime_pay": overtime_pay,
        "gross_pay": regular_pay + overtime_pay,
    }


@tool
def pay_raise_calculator(
    current_pay: float,
    raise_rate: float | None = None,
    new_pay: float | None = None,
) -> dict:
    """Calculate new pay from a raise rate or derive the raise from new pay."""
    if raise_rate is None and new_pay is None:
        raise ValueError("Provide raise_rate or new_pay")
    if new_pay is None:
        new_pay = current_pay * (1 + float(raise_rate))
    change = new_pay - current_pay
    return {
        "new_pay": new_pay,
        "pay_increase": change,
        "raise_rate": change / current_pay if current_pay else None,
    }


@tool
def prorated_salary_calculator(
    annual_salary: float,
    eligible_days: float,
    total_working_days: float = 260.0,
) -> dict:
    """Prorate annual salary over eligible working days."""
    _positive(total_working_days, "total_working_days")
    return {
        "prorated_salary": annual_salary * eligible_days / total_working_days,
        "daily_salary": annual_salary / total_working_days,
    }


@tool
def quiz_annual_income_calculator(
    periodic_pay: float, periods_per_year: float
) -> dict:
    """Calculate annual income from a periodic payment and annual frequency."""
    return _salary_from_period(periodic_pay, periods_per_year)


_RMD_FACTORS = {
    73: 26.5, 74: 25.5, 75: 24.6, 76: 23.7, 77: 22.9, 78: 22.0,
    79: 21.1, 80: 20.2, 81: 19.4, 82: 18.5, 83: 17.7, 84: 16.8,
    85: 16.0, 86: 15.2, 87: 14.4, 88: 13.7, 89: 12.9, 90: 12.2,
    91: 11.5, 92: 10.8, 93: 10.1, 94: 9.5, 95: 8.9, 96: 8.4,
    97: 7.8, 98: 7.3, 99: 6.8, 100: 6.4, 101: 6.0, 102: 5.6,
    103: 5.2, 104: 4.9, 105: 4.6, 106: 4.3, 107: 4.1, 108: 3.9,
    109: 3.7, 110: 3.5, 111: 3.4, 112: 3.3, 113: 3.1, 114: 3.0,
    115: 2.9, 116: 2.8, 117: 2.7, 118: 2.5, 119: 2.3, 120: 2.0,
}


@tool
def rmd_calculator(
    prior_year_end_balance: float,
    age: int,
    custom_distribution_period: float | None = None,
) -> dict:
    """Estimate an IRA RMD using the IRS Uniform Lifetime Table."""
    if custom_distribution_period is None:
        if age < 73:
            return {"required_minimum_distribution": 0.0, "distribution_period": None}
        factor = _RMD_FACTORS[min(age, 120)]
    else:
        factor = custom_distribution_period
    _positive(factor, "distribution period")
    return {
        "required_minimum_distribution": prior_year_end_balance / factor,
        "distribution_period": factor,
        "caution": "Inherited accounts and much-younger-spouse cases may use different tables.",
    }


@tool
def salary_calculator(
    base_salary: float,
    annual_bonus: float = 0.0,
    commissions: float = 0.0,
    taxable_benefits: float = 0.0,
) -> dict:
    """Calculate total annual compensation and common periodic equivalents."""
    total = base_salary + annual_bonus + commissions + taxable_benefits
    return {
        "annual_compensation": total,
        "monthly_compensation": total / 12,
        "biweekly_compensation": total / 26,
        "weekly_compensation": total / 52,
    }


@tool
def salary_inflation_calculator(
    current_salary: float,
    annual_inflation_rate: float,
    years: int,
    future_nominal_salary: float | None = None,
) -> dict:
    """Calculate inflation-equivalent salary and optional future real purchasing power."""
    inflation_factor = (1 + annual_inflation_rate) ** years
    equivalent = current_salary * inflation_factor
    return {
        "salary_needed_to_maintain_purchasing_power": equivalent,
        "future_salary_in_current_money": (
            future_nominal_salary / inflation_factor
            if future_nominal_salary is not None
            else None
        ),
    }


@tool
def salary_to_hourly_calculator(
    annual_salary: float,
    hours_per_week: float = 40.0,
    weeks_per_year: float = 52.0,
) -> dict:
    """Convert annual salary to hourly wage."""
    annual_hours = hours_per_week * weeks_per_year
    _positive(annual_hours, "annual hours")
    return {"hourly_rate": annual_salary / annual_hours}


@tool
def sales_tax_calculator(
    purchase_amount: float,
    sales_tax_rate: float,
    tax_inclusive: bool = False,
) -> dict:
    """Calculate sales tax for tax-exclusive or tax-inclusive prices."""
    if tax_inclusive:
        pre_tax = purchase_amount / (1 + sales_tax_rate)
        tax = purchase_amount - pre_tax
        return {"pre_tax_amount": pre_tax, "sales_tax": tax, "total": purchase_amount}
    return _sales_tax(purchase_amount, sales_tax_rate)


@tool
def state_tax_calculator(
    taxable_income: float,
    brackets: list[dict[str, Any]] | None = None,
    flat_rate: float | None = None,
    credits: float = 0.0,
    state: str = "Custom",
    tax_year: int = 2026,
) -> dict:
    """Calculate state income tax using either supplied brackets or a flat rate."""
    if brackets:
        result = _progressive_tax(taxable_income, brackets)
        result["tax"] = max(0.0, result["tax"] - credits)
    elif flat_rate is not None:
        result = _flat_tax(taxable_income, flat_rate, credits)
    else:
        raise ValueError("Provide brackets or flat_rate")
    result["state"] = state
    result["tax_year"] = tax_year
    return result


@tool
def tax_bracket_calculator(
    taxable_income: float, brackets: list[dict[str, Any]]
) -> dict:
    """Calculate progressive tax, effective rate, and marginal bracket."""
    result = _progressive_tax(taxable_income, brackets)
    used = [item for item in result["bracket_details"] if item["taxable_amount"] > 0]
    result["marginal_rate"] = used[-1]["rate"] if used else 0.0
    return result


@tool
def texas_tax_calculator(
    taxable_income: float,
    local_or_other_income_tax_rate: float = 0.0,
) -> dict:
    """Estimate Texas individual income tax, which has no state individual income tax."""
    other_tax = taxable_income * local_or_other_income_tax_rate
    return {
        "texas_state_individual_income_tax": 0.0,
        "other_income_tax": other_tax,
        "total": other_tax,
    }


@tool
def time_and_a_half_calculator(
    hourly_rate: float, overtime_hours: float
) -> dict:
    """Calculate time-and-a-half overtime rate and pay."""
    overtime_rate = hourly_rate * 1.5
    return {
        "overtime_rate": overtime_rate,
        "overtime_pay": overtime_rate * overtime_hours,
    }


@tool
def trump_taxes_vs_your_taxes_calculator(
    taxable_income: float,
    your_brackets: list[dict[str, Any]],
    trump_policy_brackets: list[dict[str, Any]],
    your_credits: float = 0.0,
    trump_policy_credits: float = 0.0,
) -> dict:
    """Compare a user's tax schedule with a specified Trump policy scenario."""
    result = _policy_comparison(
        taxable_income,
        your_brackets,
        trump_policy_brackets,
        your_credits,
        trump_policy_credits,
    )
    result["policy_label"] = "Trump policy scenario"
    return result


@tool
def vat_calculator(
    amount: float,
    vat_rate: float,
    price_includes_vat: bool = False,
) -> dict:
    """Calculate value-added tax for inclusive or exclusive prices."""
    if price_includes_vat:
        net = amount / (1 + vat_rate)
        vat = amount - net
        return {"net_amount": net, "vat": vat, "gross_amount": amount}
    vat = amount * vat_rate
    return {"net_amount": amount, "vat": vat, "gross_amount": amount + vat}


TAX_SALARY_CALCULATOR_TOOLS = (
    twelve_hour_shift_pay_calculator,
    adjusted_gross_income_calculator,
    alabama_tax_calculator,
    amt_calculator,
    annual_income_calculator,
    biden_tax_plan_calculator,
    billable_hours_calculator,
    bill_rate_calculator,
    build_back_better_calculator,
    california_sales_tax_calculator,
    california_stimulus_check_ii_calculator,
    california_tax_calculator,
    child_tax_credit_calculator,
    fica_tax_calculator,
    florida_sales_tax_calculator,
    future_salary_calculator,
    gratuity_calculator,
    gross_to_net_calculator,
    gst_calculator,
    gst_qst_canada_calculator,
    hourly_to_salary_calculator,
    illinois_tax_calculator,
    australia_income_tax_cuts_2020_21_calculator,
    philippines_income_tax_calculator,
    lottery_tax_calculator,
    modified_adjusted_gross_income_calculator,
    mileage_reimbursement_calculator,
    missouri_sales_tax_calculator,
    net_to_gross_calculator,
    new_jersey_sales_tax_calculator,
    new_york_tax_calculator,
    ohio_sales_tax_calculator,
    overtime_calculator,
    pay_raise_calculator,
    prorated_salary_calculator,
    quiz_annual_income_calculator,
    rmd_calculator,
    salary_calculator,
    salary_inflation_calculator,
    salary_to_hourly_calculator,
    sales_tax_calculator,
    state_tax_calculator,
    tax_bracket_calculator,
    texas_tax_calculator,
    time_and_a_half_calculator,
    trump_taxes_vs_your_taxes_calculator,
    vat_calculator,
)

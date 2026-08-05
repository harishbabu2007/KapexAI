"""Deterministic India-specific savings, investment, pension, and EMI tools."""

from langchain.tools import tool

from kapexai.tools.finance_calculators import _future_value
from kapexai.tools.real_estate_calculators import _payment


def _emi(principal: float, annual_rate: float, term_months: int) -> dict:
    payment = _payment(principal, annual_rate, term_months)
    total = payment * term_months
    return {
        "principal": principal,
        "monthly_emi": payment,
        "total_interest": total - principal,
        "total_payment": total,
    }


def _monthly_investment(
    monthly_investment: float,
    annual_return: float,
    years: float,
    initial_investment: float = 0.0,
    contribution_at_beginning: bool = True,
) -> dict:
    ending = _future_value(
        initial_investment,
        annual_return,
        years,
        12,
        monthly_investment,
        contribution_at_beginning,
    )
    months = round(years * 12)
    invested = initial_investment + monthly_investment * months
    return {
        "future_value": ending,
        "total_invested": invested,
        "estimated_gain": ending - invested,
    }


@tool
def atal_pension_yojana_calculator(
    current_age: int,
    pension_start_age: int,
    target_monthly_pension: float,
    monthly_contribution: float,
    assumed_annual_return: float,
) -> dict:
    """Project APY corpus from contribution age to pension age.

    The official APY contribution chart depends on entry age and guaranteed
    pension selection; monthly_contribution must match the applicable chart.
    """
    years = pension_start_age - current_age
    if years <= 0:
        raise ValueError("pension_start_age must exceed current_age")
    result = _monthly_investment(
        monthly_contribution, assumed_annual_return, years
    )
    return {
        **result,
        "target_monthly_pension": target_monthly_pension,
        "contribution_years": years,
        "caution": "Verify contribution and eligibility against the current PFRDA APY chart.",
    }


@tool
def bike_emi_calculator(
    bike_price: float,
    down_payment: float,
    annual_interest_rate: float,
    term_months: int,
    processing_fee: float = 0.0,
) -> dict:
    """Calculate two-wheeler loan EMI and financing cost."""
    return _emi(
        bike_price - down_payment + processing_fee,
        annual_interest_rate,
        term_months,
    )


@tool
def car_loan_emi_calculator(
    car_price: float,
    down_payment: float,
    annual_interest_rate: float,
    term_months: int,
    processing_fee: float = 0.0,
) -> dict:
    """Calculate Indian car-loan EMI and total interest."""
    return _emi(
        car_price - down_payment + processing_fee,
        annual_interest_rate,
        term_months,
    )


@tool
def elss_calculator(
    initial_investment: float,
    monthly_sip: float,
    expected_annual_return: float,
    years: float,
    eligible_80c_investment: float | None = None,
    marginal_tax_rate: float = 0.0,
    section_80c_cap: float = 150000.0,
) -> dict:
    """Project ELSS value and optional Section 80C tax saving."""
    result = _monthly_investment(
        monthly_sip,
        expected_annual_return,
        years,
        initial_investment,
    )
    eligible = (
        result["total_invested"]
        if eligible_80c_investment is None
        else eligible_80c_investment
    )
    deduction = min(eligible, section_80c_cap)
    return {
        **result,
        "eligible_80c_deduction": deduction,
        "estimated_tax_saved": deduction * marginal_tax_rate,
        "caution": "Tax treatment depends on the applicable regime and tax year.",
    }


@tool
def emi_calculator(
    loan_amount: float, annual_interest_rate: float, term_months: int
) -> dict:
    """Calculate equated monthly instalment for an amortizing loan."""
    return _emi(loan_amount, annual_interest_rate, term_months)


@tool
def epf_calculator(
    current_balance: float,
    monthly_basic_and_da: float,
    employee_contribution_rate: float = 0.12,
    employer_epf_rate: float = 0.0367,
    annual_interest_rate: float = 0.0825,
    years: int = 10,
) -> dict:
    """Project EPF balance from employee and employer EPF contributions."""
    employee = monthly_basic_and_da * employee_contribution_rate
    employer_epf = monthly_basic_and_da * employer_epf_rate
    result = _monthly_investment(
        employee + employer_epf,
        annual_interest_rate,
        years,
        current_balance,
    )
    return {
        **result,
        "monthly_employee_contribution": employee,
        "monthly_employer_epf_contribution": employer_epf,
        "assumption_year": "FY 2025-26 interest default",
        "caution": "Employer EPS allocation and wage ceilings can change the EPF share.",
    }


@tool
def home_loan_emi_calculator(
    property_price: float,
    down_payment: float,
    annual_interest_rate: float,
    term_years: float,
    processing_fee: float = 0.0,
) -> dict:
    """Calculate Indian home-loan EMI."""
    return _emi(
        property_price - down_payment + processing_fee,
        annual_interest_rate,
        round(term_years * 12),
    )


@tool
def hra_exemption_calculator(
    annual_hra_received: float,
    annual_basic_salary_and_da: float,
    annual_rent_paid: float,
    metro_percentage: float = 0.50,
) -> dict:
    """Calculate HRA exemption as the least of the three statutory components."""
    actual_hra = annual_hra_received
    salary_percentage = annual_basic_salary_and_da * metro_percentage
    rent_excess = max(
        0.0, annual_rent_paid - annual_basic_salary_and_da * 0.10
    )
    exemption = min(actual_hra, salary_percentage, rent_excess)
    return {
        "hra_exemption": exemption,
        "taxable_hra": max(0.0, annual_hra_received - exemption),
        "components": {
            "actual_hra_received": actual_hra,
            "salary_percentage": salary_percentage,
            "rent_less_ten_percent_salary": rent_excess,
        },
        "caution": "Eligibility and metro classification require current tax-rule verification.",
    }


@tool
def lumpsum_calculator(
    investment_amount: float,
    expected_annual_return: float,
    years: float,
) -> dict:
    """Calculate future value of a one-time investment."""
    future = investment_amount * (1 + expected_annual_return) ** years
    return {
        "future_value": future,
        "estimated_gain": future - investment_amount,
    }


@tool
def sip_plus_lumpsum_calculator(
    initial_lumpsum: float,
    monthly_sip: float,
    expected_annual_return: float,
    years: float,
) -> dict:
    """Project a combined initial lump sum and monthly SIP."""
    return _monthly_investment(
        monthly_sip,
        expected_annual_return,
        years,
        initial_lumpsum,
    )


@tool
def loan_moratorium_calculator(
    outstanding_principal: float,
    annual_interest_rate: float,
    moratorium_months: int,
    remaining_term_months: int,
    interest_capitalized: bool = True,
) -> dict:
    """Calculate balance and revised EMI after a loan moratorium."""
    accrued_interest = (
        outstanding_principal
        * ((1 + annual_interest_rate / 12) ** moratorium_months - 1)
    )
    revised_principal = (
        outstanding_principal + accrued_interest
        if interest_capitalized
        else outstanding_principal
    )
    revised = _emi(
        revised_principal, annual_interest_rate, remaining_term_months
    )
    return {
        "interest_accrued_during_moratorium": accrued_interest,
        "revised_principal": revised_principal,
        "revised_monthly_emi": revised["monthly_emi"],
        "caution": "Lender capitalization and restructuring policies vary.",
    }


@tool
def nps_india_calculator(
    current_corpus: float,
    monthly_contribution: float,
    expected_annual_return: float,
    current_age: int,
    retirement_age: int = 60,
    annuity_allocation_rate: float = 0.40,
    annuity_rate: float = 0.06,
) -> dict:
    """Project NPS corpus, lump-sum portion, and estimated annuity income."""
    years = retirement_age - current_age
    if years <= 0:
        raise ValueError("retirement_age must exceed current_age")
    result = _monthly_investment(
        monthly_contribution,
        expected_annual_return,
        years,
        current_corpus,
    )
    annuity_corpus = result["future_value"] * annuity_allocation_rate
    return {
        **result,
        "annuity_corpus": annuity_corpus,
        "lump_sum_corpus": result["future_value"] - annuity_corpus,
        "estimated_monthly_annuity": annuity_corpus * annuity_rate / 12,
        "caution": "NPS exit, annuitization, and tax rules must be verified for the current year.",
    }


@tool
def personal_loan_emi_calculator(
    loan_amount: float,
    annual_interest_rate: float,
    term_months: int,
    processing_fee: float = 0.0,
) -> dict:
    """Calculate personal-loan EMI including financed processing fees."""
    return _emi(
        loan_amount + processing_fee,
        annual_interest_rate,
        term_months,
    )


@tool
def post_office_monthly_income_scheme_calculator(
    deposit_amount: float,
    annual_interest_rate: float = 0.074,
    term_years: int = 5,
) -> dict:
    """Calculate Post Office MIS monthly income and term interest."""
    monthly_income = deposit_amount * annual_interest_rate / 12
    return {
        "monthly_income": monthly_income,
        "annual_income": monthly_income * 12,
        "total_interest_over_term": monthly_income * 12 * term_years,
        "principal_returned_at_maturity": deposit_amount,
        "caution": "Verify the current quarterly small-savings rate and deposit limits.",
    }


@tool
def ppf_calculator(
    current_balance: float,
    annual_contribution: float,
    annual_interest_rate: float = 0.071,
    years: int = 15,
    annual_contribution_cap: float = 150000.0,
) -> dict:
    """Project Public Provident Fund maturity value."""
    contribution = min(annual_contribution, annual_contribution_cap)
    future = _future_value(
        current_balance,
        annual_interest_rate,
        years,
        1,
        contribution,
        True,
    )
    return {
        "maturity_value": future,
        "annual_contribution_used": contribution,
        "caution": "PPF interest is notified quarterly and contribution rules can change.",
    }


@tool
def recurring_deposit_calculator(
    monthly_deposit: float,
    annual_interest_rate: float,
    term_months: int,
) -> dict:
    """Calculate recurring-deposit maturity value."""
    years = term_months / 12
    result = _monthly_investment(
        monthly_deposit, annual_interest_rate, years
    )
    return {
        "maturity_value": result["future_value"],
        "total_deposits": result["total_invested"],
        "interest_earned": result["estimated_gain"],
    }


@tool
def sukanya_samriddhi_yojana_calculator(
    current_balance: float,
    annual_contribution: float,
    annual_interest_rate: float = 0.082,
    contribution_years: int = 15,
    maturity_years: int = 21,
    annual_contribution_cap: float = 150000.0,
) -> dict:
    """Project Sukanya Samriddhi account value through maturity."""
    contribution = min(annual_contribution, annual_contribution_cap)
    balance = current_balance
    for year in range(maturity_years):
        if year < contribution_years:
            balance += contribution
        balance *= 1 + annual_interest_rate
    return {
        "maturity_value": balance,
        "annual_contribution_used": contribution,
        "caution": "Verify the current quarterly rate, eligibility, and withdrawal rules.",
    }


@tool
def systematic_withdrawal_plan_calculator(
    initial_investment: float,
    expected_annual_return: float,
    monthly_withdrawal: float,
    years: int,
) -> dict:
    """Simulate a systematic withdrawal plan."""
    balance = initial_investment
    monthly_rate = expected_annual_return / 12
    months = years * 12
    total_withdrawn = 0.0
    for month in range(1, months + 1):
        balance *= 1 + monthly_rate
        withdrawal = min(balance, monthly_withdrawal)
        balance -= withdrawal
        total_withdrawn += withdrawal
        if balance <= 0:
            return {
                "ending_balance": 0.0,
                "total_withdrawn": total_withdrawn,
                "depleted_in_month": month,
            }
    return {
        "ending_balance": balance,
        "total_withdrawn": total_withdrawn,
        "depleted_in_month": None,
    }


@tool
def sip_calculator(
    monthly_investment: float,
    expected_annual_return: float,
    years: float,
) -> dict:
    """Calculate systematic investment plan future value."""
    return _monthly_investment(
        monthly_investment, expected_annual_return, years
    )


@tool
def tds_interest_calculator(
    tds_amount: float,
    months_delayed: int,
    delay_type: str = "deduction",
    monthly_interest_rate_for_late_deduction: float = 0.01,
    monthly_interest_rate_for_late_payment: float = 0.015,
) -> dict:
    """Estimate Indian TDS interest for late deduction or late payment."""
    rate = (
        monthly_interest_rate_for_late_payment
        if delay_type == "payment"
        else monthly_interest_rate_for_late_deduction
    )
    return {
        "interest_rate_per_month": rate,
        "interest": tds_amount * rate * months_delayed,
        "caution": "Month counting and statutory applicability require current tax-law verification.",
    }


INDIAN_FINANCE_CALCULATOR_TOOLS = (
    atal_pension_yojana_calculator,
    bike_emi_calculator,
    car_loan_emi_calculator,
    elss_calculator,
    emi_calculator,
    epf_calculator,
    home_loan_emi_calculator,
    hra_exemption_calculator,
    lumpsum_calculator,
    sip_plus_lumpsum_calculator,
    loan_moratorium_calculator,
    nps_india_calculator,
    personal_loan_emi_calculator,
    post_office_monthly_income_scheme_calculator,
    ppf_calculator,
    recurring_deposit_calculator,
    sukanya_samriddhi_yojana_calculator,
    systematic_withdrawal_plan_calculator,
    sip_calculator,
    tds_interest_calculator,
)

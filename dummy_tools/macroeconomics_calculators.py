"""Deterministic macroeconomics and banking-liquidity calculator tools."""

import math

from langchain.tools import tool


def _ratio(a: float, b: float, name: str) -> float:
    if b == 0:
        raise ValueError(f"{name} denominator cannot be zero")
    return a / b


@tool
def buying_power_calculator(amount: float, starting_price_index: float, ending_price_index: float) -> dict:
    """Calculate inflation-adjusted buying power."""
    return {"ending_buying_power": amount * starting_price_index / ending_price_index, "purchasing_power_change": starting_price_index / ending_price_index - 1}


@tool
def carry_trade_calculator(borrowed_amount: float, borrowing_rate: float, investment_rate: float, funding_currency_change: float = 0.0, transaction_costs: float = 0.0) -> dict:
    """Estimate carry-trade profit including exchange-rate movement."""
    investment_value = borrowed_amount * (1 + investment_rate) * (1 + funding_currency_change)
    repayment = borrowed_amount * (1 + borrowing_rate)
    return {"gross_carry": investment_value - repayment, "net_profit": investment_value - repayment - transaction_costs}


@tool
def cobb_douglas_production_function_calculator(total_factor_productivity: float, capital: float, labor: float, capital_share: float) -> dict:
    """Calculate Cobb-Douglas production."""
    return {"output": total_factor_productivity * capital ** capital_share * labor ** (1 - capital_share)}


@tool
def comparative_advantage_calculator(country_a_opportunity_cost: float, country_b_opportunity_cost: float) -> dict:
    """Identify which country has comparative advantage in a good."""
    if country_a_opportunity_cost == country_b_opportunity_cost:
        winner = "equal"
    else:
        winner = "country_a" if country_a_opportunity_cost < country_b_opportunity_cost else "country_b"
    return {"comparative_advantage": winner}


@tool
def cpi_inflation_calculator(starting_cpi: float, ending_cpi: float) -> dict:
    """Calculate CPI inflation rate."""
    return {"inflation_rate": ending_cpi / starting_cpi - 1}


@tool
def currency_forward_calculator(spot_rate: float, domestic_interest_rate: float, foreign_interest_rate: float, years: float) -> dict:
    """Calculate covered-interest-parity forward exchange rate."""
    return {"forward_rate": spot_rate * (1 + domestic_interest_rate) ** years / (1 + foreign_interest_rate) ** years}


@tool
def deadweight_loss_calculator(quantity_reduction: float, wedge_per_unit: float) -> dict:
    """Calculate triangular deadweight loss."""
    return {"deadweight_loss": 0.5 * quantity_reduction * wedge_per_unit}


@tool
def discretionary_income_calculator(disposable_income: float, essential_expenses: float) -> dict:
    """Calculate discretionary income after essential expenses."""
    return {"discretionary_income": disposable_income - essential_expenses}


@tool
def disposable_income_calculator(gross_income: float, taxes: float, mandatory_contributions: float = 0.0) -> dict:
    """Calculate disposable income."""
    return {"disposable_income": gross_income - taxes - mandatory_contributions}


@tool
def fisher_effect_calculator(real_interest_rate: float, expected_inflation_rate: float) -> dict:
    """Calculate exact nominal rate under the Fisher effect."""
    return {"nominal_interest_rate": (1 + real_interest_rate) * (1 + expected_inflation_rate) - 1}


@tool
def fisher_equation_calculator(nominal_interest_rate: float, inflation_rate: float) -> dict:
    """Calculate exact real interest rate from nominal rate and inflation."""
    return {"real_interest_rate": (1 + nominal_interest_rate) / (1 + inflation_rate) - 1}


@tool
def gdp_calculator(consumption: float, investment: float, government_spending: float, exports: float, imports: float) -> dict:
    """Calculate expenditure-side GDP."""
    return {"gross_domestic_product": consumption + investment + government_spending + exports - imports}


@tool
def gdp_deflator_calculator(nominal_gdp: float, real_gdp: float) -> dict:
    """Calculate GDP deflator index."""
    return {"gdp_deflator": _ratio(nominal_gdp, real_gdp, "GDP deflator") * 100}


@tool
def gdp_gap_calculator(actual_gdp: float, potential_gdp: float) -> dict:
    """Calculate output gap as a share of potential GDP."""
    return {"gdp_gap": _ratio(actual_gdp - potential_gdp, potential_gdp, "GDP gap")}


@tool
def lcr_calculator(high_quality_liquid_assets: float, net_cash_outflows_30_days: float) -> dict:
    """Calculate Basel Liquidity Coverage Ratio."""
    return {"liquidity_coverage_ratio": _ratio(high_quality_liquid_assets, net_cash_outflows_30_days, "LCR"), "regulatory_reference": "Basel III"}


@tool
def mpc_calculator(change_in_consumption: float, change_in_disposable_income: float) -> dict:
    """Calculate marginal propensity to consume."""
    return {"marginal_propensity_to_consume": _ratio(change_in_consumption, change_in_disposable_income, "MPC")}


@tool
def money_multiplier_calculator(reserve_ratio: float, currency_deposit_ratio: float = 0.0, excess_reserve_ratio: float = 0.0) -> dict:
    """Calculate simple or currency-adjusted money multiplier."""
    return {"money_multiplier": (1 + currency_deposit_ratio) / (reserve_ratio + currency_deposit_ratio + excess_reserve_ratio)}


@tool
def money_supply_calculator(monetary_base: float, money_multiplier: float) -> dict:
    """Calculate money supply from base money and multiplier."""
    return {"money_supply": monetary_base * money_multiplier}


@tool
def mps_calculator(change_in_saving: float, change_in_disposable_income: float) -> dict:
    """Calculate marginal propensity to save."""
    return {"marginal_propensity_to_save": _ratio(change_in_saving, change_in_disposable_income, "MPS")}


@tool
def natural_rate_of_unemployment_calculator(frictional_unemployment_rate: float, structural_unemployment_rate: float) -> dict:
    """Estimate natural unemployment as frictional plus structural unemployment."""
    return {"natural_unemployment_rate": frictional_unemployment_rate + structural_unemployment_rate}


@tool
def nsfr_calculator(available_stable_funding: float, required_stable_funding: float) -> dict:
    """Calculate Basel Net Stable Funding Ratio."""
    return {"net_stable_funding_ratio": _ratio(available_stable_funding, required_stable_funding, "NSFR"), "regulatory_reference": "Basel III"}


@tool
def okuns_law_calculator(actual_unemployment_rate: float, natural_unemployment_rate: float, okun_coefficient: float = 2.0) -> dict:
    """Estimate output gap using Okun's law."""
    return {"estimated_output_gap": -okun_coefficient * (actual_unemployment_rate - natural_unemployment_rate)}


@tool
def phillips_curve_calculator(expected_inflation: float, natural_unemployment_rate: float, actual_unemployment_rate: float, sensitivity: float, supply_shock: float = 0.0) -> dict:
    """Estimate inflation from an expectations-augmented Phillips curve."""
    return {"inflation_rate": expected_inflation - sensitivity * (actual_unemployment_rate - natural_unemployment_rate) + supply_shock}


@tool
def ppp_calculator(domestic_price: float, foreign_price: float) -> dict:
    """Calculate purchasing-power-parity exchange rate."""
    return {"ppp_exchange_rate": _ratio(domestic_price, foreign_price, "PPP")}


@tool
def price_elasticity_of_supply_calculator(quantity_one: float, quantity_two: float, price_one: float, price_two: float) -> dict:
    """Calculate midpoint price elasticity of supply."""
    quantity_change = (quantity_two - quantity_one) / ((quantity_one + quantity_two) / 2)
    price_change = (price_two - price_one) / ((price_one + price_two) / 2)
    return {"price_elasticity_of_supply": _ratio(quantity_change, price_change, "supply elasticity")}


@tool
def private_savings_calculator(disposable_income: float, consumption: float) -> dict:
    """Calculate private saving."""
    return {"private_savings": disposable_income - consumption}


@tool
def real_gdp_calculator(nominal_gdp: float, gdp_deflator: float) -> dict:
    """Calculate real GDP from nominal GDP and a base-100 deflator."""
    return {"real_gdp": nominal_gdp / (gdp_deflator / 100)}


@tool
def real_interest_rate_calculator(nominal_interest_rate: float, inflation_rate: float) -> dict:
    """Calculate exact real interest rate."""
    return {"real_interest_rate": (1 + nominal_interest_rate) / (1 + inflation_rate) - 1}


@tool
def gdp_growth_rate_calculator(prior_real_gdp: float, current_real_gdp: float) -> dict:
    """Calculate real GDP growth."""
    return {"gdp_growth_rate": current_real_gdp / prior_real_gdp - 1}


@tool
def gdp_per_capita_calculator(gdp: float, population: float) -> dict:
    """Calculate GDP per capita."""
    return {"gdp_per_capita": _ratio(gdp, population, "GDP per capita")}


@tool
def gini_coefficient_calculator(incomes: list[float]) -> dict:
    """Calculate Gini coefficient from nonnegative incomes."""
    values = sorted(incomes)
    if not values or any(value < 0 for value in values):
        raise ValueError("incomes must be a non-empty nonnegative list")
    total = sum(values)
    if total == 0:
        return {"gini_coefficient": 0.0}
    n = len(values)
    weighted = sum((index + 1) * value for index, value in enumerate(values))
    return {"gini_coefficient": 2 * weighted / (n * total) - (n + 1) / n}


@tool
def inflation_calculator(starting_price: float, ending_price: float, years: float = 1.0) -> dict:
    """Calculate total and annualized inflation."""
    total = ending_price / starting_price - 1
    return {"total_inflation": total, "annualized_inflation": (ending_price / starting_price) ** (1 / years) - 1}


@tool
def interest_rate_parity_calculator(spot_rate: float, domestic_interest_rate: float, foreign_interest_rate: float, years: float = 1.0) -> dict:
    """Calculate forward exchange rate under interest-rate parity."""
    return {"implied_forward_rate": spot_rate * (1 + domestic_interest_rate) ** years / (1 + foreign_interest_rate) ** years}


@tool
def labor_force_participation_rate_calculator(labor_force: float, working_age_population: float) -> dict:
    """Calculate labor force participation rate."""
    return {"labor_force_participation_rate": _ratio(labor_force, working_age_population, "participation rate")}


@tool
def reserve_ratio_calculator(reserves: float, deposits: float) -> dict:
    """Calculate bank reserve ratio."""
    return {"reserve_ratio": _ratio(reserves, deposits, "reserve ratio")}


@tool
def spending_multiplier_calculator(marginal_propensity_to_consume: float) -> dict:
    """Calculate Keynesian spending multiplier."""
    return {"spending_multiplier": 1 / (1 - marginal_propensity_to_consume)}


@tool
def taylor_rule_calculator(neutral_nominal_rate: float, current_inflation: float, target_inflation: float, output_gap: float, inflation_weight: float = 0.5, output_gap_weight: float = 0.5) -> dict:
    """Calculate a configurable Taylor-rule policy rate."""
    rate = neutral_nominal_rate + current_inflation + inflation_weight * (current_inflation - target_inflation) + output_gap_weight * output_gap
    return {"suggested_policy_rate": rate}


@tool
def trump_tariff_calculator(import_value: float, tariff_rate: float, pass_through_rate: float = 1.0, domestic_substitution_savings: float = 0.0) -> dict:
    """Model a configurable Trump tariff scenario without assuming a current rate."""
    tariff = import_value * tariff_rate
    consumer_cost = tariff * pass_through_rate - domestic_substitution_savings
    return {"tariff_revenue": tariff, "estimated_passed_through_cost": consumer_cost, "policy_scenario": True}


@tool
def unemployment_rate_calculator(unemployed_people: float, labor_force: float) -> dict:
    """Calculate unemployment rate."""
    return {"unemployment_rate": _ratio(unemployed_people, labor_force, "unemployment rate")}


@tool
def velocity_of_money_calculator(nominal_gdp: float, money_supply: float) -> dict:
    """Calculate velocity of money."""
    return {"velocity_of_money": _ratio(nominal_gdp, money_supply, "velocity")}


MACROECONOMICS_CALCULATOR_TOOLS = (
    buying_power_calculator, carry_trade_calculator,
    cobb_douglas_production_function_calculator,
    comparative_advantage_calculator, cpi_inflation_calculator,
    currency_forward_calculator, deadweight_loss_calculator,
    discretionary_income_calculator, disposable_income_calculator,
    fisher_effect_calculator, fisher_equation_calculator, gdp_calculator,
    gdp_deflator_calculator, gdp_gap_calculator, lcr_calculator,
    mpc_calculator, money_multiplier_calculator, money_supply_calculator,
    mps_calculator, natural_rate_of_unemployment_calculator,
    nsfr_calculator, okuns_law_calculator, phillips_curve_calculator,
    ppp_calculator, price_elasticity_of_supply_calculator,
    private_savings_calculator, real_gdp_calculator,
    real_interest_rate_calculator, gdp_growth_rate_calculator,
    gdp_per_capita_calculator, gini_coefficient_calculator,
    inflation_calculator, interest_rate_parity_calculator,
    labor_force_participation_rate_calculator, reserve_ratio_calculator,
    spending_multiplier_calculator, taylor_rule_calculator,
    trump_tariff_calculator, unemployment_rate_calculator,
    velocity_of_money_calculator,
)

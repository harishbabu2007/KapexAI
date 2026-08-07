"""Deterministic microeconomics, accounting, and operating calculators."""

import math

from langchain.tools import tool


def _ratio(a: float, b: float, name: str) -> float:
    if b == 0:
        raise ValueError(f"{name} denominator cannot be zero")
    return a / b


def _elasticity(q1: float, q2: float, x1: float, x2: float) -> float:
    quantity_change = _ratio(q2 - q1, (q1 + q2) / 2, "quantity midpoint")
    x_change = _ratio(x2 - x1, (x1 + x2) / 2, "driver midpoint")
    return _ratio(quantity_change, x_change, "elasticity")


@tool
def accounting_profit_calculator(revenue: float, explicit_costs: float) -> dict:
    """Calculate accounting profit."""
    return {"accounting_profit": revenue - explicit_costs}


@tool
def accrual_ratio_calculator(net_income: float, operating_cash_flow: float, average_total_assets: float) -> dict:
    """Calculate balance-sheet-scaled accrual ratio."""
    return {"accrual_ratio": _ratio(net_income - operating_cash_flow, average_total_assets, "accrual ratio")}


@tool
def actual_cash_value_calculator(replacement_cost: float, depreciation: float) -> dict:
    """Calculate insurance actual cash value."""
    return {"actual_cash_value": max(0.0, replacement_cost - depreciation)}


@tool
def average_variable_cost_calculator(total_variable_cost: float, quantity: float) -> dict:
    """Calculate average variable cost."""
    return {"average_variable_cost": _ratio(total_variable_cost, quantity, "average variable cost")}


@tool
def cash_conversion_cycle_calculator(days_inventory_outstanding: float, days_sales_outstanding: float, days_payables_outstanding: float) -> dict:
    """Calculate cash conversion cycle."""
    return {"cash_conversion_cycle_days": days_inventory_outstanding + days_sales_outstanding - days_payables_outstanding}


@tool
def cash_flow_to_debt_ratio_calculator(operating_cash_flow: float, total_debt: float) -> dict:
    """Calculate operating cash flow to debt."""
    return {"cash_flow_to_debt_ratio": _ratio(operating_cash_flow, total_debt, "cash flow to debt")}


@tool
def cash_ratio_calculator(cash: float, cash_equivalents: float, current_liabilities: float) -> dict:
    """Calculate cash ratio."""
    return {"cash_ratio": _ratio(cash + cash_equivalents, current_liabilities, "cash ratio")}


@tool
def consumer_surplus_calculator(maximum_willingness_to_pay: float, market_price: float, quantity: float = 1.0) -> dict:
    """Calculate consumer surplus for units with a common willingness to pay."""
    return {"consumer_surplus": max(0.0, maximum_willingness_to_pay - market_price) * quantity}


@tool
def cross_price_elasticity_calculator(quantity_one: float, quantity_two: float, other_price_one: float, other_price_two: float) -> dict:
    """Calculate midpoint cross-price elasticity of demand."""
    return {"cross_price_elasticity": _elasticity(quantity_one, quantity_two, other_price_one, other_price_two)}


@tool
def current_ratio_calculator(current_assets: float, current_liabilities: float) -> dict:
    """Calculate current ratio."""
    return {"current_ratio": _ratio(current_assets, current_liabilities, "current ratio")}


@tool
def dso_calculator(average_accounts_receivable: float, credit_sales: float, period_days: float = 365) -> dict:
    """Calculate days sales outstanding."""
    return {"days_sales_outstanding": _ratio(average_accounts_receivable, credit_sales, "DSO") * period_days}


@tool
def dio_calculator(average_inventory: float, cost_of_goods_sold: float, period_days: float = 365) -> dict:
    """Calculate days inventory outstanding."""
    return {"days_inventory_outstanding": _ratio(average_inventory, cost_of_goods_sold, "DIO") * period_days}


@tool
def dpo_calculator(average_accounts_payable: float, purchases_or_cogs: float, period_days: float = 365) -> dict:
    """Calculate days payable outstanding."""
    return {"days_payable_outstanding": _ratio(average_accounts_payable, purchases_or_cogs, "DPO") * period_days}


@tool
def degree_of_operating_leverage_calculator(contribution_margin: float, operating_income: float) -> dict:
    """Calculate degree of operating leverage."""
    return {"degree_of_operating_leverage": _ratio(contribution_margin, operating_income, "DOL")}


@tool
def gross_margin_calculator(revenue: float, cost_of_goods_sold: float) -> dict:
    """Calculate gross profit and gross margin."""
    profit = revenue - cost_of_goods_sold
    return {"gross_profit": profit, "gross_margin": _ratio(profit, revenue, "gross margin")}


@tool
def income_elasticity_of_demand_calculator(quantity_one: float, quantity_two: float, income_one: float, income_two: float) -> dict:
    """Calculate midpoint income elasticity of demand."""
    return {"income_elasticity": _elasticity(quantity_one, quantity_two, income_one, income_two)}


@tool
def inventory_turnover_calculator(cost_of_goods_sold: float, average_inventory: float) -> dict:
    """Calculate inventory turnover."""
    return {"inventory_turnover": _ratio(cost_of_goods_sold, average_inventory, "inventory turnover")}


@tool
def levered_free_cash_flow_calculator(net_income: float, depreciation_amortization: float, capital_expenditure: float, change_in_working_capital: float, net_borrowing: float) -> dict:
    """Calculate levered free cash flow to equity."""
    return {"levered_free_cash_flow": net_income + depreciation_amortization - capital_expenditure - change_in_working_capital + net_borrowing}


@tool
def lifo_inventory_calculator(beginning_inventory: float, purchases: list[dict[str, float]], units_sold: float) -> dict:
    """Calculate ending inventory and COGS under a simplified LIFO layer model."""
    layers = [{"units": beginning_inventory, "unit_cost": 0.0}] + [dict(item) for item in purchases]
    remaining_to_sell, cogs = units_sold, 0.0
    for layer in reversed(layers):
        sold = min(layer["units"], remaining_to_sell)
        cogs += sold * layer["unit_cost"]
        layer["units"] -= sold
        remaining_to_sell -= sold
        if remaining_to_sell <= 0:
            break
    if remaining_to_sell > 0:
        raise ValueError("units_sold exceed available inventory")
    ending = sum(layer["units"] * layer["unit_cost"] for layer in layers)
    return {"cost_of_goods_sold": cogs, "ending_inventory": ending}


@tool
def marginal_cost_calculator(change_in_total_cost: float, change_in_quantity: float) -> dict:
    """Calculate marginal cost."""
    return {"marginal_cost": _ratio(change_in_total_cost, change_in_quantity, "marginal cost")}


@tool
def marginal_revenue_calculator(change_in_total_revenue: float, change_in_quantity: float) -> dict:
    """Calculate marginal revenue."""
    return {"marginal_revenue": _ratio(change_in_total_revenue, change_in_quantity, "marginal revenue")}


@tool
def month_over_month_calculator(previous_month_value: float, current_month_value: float) -> dict:
    """Calculate month-over-month change."""
    change = current_month_value - previous_month_value
    return {"absolute_change": change, "month_over_month_rate": _ratio(change, abs(previous_month_value), "MoM")}


@tool
def net_debt_calculator(total_debt: float, cash_and_equivalents: float) -> dict:
    """Calculate net debt."""
    return {"net_debt": total_debt - cash_and_equivalents}


@tool
def net_income_calculator(revenue: float, cost_of_goods_sold: float, operating_expenses: float, interest_expense: float, taxes: float, other_income: float = 0.0) -> dict:
    """Calculate net income."""
    return {"net_income": revenue - cost_of_goods_sold - operating_expenses - interest_expense - taxes + other_income}


@tool
def net_operating_assets_calculator(operating_assets: float, operating_liabilities: float) -> dict:
    """Calculate net operating assets."""
    return {"net_operating_assets": operating_assets - operating_liabilities}


@tool
def net_operating_working_capital_calculator(operating_current_assets: float, operating_current_liabilities: float) -> dict:
    """Calculate net operating working capital."""
    return {"net_operating_working_capital": operating_current_assets - operating_current_liabilities}


@tool
def net_profit_margin_calculator(net_income: float, revenue: float) -> dict:
    """Calculate net profit margin."""
    return {"net_profit_margin": _ratio(net_income, revenue, "net profit margin")}


@tool
def operating_cash_flow_calculator(ebit: float, tax_rate: float, depreciation_amortization: float) -> dict:
    """Calculate operating cash flow as NOPAT plus noncash charges."""
    return {"operating_cash_flow": ebit * (1 - tax_rate) + depreciation_amortization}


@tool
def depreciation_calculator(asset_cost: float, salvage_value: float, useful_life: float, method: str = "straight_line") -> dict:
    """Calculate annual straight-line or first-year double-declining depreciation."""
    if method == "double_declining":
        depreciation = asset_cost * 2 / useful_life
    else:
        depreciation = (asset_cost - salvage_value) / useful_life
    return {"annual_depreciation": depreciation, "ending_book_value_after_year_one": asset_cost - depreciation}


@tool
def ebt_calculator(revenue: float, operating_expenses: float, interest_expense: float, other_income: float = 0.0) -> dict:
    """Calculate earnings before tax."""
    return {"earnings_before_tax": revenue - operating_expenses - interest_expense + other_income}


@tool
def ebit_calculator(net_income: float, interest_expense: float, income_tax: float) -> dict:
    """Calculate earnings before interest and tax."""
    return {"ebit": net_income + interest_expense + income_tax}


@tool
def ebitda_calculator(net_income: float, interest_expense: float, income_tax: float, depreciation: float, amortization: float) -> dict:
    """Calculate EBITDA."""
    return {"ebitda": net_income + interest_expense + income_tax + depreciation + amortization}


@tool
def ebitda_margin_calculator(ebitda: float, revenue: float) -> dict:
    """Calculate EBITDA margin."""
    return {"ebitda_margin": _ratio(ebitda, revenue, "EBITDA margin")}


@tool
def eoq_calculator(annual_demand: float, ordering_cost: float, annual_holding_cost_per_unit: float) -> dict:
    """Calculate economic order quantity."""
    return {"economic_order_quantity": math.sqrt(2 * annual_demand * ordering_cost / annual_holding_cost_per_unit)}


@tool
def economic_profit_calculator(accounting_profit: float, opportunity_cost_of_capital: float) -> dict:
    """Calculate economic profit after implicit opportunity costs."""
    return {"economic_profit": accounting_profit - opportunity_cost_of_capital}


@tool
def ending_inventory_calculator(beginning_inventory: float, purchases: float, cost_of_goods_sold: float) -> dict:
    """Calculate ending inventory."""
    return {"ending_inventory": beginning_inventory + purchases - cost_of_goods_sold}


@tool
def financial_leverage_ratio_calculator(average_total_assets: float, average_shareholders_equity: float) -> dict:
    """Calculate financial leverage ratio."""
    return {"financial_leverage_ratio": _ratio(average_total_assets, average_shareholders_equity, "financial leverage")}


@tool
def fixed_asset_turnover_ratio_calculator(revenue: float, average_net_fixed_assets: float) -> dict:
    """Calculate fixed asset turnover."""
    return {"fixed_asset_turnover": _ratio(revenue, average_net_fixed_assets, "fixed asset turnover")}


@tool
def free_cash_flow_calculator(operating_cash_flow: float, capital_expenditures: float) -> dict:
    """Calculate free cash flow."""
    return {"free_cash_flow": operating_cash_flow - capital_expenditures}


@tool
def fcfe_calculator(net_income: float, depreciation_amortization: float, capital_expenditure: float, change_in_working_capital: float, net_borrowing: float) -> dict:
    """Calculate free cash flow to equity."""
    return {"free_cash_flow_to_equity": net_income + depreciation_amortization - capital_expenditure - change_in_working_capital + net_borrowing}


@tool
def fcff_calculator(ebit: float, tax_rate: float, depreciation_amortization: float, capital_expenditure: float, change_in_working_capital: float) -> dict:
    """Calculate free cash flow to firm."""
    return {"free_cash_flow_to_firm": ebit * (1 - tax_rate) + depreciation_amortization - capital_expenditure - change_in_working_capital}


@tool
def ffo_calculator(net_income: float, real_estate_depreciation_amortization: float, gains_on_property_sales: float) -> dict:
    """Calculate REIT funds from operations."""
    return {"funds_from_operations": net_income + real_estate_depreciation_amortization - gains_on_property_sales}


@tool
def goodwill_calculator(purchase_price: float, fair_value_identifiable_assets: float, fair_value_liabilities: float, noncontrolling_interest: float = 0.0) -> dict:
    """Calculate acquisition goodwill."""
    return {"goodwill": purchase_price + noncontrolling_interest - (fair_value_identifiable_assets - fair_value_liabilities)}


@tool
def operating_margin_calculator(operating_income: float, revenue: float) -> dict:
    """Calculate operating margin."""
    return {"operating_margin": _ratio(operating_income, revenue, "operating margin")}


@tool
def optimal_price_calculator(demand_intercept: float, demand_slope: float, constant_marginal_cost: float) -> dict:
    """Calculate monopoly price for linear demand Q=a-bP and constant marginal cost."""
    if demand_slope <= 0:
        raise ValueError("demand_slope must be positive")
    price = (demand_intercept / demand_slope + constant_marginal_cost) / 2
    quantity = max(0.0, demand_intercept - demand_slope * price)
    return {"optimal_price": price, "optimal_quantity": quantity}


@tool
def price_elasticity_of_demand_calculator(quantity_one: float, quantity_two: float, price_one: float, price_two: float) -> dict:
    """Calculate midpoint price elasticity of demand."""
    return {"price_elasticity_of_demand": _elasticity(quantity_one, quantity_two, price_one, price_two)}


@tool
def productivity_calculator(output: float, input_units: float) -> dict:
    """Calculate output per unit of input."""
    return {"productivity": _ratio(output, input_units, "productivity")}


@tool
def profit_calculator(revenue: float, total_cost: float) -> dict:
    """Calculate profit."""
    return {"profit": revenue - total_cost}


@tool
def receivables_turnover_ratio_calculator(net_credit_sales: float, average_accounts_receivable: float) -> dict:
    """Calculate receivables turnover."""
    return {"receivables_turnover": _ratio(net_credit_sales, average_accounts_receivable, "receivables turnover")}


@tool
def retained_earnings_calculator(beginning_retained_earnings: float, net_income: float, dividends: float) -> dict:
    """Calculate ending retained earnings."""
    return {"ending_retained_earnings": beginning_retained_earnings + net_income - dividends}


@tool
def revenue_calculator(unit_price: float, units_sold: float, other_revenue: float = 0.0) -> dict:
    """Calculate total revenue."""
    return {"revenue": unit_price * units_sold + other_revenue}


@tool
def revenue_growth_calculator(prior_revenue: float, current_revenue: float) -> dict:
    """Calculate revenue growth."""
    return {"revenue_growth_rate": _ratio(current_revenue - prior_revenue, abs(prior_revenue), "revenue growth")}


@tool
def sales_calculator(unit_price: float, units_sold: float, discounts_returns_allowances: float = 0.0) -> dict:
    """Calculate gross and net sales."""
    gross = unit_price * units_sold
    return {"gross_sales": gross, "net_sales": gross - discounts_returns_allowances}


@tool
def total_asset_turnover_calculator(revenue: float, average_total_assets: float) -> dict:
    """Calculate total asset turnover."""
    return {"total_asset_turnover": _ratio(revenue, average_total_assets, "asset turnover")}


@tool
def unlevered_free_cash_flow_calculator(ebit: float, tax_rate: float, depreciation_amortization: float, capital_expenditures: float, change_in_working_capital: float) -> dict:
    """Calculate unlevered free cash flow."""
    return {"unlevered_free_cash_flow": ebit * (1 - tax_rate) + depreciation_amortization - capital_expenditures - change_in_working_capital}


@tool
def working_capital_calculator(current_assets: float, current_liabilities: float) -> dict:
    """Calculate working capital."""
    return {"working_capital": current_assets - current_liabilities}


@tool
def working_capital_turnover_ratio_calculator(revenue: float, average_working_capital: float) -> dict:
    """Calculate working capital turnover."""
    return {"working_capital_turnover": _ratio(revenue, average_working_capital, "working capital turnover")}


MICROECONOMICS_CALCULATOR_TOOLS = (
    accounting_profit_calculator, accrual_ratio_calculator, actual_cash_value_calculator,
    average_variable_cost_calculator, cash_conversion_cycle_calculator,
    cash_flow_to_debt_ratio_calculator, cash_ratio_calculator,
    consumer_surplus_calculator, cross_price_elasticity_calculator,
    current_ratio_calculator, dso_calculator, dio_calculator, dpo_calculator,
    degree_of_operating_leverage_calculator, gross_margin_calculator,
    income_elasticity_of_demand_calculator, inventory_turnover_calculator,
    levered_free_cash_flow_calculator, lifo_inventory_calculator,
    marginal_cost_calculator, marginal_revenue_calculator,
    month_over_month_calculator, net_debt_calculator, net_income_calculator,
    net_operating_assets_calculator, net_operating_working_capital_calculator,
    net_profit_margin_calculator, operating_cash_flow_calculator,
    depreciation_calculator, ebt_calculator, ebit_calculator,
    ebitda_calculator, ebitda_margin_calculator, eoq_calculator,
    economic_profit_calculator, ending_inventory_calculator,
    financial_leverage_ratio_calculator, fixed_asset_turnover_ratio_calculator,
    free_cash_flow_calculator, fcfe_calculator, fcff_calculator,
    ffo_calculator, goodwill_calculator, operating_margin_calculator,
    optimal_price_calculator, price_elasticity_of_demand_calculator,
    productivity_calculator, profit_calculator,
    receivables_turnover_ratio_calculator, retained_earnings_calculator,
    revenue_calculator, revenue_growth_calculator, sales_calculator,
    total_asset_turnover_calculator, unlevered_free_cash_flow_calculator,
    working_capital_calculator, working_capital_turnover_ratio_calculator,
)

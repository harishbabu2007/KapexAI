"""Deterministic sales, pricing, discount, and commission calculator tools."""

from langchain.tools import tool


def _discount(price: float, rates: list[float]) -> dict:
    final = price
    for rate in rates:
        final *= 1 - rate
    return {
        "original_price": price,
        "final_price": final,
        "total_discount": price - final,
        "effective_discount_rate": 1 - final / price if price else 0.0,
    }


def _margin(revenue: float, cost: float) -> dict:
    profit = revenue - cost
    return {
        "profit": profit,
        "margin": profit / revenue if revenue else None,
        "markup": profit / cost if cost else None,
    }


@tool
def black_friday_calculator(original_price: float, discount_rate: float, sales_tax_rate: float = 0.0) -> dict:
    """Calculate Black Friday discounted price and tax."""
    result = _discount(original_price, [discount_rate])
    tax = result["final_price"] * sales_tax_rate
    return {**result, "sales_tax": tax, "checkout_total": result["final_price"] + tax}


@tool
def cash_back_calculator(purchase_amount: float, cash_back_rate: float, cash_back_cap: float | None = None) -> dict:
    """Calculate card or retailer cash-back rewards."""
    reward = purchase_amount * cash_back_rate
    if cash_back_cap is not None:
        reward = min(reward, cash_back_cap)
    return {"cash_back": reward, "net_effective_cost": purchase_amount - reward}


@tool
def check_digit_calculator(number: str, algorithm: str = "luhn") -> dict:
    """Calculate a Luhn or modulo-10 check digit."""
    digits = [int(character) for character in number if character.isdigit()]
    if not digits:
        raise ValueError("number must contain digits")
    if algorithm == "luhn":
        total = 0
        parity = (len(digits) + 1) % 2
        for index, digit in enumerate(digits):
            value = digit * 2 if index % 2 == parity else digit
            total += value - 9 if value > 9 else value
        check = (10 - total % 10) % 10
    else:
        check = (10 - sum(digits) % 10) % 10
    return {"check_digit": check, "number_with_check_digit": f"{number}{check}"}


@tool
def cltv_calculator(average_purchase_value: float, purchase_frequency_per_year: float, customer_lifespan_years: float, gross_margin_rate: float = 1.0, acquisition_cost: float = 0.0) -> dict:
    """Calculate customer lifetime value from purchasing behavior."""
    revenue = average_purchase_value * purchase_frequency_per_year * customer_lifespan_years
    return {"lifetime_revenue": revenue, "customer_lifetime_value": revenue * gross_margin_rate - acquisition_cost}


@tool
def commission_calculator(sales_amount: float, commission_rate: float, base_pay: float = 0.0, threshold: float = 0.0) -> dict:
    """Calculate sales commission and total compensation."""
    commissionable = max(0.0, sales_amount - threshold)
    commission = commissionable * commission_rate
    return {"commissionable_sales": commissionable, "commission": commission, "total_compensation": base_pay + commission}


@tool
def cyber_monday_calculator(original_price: float, discount_rate: float, coupon_rate: float = 0.0, sales_tax_rate: float = 0.0) -> dict:
    """Calculate Cyber Monday stacked discounts and checkout total."""
    result = _discount(original_price, [discount_rate, coupon_rate])
    return {**result, "checkout_total": result["final_price"] * (1 + sales_tax_rate)}


@tool
def discount_calculator(original_price: float, discount_rate: float) -> dict:
    """Calculate discounted price and savings."""
    return _discount(original_price, [discount_rate])


@tool
def double_discount_calculator(original_price: float, first_discount_rate: float, second_discount_rate: float) -> dict:
    """Calculate two sequential discounts."""
    return _discount(original_price, [first_discount_rate, second_discount_rate])


@tool
def margin_calculator(revenue: float, cost: float) -> dict:
    """Calculate gross profit, margin, and markup."""
    return _margin(revenue, cost)


@tool
def margin_and_sales_tax_calculator(cost: float, target_margin_rate: float, sales_tax_rate: float) -> dict:
    """Calculate selling price needed for a target margin and tax-inclusive total."""
    if target_margin_rate >= 1:
        raise ValueError("target_margin_rate must be below 1")
    price = cost / (1 - target_margin_rate)
    return {"pre_tax_selling_price": price, "sales_tax": price * sales_tax_rate, "customer_total": price * (1 + sales_tax_rate)}


@tool
def margin_and_vat_calculator(cost: float, target_margin_rate: float, vat_rate: float) -> dict:
    """Calculate margin-based net price and VAT-inclusive price."""
    if target_margin_rate >= 1:
        raise ValueError("target_margin_rate must be below 1")
    net = cost / (1 - target_margin_rate)
    return {"net_selling_price": net, "vat": net * vat_rate, "gross_selling_price": net * (1 + vat_rate)}


@tool
def margin_calculator_classic(selling_price: float, purchase_cost: float) -> dict:
    """Calculate classic gross margin from selling price and purchase cost."""
    return _margin(selling_price, purchase_cost)


@tool
def margin_with_discount_calculator(list_price: float, cost: float, discount_rate: float) -> dict:
    """Calculate profit margin after a selling-price discount."""
    discounted = list_price * (1 - discount_rate)
    return {"discounted_price": discounted, **_margin(discounted, cost)}


@tool
def markdown_calculator(original_price: float, sale_price: float) -> dict:
    """Calculate markdown amount and percentage."""
    markdown = original_price - sale_price
    return {"markdown": markdown, "markdown_rate": markdown / original_price if original_price else None}


@tool
def markup_calculator(cost: float, markup_rate: float) -> dict:
    """Calculate selling price from cost and markup rate."""
    markup = cost * markup_rate
    return {"markup": markup, "selling_price": cost + markup}


@tool
def margin_and_markup_calculator(cost: float, selling_price: float) -> dict:
    """Calculate margin and markup together."""
    return _margin(selling_price, cost)


@tool
def markup_calculator_classic(cost: float, selling_price: float) -> dict:
    """Calculate classic markup amount and rate."""
    profit = selling_price - cost
    return {"markup": profit, "markup_rate": profit / cost if cost else None}


@tool
def paypal_fee_calculator(transaction_amount: float, percentage_fee: float, fixed_fee: float, cross_border_fee_rate: float = 0.0) -> dict:
    """Calculate PayPal-style transaction fees from explicit current rates."""
    fee = transaction_amount * (percentage_fee + cross_border_fee_rate) + fixed_fee
    return {"fee": fee, "net_received": transaction_amount - fee, "caution": "Use the current fee schedule for account type, country, and currency."}


@tool
def percentage_discount_calculator(original_price: float, sale_price: float) -> dict:
    """Derive percentage discount from original and sale prices."""
    return {"discount_rate": (original_price - sale_price) / original_price if original_price else None}


@tool
def percent_off_calculator(original_price: float, percent_off: float) -> dict:
    """Calculate price after a stated percent-off discount."""
    return _discount(original_price, [percent_off])


@tool
def triple_discount_calculator(original_price: float, first_rate: float, second_rate: float, third_rate: float) -> dict:
    """Calculate three sequential discounts."""
    return _discount(original_price, [first_rate, second_rate, third_rate])


SALES_CALCULATOR_TOOLS = (
    black_friday_calculator, cash_back_calculator, check_digit_calculator,
    cltv_calculator, commission_calculator, cyber_monday_calculator,
    discount_calculator, double_discount_calculator, margin_calculator,
    margin_and_sales_tax_calculator, margin_and_vat_calculator,
    margin_calculator_classic, margin_with_discount_calculator,
    markdown_calculator, markup_calculator, margin_and_markup_calculator,
    markup_calculator_classic, paypal_fee_calculator,
    percentage_discount_calculator, percent_off_calculator,
    triple_discount_calculator,
)

"""Financial, accounting, valuation, and public-filing tools."""

import math
from statistics import mean, pstdev
from typing import Any

from langchain.tools import tool

from kapexai.tools.runtime import cached_json, require_env


def _sec_headers() -> dict[str, str]:
    identity = require_env("SEC_USER_AGENT")
    return {
        "User-Agent": identity,
        "Accept-Encoding": "gzip, deflate",
        "Host": "data.sec.gov",
    }


def _normalize_cik(cik: str | int) -> str:
    digits = "".join(character for character in str(cik) if character.isdigit())
    if not digits or len(digits) > 10:
        raise ValueError("CIK must contain between 1 and 10 digits")
    return digits.zfill(10)


@tool
def sec_company_lookup(ticker: str) -> dict:
    """Resolve a U.S. public-company ticker to its SEC CIK and legal name.

    Requires SEC_USER_AGENT containing an application name and contact email.
    """
    require_env("SEC_USER_AGENT")
    payload = cached_json(
        "GET",
        "https://www.sec.gov/files/company_tickers.json",
        headers={"User-Agent": require_env("SEC_USER_AGENT")},
        ttl_seconds=86400,
    )
    target = ticker.upper()
    for item in payload.values():
        if str(item.get("ticker", "")).upper() == target:
            return {
                "ticker": target,
                "cik": str(item.get("cik_str")).zfill(10),
                "name": item.get("title"),
                "source": "https://www.sec.gov/files/company_tickers.json",
            }
    return {
        "ticker": target,
        "cik": None,
        "name": None,
        "source": "https://www.sec.gov/files/company_tickers.json",
    }


@tool
def sec_company_submissions(
    cik: str,
    forms: list[str] | None = None,
    limit: int = 25,
) -> dict:
    """Retrieve recent SEC filing metadata for a company CIK."""
    normalized = _normalize_cik(cik)
    url = f"https://data.sec.gov/submissions/CIK{normalized}.json"
    payload = cached_json(
        "GET",
        url,
        headers=_sec_headers(),
        ttl_seconds=3600,
    )
    recent = payload.get("filings", {}).get("recent", {})
    accepted_forms = {form.upper() for form in (forms or [])}
    filings = []
    count = len(recent.get("accessionNumber", []))
    for index in range(count):
        form = recent.get("form", [None] * count)[index]
        if accepted_forms and str(form).upper() not in accepted_forms:
            continue
        accession = recent.get("accessionNumber", [None] * count)[index]
        accession_path = str(accession).replace("-", "")
        primary_document = recent.get("primaryDocument", [None] * count)[index]
        filings.append(
            {
                "form": form,
                "filing_date": recent.get("filingDate", [None] * count)[index],
                "report_date": recent.get("reportDate", [None] * count)[index],
                "accession_number": accession,
                "primary_document": primary_document,
                "filing_url": (
                    "https://www.sec.gov/Archives/edgar/data/"
                    f"{int(normalized)}/{accession_path}/{primary_document}"
                ),
            }
        )
        if len(filings) >= max(1, min(limit, 100)):
            break
    return {
        "cik": normalized,
        "name": payload.get("name"),
        "tickers": payload.get("tickers", []),
        "exchanges": payload.get("exchanges", []),
        "sic": payload.get("sic"),
        "sic_description": payload.get("sicDescription"),
        "filings": filings,
        "source": url,
    }


@tool
def sec_company_facts(
    cik: str,
    concepts: list[str] | None = None,
    observations_per_concept: int = 12,
) -> dict:
    """Retrieve normalized SEC XBRL company facts for selected concepts.

    Concept names are usually US-GAAP tags such as Revenues, NetIncomeLoss,
    Assets, Liabilities, or CashAndCashEquivalentsAtCarryingValue.
    """
    normalized = _normalize_cik(cik)
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{normalized}.json"
    payload = cached_json(
        "GET",
        url,
        headers=_sec_headers(),
        ttl_seconds=3600,
    )
    facts = payload.get("facts", {})
    requested = set(concepts or [])
    output: dict[str, Any] = {}
    for taxonomy, taxonomy_facts in facts.items():
        for concept, detail in taxonomy_facts.items():
            if requested and concept not in requested:
                continue
            units: dict[str, Any] = {}
            for unit, rows in detail.get("units", {}).items():
                sorted_rows = sorted(
                    rows,
                    key=lambda row: (
                        row.get("filed", ""),
                        row.get("end", ""),
                    ),
                    reverse=True,
                )
                units[unit] = sorted_rows[: max(1, observations_per_concept)]
            output[f"{taxonomy}:{concept}"] = {
                "label": detail.get("label"),
                "description": detail.get("description"),
                "units": units,
            }
            if not requested and len(output) >= 40:
                break
        if not requested and len(output) >= 40:
            break
    return {
        "cik": normalized,
        "entity_name": payload.get("entityName"),
        "facts": output,
        "source": url,
        "caution": "Confirm taxonomy, units, period, form, and amended filings.",
    }


@tool
def calculate_financial_ratios(
    revenue: float,
    gross_profit: float,
    operating_income: float,
    net_income: float,
    current_assets: float,
    current_liabilities: float,
    total_debt: float,
    cash: float,
    total_equity: float,
    operating_cash_flow: float,
    capital_expenditure: float,
) -> dict:
    """Calculate core profitability, liquidity, leverage, and cash-flow ratios."""
    def ratio(numerator: float, denominator: float) -> float | None:
        return None if denominator == 0 else numerator / denominator

    free_cash_flow = operating_cash_flow - capital_expenditure
    return {
        "gross_margin": ratio(gross_profit, revenue),
        "operating_margin": ratio(operating_income, revenue),
        "net_margin": ratio(net_income, revenue),
        "current_ratio": ratio(current_assets, current_liabilities),
        "debt_to_equity": ratio(total_debt, total_equity),
        "net_debt": total_debt - cash,
        "return_on_equity": ratio(net_income, total_equity),
        "operating_cash_flow_margin": ratio(operating_cash_flow, revenue),
        "free_cash_flow": free_cash_flow,
        "free_cash_flow_margin": ratio(free_cash_flow, revenue),
    }


@tool
def discounted_cash_flow(
    free_cash_flows: list[float],
    discount_rate: float,
    terminal_growth_rate: float,
    net_debt: float = 0,
    shares_outstanding: float | None = None,
) -> dict:
    """Value forecast free cash flows with a Gordon-growth terminal value.

    Rates are decimal values, for example 0.10 for 10%.
    """
    if not free_cash_flows:
        raise ValueError("At least one forecast free cash flow is required")
    if discount_rate <= terminal_growth_rate:
        raise ValueError("discount_rate must exceed terminal_growth_rate")
    if discount_rate <= -1 or terminal_growth_rate <= -1:
        raise ValueError("rates must be greater than -100%")
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
            if shares_outstanding and shares_outstanding > 0
            else None
        ),
        "terminal_value_share_of_enterprise_value": (
            terminal_present_value / enterprise_value
            if enterprise_value
            else None
        ),
    }


@tool
def investment_return_metrics(
    periodic_returns: list[float],
    risk_free_rate: float = 0.0,
    periods_per_year: int = 12,
) -> dict:
    """Calculate annualized return, volatility, Sharpe ratio, and max drawdown.

    Returns and risk-free rate use decimal form.
    """
    if len(periodic_returns) < 2:
        raise ValueError("At least two periodic returns are required")
    growth = math.prod(1 + value for value in periodic_returns)
    annualized_return = growth ** (periods_per_year / len(periodic_returns)) - 1
    volatility = pstdev(periodic_returns) * math.sqrt(periods_per_year)
    annualized_mean = mean(periodic_returns) * periods_per_year
    sharpe = (
        (annualized_mean - risk_free_rate) / volatility
        if volatility
        else None
    )
    wealth = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for periodic_return in periodic_returns:
        wealth *= 1 + periodic_return
        peak = max(peak, wealth)
        max_drawdown = min(max_drawdown, wealth / peak - 1)
    return {
        "annualized_return": annualized_return,
        "annualized_volatility": volatility,
        "sharpe_ratio": sharpe,
        "maximum_drawdown": max_drawdown,
        "ending_growth_multiple": growth,
    }

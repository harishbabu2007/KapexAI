"""Macroeconomic, country, labor, and currency data tools."""

from datetime import date
from typing import Any

from langchain.tools import tool

from kapexai.tools.runtime import cached_json


@tool
def world_bank_indicator(
    country_code: str,
    indicator_code: str,
    start_year: int = 2015,
    end_year: int | None = None,
) -> dict:
    """Retrieve a World Bank indicator time series for a country or region.

    Examples: NY.GDP.MKTP.CD (GDP), SP.POP.TOTL (population),
    FP.CPI.TOTL.ZG (inflation).
    """
    end_year = end_year or date.today().year
    if start_year > end_year:
        raise ValueError("start_year cannot be after end_year")
    url = (
        f"https://api.worldbank.org/v2/country/{country_code}/indicator/"
        f"{indicator_code}"
    )
    payload = cached_json(
        "GET",
        url,
        params={
            "format": "json",
            "date": f"{start_year}:{end_year}",
            "per_page": 1000,
        },
        ttl_seconds=21600,
    )
    if not isinstance(payload, list) or len(payload) < 2:
        return {
            "country_code": country_code,
            "indicator_code": indicator_code,
            "observations": [],
            "source": url,
        }
    metadata, rows = payload[0], payload[1] or []
    observations = [
        {
            "year": int(row["date"]),
            "value": row.get("value"),
            "country": row.get("country", {}).get("value"),
            "unit": row.get("unit"),
            "observation_status": row.get("obs_status"),
        }
        for row in rows
        if row.get("date")
    ]
    observations.sort(key=lambda item: item["year"])
    return {
        "country_code": country_code.upper(),
        "indicator_code": indicator_code,
        "indicator": (
            rows[0].get("indicator", {}).get("value") if rows else None
        ),
        "page_metadata": metadata,
        "observations": observations,
        "source": url,
    }


@tool
def world_bank_country_profile(country_code: str) -> dict:
    """Retrieve World Bank country metadata such as region and income level."""
    url = f"https://api.worldbank.org/v2/country/{country_code}"
    payload = cached_json(
        "GET",
        url,
        params={"format": "json"},
        ttl_seconds=86400,
    )
    rows = payload[1] if isinstance(payload, list) and len(payload) > 1 else []
    if not rows:
        return {"country_code": country_code, "country": None, "source": url}
    row = rows[0]
    return {
        "country_code": row.get("iso2Code"),
        "country": row.get("name"),
        "region": row.get("region", {}).get("value"),
        "income_level": row.get("incomeLevel", {}).get("value"),
        "lending_type": row.get("lendingType", {}).get("value"),
        "capital": row.get("capitalCity"),
        "longitude": row.get("longitude"),
        "latitude": row.get("latitude"),
        "source": url,
    }


@tool
def bls_time_series(
    series_ids: list[str],
    start_year: int | None = None,
    end_year: int | None = None,
) -> dict:
    """Retrieve U.S. labor, inflation, wage, or productivity series from BLS."""
    if not series_ids or len(series_ids) > 20:
        raise ValueError("Provide between 1 and 20 BLS series IDs")
    body: dict[str, Any] = {"seriesid": series_ids}
    if start_year is not None:
        body["startyear"] = str(start_year)
    if end_year is not None:
        body["endyear"] = str(end_year)
    payload = cached_json(
        "POST",
        "https://api.bls.gov/publicAPI/v2/timeseries/data/",
        json_body=body,
        ttl_seconds=21600,
    )
    if payload.get("status") != "REQUEST_SUCCEEDED":
        return {
            "status": payload.get("status"),
            "messages": payload.get("message", []),
            "series": [],
            "source": "https://api.bls.gov/publicAPI/v2/timeseries/data/",
        }
    series = []
    for item in payload.get("Results", {}).get("series", []):
        observations = []
        for row in item.get("data", []):
            raw_value = row.get("value")
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                value = None
            observations.append(
                {
                    "year": int(row["year"]),
                    "period": row.get("period"),
                    "period_name": row.get("periodName"),
                    "value": value,
                    "raw_value": raw_value,
                    "footnotes": [
                        note.get("text")
                        for note in row.get("footnotes", [])
                        if note and note.get("text")
                    ],
                }
            )
        series.append(
            {
                "series_id": item.get("seriesID"),
                "observations": observations,
            }
        )
    return {
        "status": payload.get("status"),
        "series": series,
        "source": "https://api.bls.gov/publicAPI/v2/timeseries/data/",
    }


@tool
def exchange_rate_series(
    base_currency: str,
    quote_currencies: list[str],
    start_date: str | None = None,
    end_date: str | None = None,
    group: str | None = None,
) -> dict:
    """Retrieve current or historical central-bank exchange rates.

    Dates use YYYY-MM-DD. Group may be 'week' or 'month'.
    """
    if not quote_currencies:
        raise ValueError("At least one quote currency is required")
    params: dict[str, Any] = {
        "base": base_currency.upper(),
        "quotes": ",".join(code.upper() for code in quote_currencies),
    }
    if start_date:
        params["from"] = start_date
    if end_date:
        params["to"] = end_date
    if group:
        if group not in {"week", "month"}:
            raise ValueError("group must be 'week' or 'month'")
        params["group"] = group
    payload = cached_json(
        "GET",
        "https://api.frankfurter.dev/v2/rates",
        params=params,
        ttl_seconds=21600,
    )
    return {
        "base_currency": base_currency.upper(),
        "quote_currencies": [code.upper() for code in quote_currencies],
        "rates": payload,
        "source": "https://api.frankfurter.dev/v2/rates",
    }

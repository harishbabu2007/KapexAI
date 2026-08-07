"""Free Astrology API tools for optional symbolic chart interpretation."""

import threading
import time
from datetime import datetime
from typing import Any, Literal

from langchain.tools import tool

from kapexai.tools.runtime import cached_json, require_env


API_BASE = "https://json.freeastrologyapi.com"
_API_LOCK = threading.Lock()
_LAST_REQUEST_AT = 0.0

VEDIC_SIGNS = {
    1: "Aries / Mesha",
    2: "Taurus / Vrishabha",
    3: "Gemini / Mithuna",
    4: "Cancer / Karka",
    5: "Leo / Simha",
    6: "Virgo / Kanya",
    7: "Libra / Tula",
    8: "Scorpio / Vrischika",
    9: "Sagittarius / Dhanu",
    10: "Capricorn / Makara",
    11: "Aquarius / Kumbha",
    12: "Pisces / Meena",
}

HouseSystem = Literal[
    "P",
    "K",
    "O",
    "R",
    "C",
    "E",
    "W",
    "X",
    "H",
    "T",
    "B",
    "M",
]


def _validate_datetime_location(
    year: int,
    month: int,
    day: int,
    hours: int,
    minutes: int,
    seconds: int,
    latitude: float,
    longitude: float,
    timezone: float,
) -> None:
    datetime(year, month, day, hours, minutes, seconds)
    if not -90 <= latitude <= 90:
        raise ValueError("latitude must be between -90 and 90")
    if not -180 <= longitude <= 180:
        raise ValueError("longitude must be between -180 and 180")
    if not -14 <= timezone <= 14:
        raise ValueError("timezone must be a UTC offset between -14 and 14")


def _birth_payload(
    year: int,
    month: int,
    day: int,
    hours: int,
    minutes: int,
    seconds: int,
    latitude: float,
    longitude: float,
    timezone: float,
    *,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _validate_datetime_location(
        year,
        month,
        day,
        hours,
        minutes,
        seconds,
        latitude,
        longitude,
        timezone,
    )
    payload: dict[str, Any] = {
        "year": year,
        "month": month,
        "date": day,
        "hours": hours,
        "minutes": minutes,
        "seconds": seconds,
        "latitude": latitude,
        "longitude": longitude,
        "timezone": timezone,
    }
    if settings:
        payload["settings"] = settings
    return payload


def _api_call(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    api_key = require_env("FREE_ASTROLOGY_API_KEY")
    global _LAST_REQUEST_AT
    with _API_LOCK:
        wait = 1.02 - (time.monotonic() - _LAST_REQUEST_AT)
        if wait > 0:
            time.sleep(wait)
        response = cached_json(
            "POST",
            f"{API_BASE}/{endpoint}",
            json_body=payload,
            headers={"x-api-key": api_key},
            ttl_seconds=21600,
        )
        _LAST_REQUEST_AT = time.monotonic()
    return {
        "provider": "Free Astrology API",
        "endpoint": endpoint,
        "source": f"{API_BASE}/{endpoint}",
        "data": response,
        "disclaimer": (
            "Astrology is non-scientific and interpretive. This result is for "
            "reflection or entertainment and must not determine financial, "
            "legal, hiring, health, or safety decisions."
        ),
        "privacy_note": (
            "Only submit another person's birth data with their informed consent."
        ),
        "usage_note": (
            "The provider's free plan is rate-limited. Request only the chart "
            "components needed for the current question."
        ),
    }


def _vedic_settings(
    observation_point: Literal["topocentric", "geocentric"],
    ayanamsha: int,
    lunar_node: Literal["true", "mean"],
    language: str,
) -> dict[str, Any]:
    if ayanamsha not in {1, 3, 5, 7}:
        raise ValueError("ayanamsha must be 1 (Lahiri), 3 (KP), 5 (Raman), or 7 (Jaimini)")
    return {
        "observation_point": observation_point,
        "ayanamsha": ayanamsha,
        "language": language,
        "lunar_node": lunar_node,
    }


def _western_settings(
    house_system: HouseSystem,
    zodiac_type: Literal["Tropical", "Siderial"],
    sidereal_mode: Literal["FAGAN_BRADLEY", "LAHIRI"],
    language: str,
) -> dict[str, Any]:
    return {
        "house_system": house_system,
        "zodiac_type": zodiac_type,
        "sidereal_mode": sidereal_mode,
        "language": language,
    }


def _rashi_summary(response: dict[str, Any]) -> list[dict[str, Any]]:
    raw = response.get("output", response)
    if not isinstance(raw, dict):
        return []
    summary = []
    for object_name, detail in raw.items():
        if not isinstance(detail, dict):
            continue
        sign_number = detail.get("current_sign")
        summary.append(
            {
                "object": object_name,
                "sign_number": sign_number,
                "rashi": VEDIC_SIGNS.get(sign_number),
                "longitude": detail.get("fullDegree"),
                "nakshatra": detail.get("nakshatra_name"),
                "nakshatra_lord": detail.get("nakshatra_lord"),
                "house": detail.get("house_number"),
                "is_retrograde": detail.get("isRetro"),
            }
        )
    return summary


@tool
def free_astrology_resolve_location(place_name: str) -> dict:
    """Resolve a place name to coordinates using Free Astrology API."""
    result = _api_call("geo-details", {"location": place_name})
    result["purpose"] = "Use returned coordinates as inputs to chart tools."
    return result


@tool
def free_astrology_timezone_with_dst(
    latitude: float,
    longitude: float,
    year: int,
    month: int,
    day: int,
    hours: int = 12,
    minutes: int = 0,
    seconds: int = 0,
) -> dict:
    """Resolve UTC offset and daylight-saving status for a place and date."""
    payload = _birth_payload(
        year,
        month,
        day,
        hours,
        minutes,
        seconds,
        latitude,
        longitude,
        0.0,
    )
    return _api_call("timezone-with-dst", payload)


@tool
def free_astrology_vedic_rasi_chart(
    year: int,
    month: int,
    day: int,
    hours: int,
    minutes: int,
    seconds: int,
    latitude: float,
    longitude: float,
    timezone: float,
    observation_point: Literal["topocentric", "geocentric"] = "topocentric",
    ayanamsha: int = 1,
    lunar_node: Literal["true", "mean"] = "true",
    language: str = "en",
) -> dict:
    """Calculate the Vedic D1/Raashi planetary chart.

    D1 is the primary symbolic chart for identity, life themes, and Raashi.
    """
    result = _api_call(
        "planets",
        _birth_payload(
            year,
            month,
            day,
            hours,
            minutes,
            seconds,
            latitude,
            longitude,
            timezone,
            settings=_vedic_settings(
                observation_point, ayanamsha, lunar_node, language
            ),
        ),
    )
    data = result["data"]
    result["rashi_summary"] = _rashi_summary(data) if isinstance(data, dict) else []
    result["symbolic_use"] = "Raashi, Ascendant, planetary signs, houses, and nakshatras."
    return result


@tool
def free_astrology_vedic_extended_chart(
    year: int,
    month: int,
    day: int,
    hours: int,
    minutes: int,
    seconds: int,
    latitude: float,
    longitude: float,
    timezone: float,
    observation_point: Literal["topocentric", "geocentric"] = "topocentric",
    ayanamsha: int = 1,
    lunar_node: Literal["true", "mean"] = "true",
    language: str = "en",
) -> dict:
    """Retrieve extended Vedic chart details including dignities and relationships."""
    return _api_call(
        "extended-horoscope-details",
        _birth_payload(
            year,
            month,
            day,
            hours,
            minutes,
            seconds,
            latitude,
            longitude,
            timezone,
            settings=_vedic_settings(
                observation_point, ayanamsha, lunar_node, language
            ),
        ),
    )


def _vedic_divisional_chart(
    endpoint: str,
    symbolic_use: str,
    year: int,
    month: int,
    day: int,
    hours: int,
    minutes: int,
    seconds: int,
    latitude: float,
    longitude: float,
    timezone: float,
    observation_point: Literal["topocentric", "geocentric"],
    ayanamsha: int,
    lunar_node: Literal["true", "mean"],
    language: str,
) -> dict:
    result = _api_call(
        endpoint,
        _birth_payload(
            year,
            month,
            day,
            hours,
            minutes,
            seconds,
            latitude,
            longitude,
            timezone,
            settings=_vedic_settings(
                observation_point, ayanamsha, lunar_node, language
            ),
        ),
    )
    result["symbolic_use"] = symbolic_use
    return result


@tool
def free_astrology_vedic_hora_chart(
    year: int,
    month: int,
    day: int,
    hours: int,
    minutes: int,
    seconds: int,
    latitude: float,
    longitude: float,
    timezone: float,
    observation_point: Literal["topocentric", "geocentric"] = "topocentric",
    ayanamsha: int = 1,
    lunar_node: Literal["true", "mean"] = "true",
    language: str = "en",
) -> dict:
    """Calculate the Vedic D2/Hora chart for symbolic wealth reflection."""
    return _vedic_divisional_chart(
        "d2-chart-info",
        "Symbolic reflection on resources, money habits, and wealth themes.",
        year, month, day, hours, minutes, seconds, latitude, longitude, timezone,
        observation_point, ayanamsha, lunar_node, language,
    )


@tool
def free_astrology_vedic_navamsa_chart(
    year: int,
    month: int,
    day: int,
    hours: int,
    minutes: int,
    seconds: int,
    latitude: float,
    longitude: float,
    timezone: float,
    observation_point: Literal["topocentric", "geocentric"] = "topocentric",
    ayanamsha: int = 1,
    lunar_node: Literal["true", "mean"] = "true",
    language: str = "en",
) -> dict:
    """Calculate the Vedic D9/Navamsa chart for values and partnership reflection."""
    return _vedic_divisional_chart(
        "d9-chart-info",
        "Symbolic reflection on values, maturity, commitment, and partnerships.",
        year, month, day, hours, minutes, seconds, latitude, longitude, timezone,
        observation_point, ayanamsha, lunar_node, language,
    )


@tool
def free_astrology_vedic_dasamsa_chart(
    year: int,
    month: int,
    day: int,
    hours: int,
    minutes: int,
    seconds: int,
    latitude: float,
    longitude: float,
    timezone: float,
    observation_point: Literal["topocentric", "geocentric"] = "topocentric",
    ayanamsha: int = 1,
    lunar_node: Literal["true", "mean"] = "true",
    language: str = "en",
) -> dict:
    """Calculate the Vedic D10/Dasamsa chart for career and business reflection."""
    return _vedic_divisional_chart(
        "d10-chart-info",
        "Symbolic reflection on vocation, leadership, reputation, and business work.",
        year, month, day, hours, minutes, seconds, latitude, longitude, timezone,
        observation_point, ayanamsha, lunar_node, language,
    )


@tool
def free_astrology_vimsottari_dasas(
    year: int,
    month: int,
    day: int,
    hours: int,
    minutes: int,
    seconds: int,
    latitude: float,
    longitude: float,
    timezone: float,
    observation_point: Literal["topocentric", "geocentric"] = "topocentric",
    ayanamsha: int = 1,
    lunar_node: Literal["true", "mean"] = "true",
    language: str = "en",
) -> dict:
    """Calculate complete Vimshottari Maha and Antar Dasha periods.

    Periods may support symbolic timing narratives, never guaranteed forecasts.
    """
    result = _api_call(
        "complete-maha-antar-dasa",
        _birth_payload(
            year,
            month,
            day,
            hours,
            minutes,
            seconds,
            latitude,
            longitude,
            timezone,
            settings=_vedic_settings(
                observation_point, ayanamsha, lunar_node, language
            ),
        ),
    )
    result["symbolic_use"] = "Timing windows and age periods for reflective scenario planning."
    return result


@tool
def free_astrology_shadbala_summary(
    year: int,
    month: int,
    day: int,
    hours: int,
    minutes: int,
    seconds: int,
    latitude: float,
    longitude: float,
    timezone: float,
    observation_point: Literal["topocentric", "geocentric"] = "topocentric",
    ayanamsha: int = 1,
    lunar_node: Literal["true", "mean"] = "true",
    language: str = "en",
) -> dict:
    """Retrieve Vedic Shadbala planetary strength summary."""
    return _api_call(
        "shadbala-summary",
        _birth_payload(
            year,
            month,
            day,
            hours,
            minutes,
            seconds,
            latitude,
            longitude,
            timezone,
            settings=_vedic_settings(
                observation_point, ayanamsha, lunar_node, language
            ),
        ),
    )


def _western_chart(
    endpoint: str,
    year: int,
    month: int,
    day: int,
    hours: int,
    minutes: int,
    seconds: int,
    latitude: float,
    longitude: float,
    timezone: float,
    house_system: HouseSystem,
    zodiac_type: Literal["Tropical", "Siderial"],
    sidereal_mode: Literal["FAGAN_BRADLEY", "LAHIRI"],
    language: str,
) -> dict:
    return _api_call(
        endpoint,
        _birth_payload(
            year,
            month,
            day,
            hours,
            minutes,
            seconds,
            latitude,
            longitude,
            timezone,
            settings=_western_settings(
                house_system, zodiac_type, sidereal_mode, language
            ),
        ),
    )


@tool
def free_astrology_western_planets(
    year: int,
    month: int,
    day: int,
    hours: int,
    minutes: int,
    seconds: int,
    latitude: float,
    longitude: float,
    timezone: float,
    house_system: HouseSystem = "P",
    zodiac_type: Literal["Tropical", "Siderial"] = "Tropical",
    sidereal_mode: Literal["FAGAN_BRADLEY", "LAHIRI"] = "FAGAN_BRADLEY",
    language: str = "en",
) -> dict:
    """Calculate Western natal planetary placements."""
    return _western_chart(
        "western/planets",
        year, month, day, hours, minutes, seconds, latitude, longitude, timezone,
        house_system, zodiac_type, sidereal_mode, language,
    )


@tool
def free_astrology_western_houses(
    year: int,
    month: int,
    day: int,
    hours: int,
    minutes: int,
    seconds: int,
    latitude: float,
    longitude: float,
    timezone: float,
    house_system: HouseSystem = "P",
    zodiac_type: Literal["Tropical", "Siderial"] = "Tropical",
    sidereal_mode: Literal["FAGAN_BRADLEY", "LAHIRI"] = "FAGAN_BRADLEY",
    language: str = "en",
) -> dict:
    """Calculate Western natal houses and angles."""
    return _western_chart(
        "western/houses",
        year, month, day, hours, minutes, seconds, latitude, longitude, timezone,
        house_system, zodiac_type, sidereal_mode, language,
    )


@tool
def free_astrology_western_aspects(
    year: int,
    month: int,
    day: int,
    hours: int,
    minutes: int,
    seconds: int,
    latitude: float,
    longitude: float,
    timezone: float,
    house_system: HouseSystem = "P",
    zodiac_type: Literal["Tropical", "Siderial"] = "Tropical",
    sidereal_mode: Literal["FAGAN_BRADLEY", "LAHIRI"] = "FAGAN_BRADLEY",
    language: str = "en",
) -> dict:
    """Calculate Western natal planetary aspects."""
    return _western_chart(
        "western/aspects",
        year, month, day, hours, minutes, seconds, latitude, longitude, timezone,
        house_system, zodiac_type, sidereal_mode, language,
    )


@tool
def free_astrology_panchang_good_bad_times(
    year: int,
    month: int,
    day: int,
    latitude: float,
    longitude: float,
    timezone: float,
    hours: int = 6,
    minutes: int = 0,
    seconds: int = 0,
    language: str = "en",
) -> dict:
    """Retrieve Panchang good/bad time windows for a candidate date and place.

    Use only as a symbolic scheduling overlay after operational constraints.
    """
    result = _api_call(
        "good-bad-times",
        _birth_payload(
            year,
            month,
            day,
            hours,
            minutes,
            seconds,
            latitude,
            longitude,
            timezone,
            settings={"language": language},
        ),
    )
    result["symbolic_use"] = "Compare user-supplied candidate launch dates or locations."
    return result


@tool
def free_astrology_ashtakoot_compatibility(
    person_a: dict[str, Any],
    person_b: dict[str, Any],
    language: str = "en",
) -> dict:
    """Retrieve traditional Vedic Ashtakoot compatibility.

    This API model is traditionally designed for marriage matching. It must not
    be used to hire, reject, rank, or select business partners. For any other
    person, obtain informed consent before submitting birth data.
    """
    required = {
        "year",
        "month",
        "date",
        "hours",
        "minutes",
        "seconds",
        "latitude",
        "longitude",
        "timezone",
    }
    for label, person in (("person_a", person_a), ("person_b", person_b)):
        missing = sorted(required - person.keys())
        if missing:
            raise ValueError(f"{label} is missing: {', '.join(missing)}")
        _validate_datetime_location(
            int(person["year"]),
            int(person["month"]),
            int(person["date"]),
            int(person["hours"]),
            int(person["minutes"]),
            int(person["seconds"]),
            float(person["latitude"]),
            float(person["longitude"]),
            float(person["timezone"]),
        )
    result = _api_call(
        "match-making/ashtakoot-score",
        {
            "female": person_a,
            "male": person_b,
            "language": language,
        },
    )
    result["prohibited_use"] = (
        "Do not use this score for business partner selection, employment, "
        "credit, investment, or other consequential decisions."
    )
    return result


FREE_ASTROLOGY_API_TOOLS = (
    free_astrology_resolve_location,
    free_astrology_timezone_with_dst,
    free_astrology_vedic_rasi_chart,
    free_astrology_vedic_extended_chart,
    free_astrology_vedic_hora_chart,
    free_astrology_vedic_navamsa_chart,
    free_astrology_vedic_dasamsa_chart,
    free_astrology_vimsottari_dasas,
    free_astrology_shadbala_summary,
    free_astrology_western_planets,
    free_astrology_western_houses,
    free_astrology_western_aspects,
    free_astrology_panchang_good_bad_times,
    free_astrology_ashtakoot_compatibility,
)

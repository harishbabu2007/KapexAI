"""Evidence-based foresight and astronomical reference tools."""

from langchain.tools import tool

from kapexai.tools.runtime import cached_json


@tool
def jpl_horizons_ephemeris(
    target: str,
    start_time: str,
    stop_time: str,
    step_size: str = "1 d",
    center: str = "500@399",
) -> dict:
    """Retrieve astronomical ephemeris data from NASA JPL Horizons.

    This supplies astronomical positions, not evidence that astrology predicts
    personal or business outcomes. Dates should use YYYY-MM-DD.
    """
    payload = cached_json(
        "GET",
        "https://ssd.jpl.nasa.gov/api/horizons.api",
        params={
            "format": "json",
            "COMMAND": f"'{target}'",
            "OBJ_DATA": "'YES'",
            "MAKE_EPHEM": "'YES'",
            "EPHEM_TYPE": "'OBSERVER'",
            "CENTER": f"'{center}'",
            "START_TIME": f"'{start_time}'",
            "STOP_TIME": f"'{stop_time}'",
            "STEP_SIZE": f"'{step_size}'",
            "QUANTITIES": "'1,9,20,23,24,29'",
            "CSV_FORMAT": "'YES'",
        },
        ttl_seconds=86400,
    )
    result = payload.get("result", "")
    return {
        "target": target,
        "start_time": start_time,
        "stop_time": stop_time,
        "ephemeris": result[-20000:],
        "source": "https://ssd.jpl.nasa.gov/api/horizons.api",
        "disclaimer": (
            "Astronomical data is scientific; astrological interpretation is "
            "non-scientific and must not drive high-stakes decisions."
        ),
    }


@tool
def future_signpost_matrix(
    scenarios: list[dict],
) -> dict:
    """Structure plausible future scenarios with signals and trigger actions.

    Each scenario may include name, description, probability, signals, impacts,
    and trigger_actions.
    """
    normalized = []
    probability_total = 0.0
    for scenario in scenarios:
        probability = float(scenario.get("probability", 0))
        if probability < 0 or probability > 1:
            raise ValueError("Scenario probabilities must be between 0 and 1")
        probability_total += probability
        normalized.append(
            {
                "name": scenario.get("name"),
                "description": scenario.get("description"),
                "probability": probability,
                "signals": list(scenario.get("signals", [])),
                "impacts": list(scenario.get("impacts", [])),
                "trigger_actions": list(scenario.get("trigger_actions", [])),
            }
        )
    return {
        "scenarios": normalized,
        "probability_total": probability_total,
        "probabilities_sum_to_one": abs(probability_total - 1.0) < 0.001,
        "guidance": (
            "Use probabilities as planning judgments, not claims of certainty."
        ),
    }

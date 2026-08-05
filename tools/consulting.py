"""Deterministic consulting, planning, and decision-support tools."""

from typing import Any

from langchain.tools import tool


@tool
def market_size_model(
    total_customers: float,
    annual_revenue_per_customer: float,
    serviceable_share: float,
    obtainable_share: float,
) -> dict:
    """Calculate TAM, SAM, and SOM from transparent bottom-up assumptions.

    Share inputs use decimal form, for example 0.25 for 25%.
    """
    if total_customers < 0 or annual_revenue_per_customer < 0:
        raise ValueError("customer and revenue assumptions cannot be negative")
    if not 0 <= serviceable_share <= 1 or not 0 <= obtainable_share <= 1:
        raise ValueError("share assumptions must be between 0 and 1")
    tam = total_customers * annual_revenue_per_customer
    sam = tam * serviceable_share
    som = sam * obtainable_share
    return {
        "tam": tam,
        "sam": sam,
        "som": som,
        "assumptions": {
            "total_customers": total_customers,
            "annual_revenue_per_customer": annual_revenue_per_customer,
            "serviceable_share": serviceable_share,
            "obtainable_share": obtainable_share,
        },
    }


@tool
def weighted_decision_matrix(
    criteria: list[dict[str, Any]],
    options: list[dict[str, Any]],
) -> dict:
    """Rank strategic options using weighted criteria and explicit scores.

    Criteria require name and weight. Options require name and a scores mapping
    from criterion name to a 0-10 score.
    """
    if not criteria or not options:
        raise ValueError("criteria and options cannot be empty")
    total_weight = sum(float(item.get("weight", 0)) for item in criteria)
    if total_weight <= 0:
        raise ValueError("criterion weights must total more than zero")
    criterion_names = [str(item["name"]) for item in criteria]
    results = []
    for option in options:
        scores = option.get("scores", {})
        weighted_score = 0.0
        contributions = {}
        for criterion in criteria:
            name = str(criterion["name"])
            score = float(scores.get(name, 0))
            if score < 0 or score > 10:
                raise ValueError(f"Score for '{name}' must be between 0 and 10")
            contribution = score * float(criterion["weight"]) / total_weight
            contributions[name] = contribution
            weighted_score += contribution
        results.append(
            {
                "option": option["name"],
                "weighted_score": weighted_score,
                "contributions": contributions,
                "missing_scores": [
                    name for name in criterion_names if name not in scores
                ],
            }
        )
    results.sort(key=lambda item: item["weighted_score"], reverse=True)
    return {
        "ranking": results,
        "normalized_weight_total": 1.0,
        "caution": "The ranking reflects supplied assumptions, not objective truth.",
    }


@tool
def scenario_projection(
    base_value: float,
    periods: int,
    scenarios: list[dict[str, Any]],
) -> dict:
    """Project a base value under multiple compound-growth scenarios.

    Each scenario requires name and annual_growth_rate in decimal form.
    """
    if periods < 1 or periods > 50:
        raise ValueError("periods must be between 1 and 50")
    projections = []
    for scenario in scenarios:
        rate = float(scenario["annual_growth_rate"])
        values = [
            base_value * ((1 + rate) ** period)
            for period in range(periods + 1)
        ]
        projections.append(
            {
                "name": scenario["name"],
                "annual_growth_rate": rate,
                "values": values,
                "ending_value": values[-1],
            }
        )
    return {
        "base_value": base_value,
        "periods": periods,
        "scenarios": projections,
    }


@tool
def risk_register(
    risks: list[dict[str, Any]],
) -> dict:
    """Score business risks by likelihood, impact, and control effectiveness.

    Likelihood and impact use 1-5. Control effectiveness uses 0-1.
    """
    output = []
    for risk in risks:
        likelihood = int(risk.get("likelihood", 1))
        impact = int(risk.get("impact", 1))
        control = float(risk.get("control_effectiveness", 0))
        if not 1 <= likelihood <= 5 or not 1 <= impact <= 5:
            raise ValueError("likelihood and impact must be 1-5")
        if not 0 <= control <= 1:
            raise ValueError("control_effectiveness must be between 0 and 1")
        inherent = likelihood * impact
        residual = inherent * (1 - control)
        output.append(
            {
                **risk,
                "inherent_score": inherent,
                "residual_score": residual,
                "priority": (
                    "critical"
                    if residual >= 16
                    else "high"
                    if residual >= 10
                    else "medium"
                    if residual >= 5
                    else "low"
                ),
            }
        )
    output.sort(key=lambda item: item["residual_score"], reverse=True)
    return {"risks": output}


@tool
def raci_validator(rows: list[dict[str, Any]]) -> dict:
    """Validate a RACI responsibility matrix for missing or duplicate ownership.

    Each row requires activity and assignments mapping people/roles to R, A, C,
    or I.
    """
    findings = []
    for row in rows:
        assignments = {
            person: str(role).upper()
            for person, role in row.get("assignments", {}).items()
        }
        accountable = [
            person for person, role in assignments.items() if role == "A"
        ]
        responsible = [
            person for person, role in assignments.items() if role == "R"
        ]
        issues = []
        if len(accountable) == 0:
            issues.append("No accountable owner")
        elif len(accountable) > 1:
            issues.append("Multiple accountable owners")
        if len(responsible) == 0:
            issues.append("No responsible executor")
        invalid = [
            f"{person}:{role}"
            for person, role in assignments.items()
            if role not in {"R", "A", "C", "I"}
        ]
        if invalid:
            issues.append(f"Invalid assignments: {', '.join(invalid)}")
        findings.append(
            {
                "activity": row.get("activity"),
                "accountable": accountable,
                "responsible": responsible,
                "issues": issues,
            }
        )
    return {
        "rows": findings,
        "valid": all(not finding["issues"] for finding in findings),
    }


@tool
def kpi_tree_builder(
    objective: str,
    outcome_kpis: list[str],
    driver_kpis: list[str],
    guardrail_kpis: list[str],
) -> dict:
    """Structure supplied measures into an executive KPI tree."""
    return {
        "objective": objective,
        "outcomes": [
            {"name": name, "type": "lagging", "owner_required": True}
            for name in outcome_kpis
        ],
        "drivers": [
            {"name": name, "type": "leading", "threshold_required": True}
            for name in driver_kpis
        ],
        "guardrails": [
            {"name": name, "type": "constraint", "breach_action_required": True}
            for name in guardrail_kpis
        ],
        "review_questions": [
            "Does each outcome have at least one controllable driver?",
            "Does each KPI have an owner, formula, cadence, and data source?",
            "Are intervention thresholds and actions explicit?",
        ],
    }

"""Deterministic analysis tools used by the baseline workers."""

from typing import Dict, List


def generate_swot(topic: str) -> Dict[str, List[str]]:
    return {
        "topic": topic,
        "strengths": [f"Strong brand in {topic}", "Diversified revenue streams"],
        "weaknesses": ["High operating costs", "Dependence on key clients"],
        "opportunities": ["Expanding to new markets", "Product line extension"],
        "threats": ["Regulatory changes", "New competitors"],
    }


def generate_porter_five_forces(topic: str) -> Dict[str, str]:
    return {
        "topic": topic,
        "threat_of_new_entrants": "Medium - moderate barriers to entry",
        "bargaining_power_of_suppliers": "Low - many suppliers",
        "bargaining_power_of_buyers": "High - informed buyers",
        "threat_of_substitutes": "Medium - some viable alternatives",
        "industry_rivalry": "High - competing incumbents",
    }


def generate_financial_summary(topic: str) -> Dict[str, str]:
    return {
        "topic": topic,
        "revenue_trend": "Growing 8% YoY",
        "margin": "Gross margin about 38%",
        "cash_position": "Healthy cash reserves",
        "key_risks": "Currency exposure and interest rates",
    }


def run_all(topic: str) -> Dict[str, object]:
    return {
        "swot": generate_swot(topic),
        "porter": generate_porter_five_forces(topic),
        "financial": generate_financial_summary(topic),
    }

"""Public legal and regulatory research tools."""

import os
from typing import Any

from langchain.tools import tool

from kapexai.tools.runtime import cached_json, require_env


@tool
def federal_register_search(
    query: str,
    document_type: str | None = None,
    agency_slug: str | None = None,
    published_after: str | None = None,
    max_results: int = 20,
) -> dict:
    """Search U.S. Federal Register rules, proposed rules, and notices.

    FederalRegister.gov is informational; verify legal reliance against the
    official edition linked by each result.
    """
    params: dict[str, Any] = {
        "conditions[term]": query,
        "per_page": max(1, min(max_results, 100)),
        "order": "newest",
    }
    if document_type:
        valid_types = {
            "RULE",
            "PRORULE",
            "NOTICE",
            "PRESDOCU",
        }
        normalized = document_type.upper()
        if normalized not in valid_types:
            raise ValueError(
                "document_type must be RULE, PRORULE, NOTICE, or PRESDOCU"
            )
        params["conditions[type][]"] = normalized
    if agency_slug:
        params["conditions[agencies][]"] = agency_slug
    if published_after:
        params["conditions[publication_date][gte]"] = published_after
    url = "https://www.federalregister.gov/api/v1/documents.json"
    payload = cached_json("GET", url, params=params, ttl_seconds=3600)
    results = [
        {
            "title": item.get("title"),
            "type": item.get("type"),
            "document_number": item.get("document_number"),
            "publication_date": item.get("publication_date"),
            "agencies": [
                agency.get("name") for agency in item.get("agencies", [])
            ],
            "abstract": item.get("abstract"),
            "html_url": item.get("html_url"),
            "pdf_url": item.get("pdf_url"),
            "citation": item.get("citation"),
        }
        for item in payload.get("results", [])
    ]
    return {
        "query": query,
        "count": len(results),
        "results": results,
        "source": url,
        "legal_status": (
            "FederalRegister.gov is informational; verify against the official "
            "Federal Register edition on govinfo.gov."
        ),
    }


@tool
def courtlistener_case_search(
    query: str,
    court: str | None = None,
    max_results: int = 10,
) -> dict:
    """Search U.S. case-law records through CourtListener.

    Requires a free COURTLISTENER_API_TOKEN. Results are legal research leads,
    not a substitute for qualified counsel or citator validation.
    """
    token = require_env("COURTLISTENER_API_TOKEN")
    params: dict[str, Any] = {
        "q": query,
        "type": "o",
        "order_by": "score desc",
    }
    if court:
        params["court"] = court
    payload = cached_json(
        "GET",
        "https://www.courtlistener.com/api/rest/v4/search/",
        params=params,
        headers={"Authorization": f"Token {token}"},
        ttl_seconds=3600,
    )
    results = []
    for item in payload.get("results", [])[: max(1, min(max_results, 20))]:
        results.append(
            {
                "case_name": item.get("caseName"),
                "citation": item.get("citation"),
                "court": item.get("court"),
                "date_filed": item.get("dateFiled"),
                "status": item.get("status"),
                "absolute_url": (
                    f"https://www.courtlistener.com{item.get('absolute_url')}"
                    if item.get("absolute_url")
                    else None
                ),
                "snippet": item.get("snippet"),
            }
        )
    return {
        "query": query,
        "count": len(results),
        "results": results,
        "source": "https://www.courtlistener.com/api/rest/v4/search/",
        "caution": "Validate authority, treatment, jurisdiction, and current law.",
    }


@tool
def legal_issue_register(
    issues: list[dict[str, Any]],
) -> dict:
    """Score and prioritize supplied legal issues without making legal findings.

    Each issue may contain name, likelihood (1-5), severity (1-5), urgency
    (1-5), jurisdiction, owner, and mitigation.
    """
    normalized = []
    for issue in issues:
        likelihood = int(issue.get("likelihood", 1))
        severity = int(issue.get("severity", 1))
        urgency = int(issue.get("urgency", 1))
        if any(value < 1 or value > 5 for value in (likelihood, severity, urgency)):
            raise ValueError("likelihood, severity, and urgency must be 1-5")
        score = likelihood * severity * urgency
        normalized.append(
            {
                **issue,
                "likelihood": likelihood,
                "severity": severity,
                "urgency": urgency,
                "priority_score": score,
                "priority": (
                    "critical"
                    if score >= 60
                    else "high"
                    if score >= 30
                    else "medium"
                    if score >= 12
                    else "low"
                ),
            }
        )
    normalized.sort(key=lambda item: item["priority_score"], reverse=True)
    return {
        "issues": normalized,
        "disclaimer": (
            "This is an issue-prioritization aid, not a legal opinion."
        ),
    }

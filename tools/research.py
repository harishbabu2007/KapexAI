"""Research, market-intelligence, and evidence-discovery tools."""

import os
from typing import Any

from langchain.tools import tool

from kapexai.tools.runtime import ToolServiceError, cached_json, require_env


@tool
def gdelt_news_search(
    query: str,
    max_records: int = 20,
    timespan: str = "3months",
) -> dict:
    """Search recent global news coverage using GDELT DOC 2.0.

    Use for current market signals, competitor news, regulation coverage, and
    emerging issues. Treat machine-generated metadata as leads to verify.
    """
    max_records = max(1, min(max_records, 50))
    url = "https://api.gdeltproject.org/api/v2/doc/doc"
    try:
        payload = cached_json(
            "GET",
            url,
            params={
                "query": query,
                "mode": "ArtList",
                "format": "json",
                "maxrecords": max_records,
                "timespan": timespan,
                "sort": "HybridRel",
            },
            ttl_seconds=900,
        )
    except ToolServiceError as exc:
        return {
            "query": query,
            "count": 0,
            "articles": [],
            "source": url,
            "status": "temporarily_unavailable",
            "error": str(exc),
            "caution": "Retry later or use another research source.",
        }
    articles = []
    for item in payload.get("articles", [])[:max_records]:
        articles.append(
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "domain": item.get("domain"),
                "source_country": item.get("sourcecountry"),
                "language": item.get("language"),
                "published_at": item.get("seendate"),
            }
        )
    return {
        "query": query,
        "count": len(articles),
        "articles": articles,
        "source": url,
        "status": "ok",
        "caution": "News results are discovery leads; verify material claims.",
    }


@tool
def crossref_research_search(
    query: str,
    max_results: int = 10,
    from_year: int | None = None,
) -> dict:
    """Search scholarly and professional publications indexed by Crossref."""
    max_results = max(1, min(max_results, 25))
    params: dict[str, Any] = {
        "query": query,
        "rows": max_results,
        "select": "DOI,title,author,published,container-title,type,URL,is-referenced-by-count",
    }
    if from_year:
        params["filter"] = f"from-pub-date:{from_year}-01-01"
    email = os.getenv("CROSSREF_MAILTO", "").strip()
    if email:
        params["mailto"] = email
    payload = cached_json(
        "GET",
        "https://api.crossref.org/works",
        params=params,
        ttl_seconds=86400,
    )
    results = []
    for item in payload.get("message", {}).get("items", []):
        authors = [
            " ".join(
                part
                for part in [author.get("given"), author.get("family")]
                if part
            )
            for author in item.get("author", [])
        ]
        date_parts = (
            item.get("published", {}).get("date-parts", [[]])[0]
            if item.get("published")
            else []
        )
        results.append(
            {
                "title": (item.get("title") or [None])[0],
                "doi": item.get("DOI"),
                "url": item.get("URL"),
                "authors": authors[:8],
                "published": "-".join(str(value) for value in date_parts),
                "publisher_or_journal": (
                    item.get("container-title") or [None]
                )[0],
                "type": item.get("type"),
                "citation_count": item.get("is-referenced-by-count"),
            }
        )
    return {
        "query": query,
        "count": len(results),
        "works": results,
        "source": "https://api.crossref.org/works",
    }


@tool
def openalex_research_search(query: str, max_results: int = 10) -> dict:
    """Search OpenAlex for research works and citation signals.

    Requires a free OPENALEX_API_KEY.
    """
    api_key = require_env("OPENALEX_API_KEY")
    max_results = max(1, min(max_results, 25))
    payload = cached_json(
        "GET",
        "https://api.openalex.org/works",
        params={
            "search": query,
            "per-page": max_results,
            "api_key": api_key,
            "select": (
                "id,doi,title,publication_year,cited_by_count,"
                "authorships,primary_location,open_access"
            ),
        },
        ttl_seconds=86400,
    )
    works = []
    for item in payload.get("results", []):
        authors = [
            authorship.get("author", {}).get("display_name")
            for authorship in item.get("authorships", [])[:8]
        ]
        location = item.get("primary_location") or {}
        source = location.get("source") or {}
        works.append(
            {
                "title": item.get("title"),
                "doi": item.get("doi"),
                "openalex_id": item.get("id"),
                "publication_year": item.get("publication_year"),
                "citation_count": item.get("cited_by_count"),
                "authors": [author for author in authors if author],
                "source": source.get("display_name"),
                "landing_page": location.get("landing_page_url"),
                "open_access": item.get("open_access"),
            }
        )
    return {
        "query": query,
        "count": len(works),
        "works": works,
        "source": "https://api.openalex.org/works",
    }


@tool
def wikipedia_search(query: str, max_results: int = 5) -> dict:
    """Search Wikipedia for background orientation, terminology, and entities.

    Use as a starting point only; confirm decision-critical facts elsewhere.
    """
    max_results = max(1, min(max_results, 10))
    payload = cached_json(
        "GET",
        "https://en.wikipedia.org/w/api.php",
        params={
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": max_results,
            "format": "json",
            "origin": "*",
        },
        ttl_seconds=86400,
    )
    results = [
        {
            "title": item.get("title"),
            "page_id": item.get("pageid"),
            "snippet": item.get("snippet"),
            "url": (
                "https://en.wikipedia.org/?curid="
                f"{item.get('pageid')}"
            ),
        }
        for item in payload.get("query", {}).get("search", [])
    ]
    return {
        "query": query,
        "count": len(results),
        "results": results,
        "source": "https://en.wikipedia.org/w/api.php",
        "caution": "Use for orientation, not as sole authority.",
    }

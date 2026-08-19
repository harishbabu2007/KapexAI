"""Indian legal & regulatory research tools.

Three tools ride the generic tool→router→message-log pipeline exactly like the
SWOT tool — no router, agent, or suggestion-system changes are required:

* ``indian_legal_search``   — discovery-only Tavily search biased towards the
  official Indian regulatory domains in ``worker/helpers/indian_sources.py``;
  emits ``legal_research`` (and ``legal_request``) entries.
* ``indian_case_search``    — Indian Kanoon API search; emits ``case_search``
  (and ``case_search_request``) entries.
* ``legal_issue_register``  — LLM-identified issues validated and scored
  deterministically; emits ``issue_register`` entries.

Grounding rules are enforced in Python, not just prompts: URLs/authorities are
only ever taken from actual retrieval results, ``effective_date`` is never
derived from a publication date, third-party sources are never presented as
official, and API tokens never leave the server or enter errors/output.
"""

import json
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from langchain_mistralai import ChatMistralAI

from worker.helpers.cached_http import (
    ToolConfigurationError,
    ToolServiceError,
    cached_json,
    require_env,
)
from worker.helpers.indian_sources import classify_source, official_domains
from worker.helpers.json_utils import parse_json
from worker.helpers.messages import business_context, format_transcript
from worker.prompts.legal import (
    INDIAN_CASE_QUERY_TEMPLATE,
    INDIAN_ISSUE_REGISTER_TEMPLATE,
    INDIAN_LEGAL_EXTRACTION_TEMPLATE,
    INDIAN_LEGAL_QUERY_TEMPLATE,
)
from worker.tools.base import Tool

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
INDIAN_KANOON_SEARCH_URL = "https://api.indiankanoon.org/search/"
INDIAN_KANOON_DOC_URL = "https://indiankanoon.org/doc/{tid}/"
TAVILY_MAX_RESULTS = 5

LEGAL_RESEARCH_DISCLAIMER = (
    "AI-curated. Verify every item against the official government source "
    "before relying on it."
)
CASE_SEARCH_DISCLAIMER = (
    "Case search by Indian Kanoon, a third-party legal database. Verify results "
    "against official court records — coverage may be incomplete or dated, and "
    "pending cases are not included."
)
ISSUE_REGISTER_DISCLAIMER = (
    "Compliance-awareness aid, not legal advice. Confirm every topic with a "
    "qualified advisor."
)

# Indian Kanoon `docsource` codes → body name. Only known codes are mapped;
# unknown codes surface as null rather than guessed.
KANOON_COURTS = {
    "supremecourt": "Supreme Court of India",
    "delhi": "High Court of Delhi",
    "bombay": "High Court of Bombay",
    "madras": "High Court of Madras",
    "calcutta": "High Court of Calcutta",
    "allahabad": "High Court of Allahabad",
    "patna": "High Court of Patna",
    "kerala": "High Court of Kerala",
    "karnataka": "High Court of Karnataka",
    "gujarat": "High Court of Gujarat",
    "rajasthan": "High Court of Rajasthan",
    "punjab": "High Court of Punjab and Haryana",
    "ghc": "High Court of Gauhati",
    "meghalaya": "High Court of Meghalaya",
    "chhattisgarh": "High Court of Chhattisgarh",
    "jharkhand": "High Court of Jharkhand",
    "uttarakhand": "High Court of Uttarakhand",
    "madhyapradesh": "Madhya Pradesh High Court",
    "mp": "Madhya Pradesh High Court",
    "odisha": "Orissa High Court",
    "orissa": "Orissa High Court",
    "himachal": "Himachal Pradesh High Court",
    "sikkim": "High Court of Sikkim",
    "tripura": "Tripura High Court",
    "manipur": "Manipur High Court",
    "telangana": "High Court of Telangana",
    "ap": "High Court of Andhra Pradesh",
    "ncdrc": "National Consumer Disputes Redressal Commission",
    "aifac": "Appellate Tribunal for Foreign Exchange (ATFE)",
    "itat": "Income Tax Appellate Tribunal (ITAT)",
    "cai": "Competition Commission of India / Appellate Tribunal",
    "cbdt": "Central Board of Direct Taxes",
    "irdai": "Insurance Regulatory and Development Authority of India",
    "pfrda": "Pension Fund Regulatory and Development Authority",
}


class IndianLegalSearchTool(Tool):
    """Tavily discovery over the official Indian regulatory allowlist."""

    name = "indian_legal_search"
    description = (
        "Research Indian regulatory and legal obligations for a business (India Code, "
        "eGazette, FSSAI, RBI, SEBI, MCA, Income Tax, GSTN, MeitY, Labour)."
    )
    example = "What licences do I need to run a food business in India?"
    suggestion = "Wanna check which Indian licences and regulations apply?"
    requires_context = False

    def __init__(self) -> None:
        self.llm = ChatMistralAI(model="mistral-small-2506", temperature=0.2)

    async def run(self, state: dict) -> list[dict]:
        request = str(state.get("user_input") or "")
        context = business_context(state["messages"])
        transcript = format_transcript(state["messages"])

        try:
            query = await self._build_query(request, context, transcript)
            payload = await self._search(query)
        except ToolConfigurationError as exc:
            return _request_entry("legal_request", request) + _missing_credentials(
                str(exc)
            )
        except ToolServiceError as exc:
            return _request_entry("legal_request", request) + _tool_error(str(exc))

        results = []
        try:
            results = await self._extract_results(payload, request)
        except ToolServiceError as exc:
            return _request_entry("legal_request", request) + _tool_error(str(exc))

        if not results:
            return _request_entry("legal_request", request) + [
                {
                    "role": "ASSISTANT",
                    "agent": "TOOL",
                    "type": "legal_research",
                    "content": _format_research(query, []),
                    "query": query,
                    "results": [],
                    "disclaimer": LEGAL_RESEARCH_DISCLAIMER,
                }
            ]

        return _request_entry("legal_request", request) + [
            {
                "role": "ASSISTANT",
                "agent": "TOOL",
                "type": "legal_research",
                "content": _format_research(query, results),
                "query": query,
                "results": results,
                "disclaimer": LEGAL_RESEARCH_DISCLAIMER,
            }
        ]

    async def _build_query(self, request: str, context: dict, transcript: str) -> str:
        chain = INDIAN_LEGAL_QUERY_TEMPLATE | self.llm
        response = await chain.ainvoke(
            {
                "request": request,
                "context": json.dumps(context, indent=2),
                "transcript": transcript,
            }
        )
        data = parse_json(response.content)
        query = (data or {}).get("query") if isinstance(data, dict) else None
        return str(query or request).strip()

    async def _search(self, query: str) -> dict:
        token = require_env("TAVILY_API_KEY")
        return await cached_json(
            "POST",
            TAVILY_SEARCH_URL,
            json_body={
                "query": query,
                "max_results": TAVILY_MAX_RESULTS,
                "search_depth": "basic",
                "include_domains": official_domains(),
                "include_answer": False,
                "include_raw_content": False,
            },
            headers={"Authorization": f"Bearer {token}"},
            ttl_seconds=3600,
        )

    async def _extract_results(self, payload: dict, request: str) -> list[dict]:
        items = payload.get("results", []) if isinstance(payload, dict) else []
        items = [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []
        if not items:
            return []
        chain = INDIAN_LEGAL_EXTRACTION_TEMPLATE | self.llm
        response = await chain.ainvoke(
            {
                "request": request,
                "search_results": json.dumps(items, indent=2, default=str),
            }
        )
        data = parse_json(response.content)
        extracted = data.get("results", []) if isinstance(data, dict) else []
        return _validate_research_items(items, extracted)


class IndianCaseSearchTool(Tool):
    """Indian Kanoon (third-party) case-law search."""

    name = "indian_case_search"
    description = (
        "Search Indian court judgments and orders (Supreme Court, High Courts, tribunals) "
        "through Indian Kanoon."
    )
    example = "Find Indian judgments about food packaging label requirements"
    suggestion = "Wanna search Indian case law on that?"
    requires_context = False

    def __init__(self) -> None:
        self.llm = ChatMistralAI(model="mistral-small-2506", temperature=0.2)

    async def run(self, state: dict) -> list[dict]:
        request = str(state.get("user_input") or "")
        transcript = format_transcript(state["messages"])

        try:
            query = await self._build_query(request, transcript)
            payload = await self._search(query)
        except ToolConfigurationError as exc:
            return _request_entry("case_search_request", request) + _missing_credentials(
                str(exc)
            )
        except ToolServiceError as exc:
            return _request_entry("case_search_request", request) + _tool_error(str(exc))

        cases = _parse_cases(payload)
        return _request_entry("case_search_request", request) + [
            {
                "role": "ASSISTANT",
                "agent": "TOOL",
                "type": "case_search",
                "content": _format_cases(query, cases),
                "query": query,
                "cases": cases,
                "disclaimer": CASE_SEARCH_DISCLAIMER,
            }
        ]

    async def _build_query(self, request: str, transcript: str) -> str:
        chain = INDIAN_CASE_QUERY_TEMPLATE | self.llm
        response = await chain.ainvoke(
            {"request": request, "transcript": transcript}
        )
        data = parse_json(response.content)
        query = (data or {}).get("query") if isinstance(data, dict) else None
        return str(query or request).strip()

    async def _search(self, query: str) -> dict:
        token = require_env("INDIANKANOON_API_TOKEN")
        return await cached_json(
            "POST",
            INDIAN_KANOON_SEARCH_URL,
            data={"formInput": query, "pagenum": 0},
            headers={
                "Accept": "application/json",
                "Authorization": f"Token {token}",
            },
            ttl_seconds=3600,
        )


class LegalIssueRegisterTool(Tool):
    """Builds a deterministic scored compliance issue register."""

    name = "legal_issue_register"
    description = (
        "Build a prioritized Indian compliance issue register for the business with "
        "deterministic risk scoring."
    )
    example = "List and score the legal issues my food business might face"
    suggestion = "Wanna register your business's compliance issues and risk scores?"
    requires_context = False

    def __init__(self) -> None:
        self.llm = ChatMistralAI(model="mistral-small-2506", temperature=0.2)

    async def run(self, state: dict) -> list[dict]:
        request = str(state.get("user_input") or "")
        context = business_context(state["messages"])
        transcript = format_transcript(state["messages"])
        available = _available_sources(state["messages"])
        available_urls = {s["url"] for s in available}

        chain = INDIAN_ISSUE_REGISTER_TEMPLATE | self.llm
        response = await chain.ainvoke(
            {
                "request": request,
                "context": json.dumps(context, indent=2),
                "transcript": transcript,
                "available_sources": json.dumps(available, indent=2),
            }
        )
        data = parse_json(response.content)
        raw_issues = data.get("issues", []) if isinstance(data, dict) else []
        issues = _score_issues(_validate_issues(raw_issues, available_urls))

        return _request_entry("issue_register_request", request) + [
            {
                "role": "ASSISTANT",
                "agent": "TOOL",
                "type": "issue_register",
                "content": _format_issues(issues),
                "issues": issues,
                "disclaimer": ISSUE_REGISTER_DISCLAIMER,
            }
        ]


# ── validation & formatting ─────────────────────────────────


def _validate_research_items(items: list[dict], extracted: list) -> list[dict]:
    """Reconciles the LLM extraction against the genuinely retrieved results.

    Only entries whose ``source_url`` matches a retrieved URL survive — invented
    URLs are dropped. Titles are copied verbatim from retrieval, source type and
    authority are decided by the domain allowlist (never the LLM), and dates are
    validated so an effective date can never silently fall back to a
    publication date. Official sources are listed first.
    """
    by_url: dict[str, dict] = {}
    for item in items:
        url = str(item.get("url") or "").strip()
        if url and url not in by_url:
            by_url[url] = item

    official: list[dict] = []
    third_party: list[dict] = []
    seen: set[str] = set()
    for raw in extracted:
        if not isinstance(raw, dict):
            continue
        source_url = str(raw.get("source_url") or "").strip()
        source = by_url.get(source_url)
        if source is None:
            continue  # never fabricate a source URL
        if source_url in seen:
            continue
        seen.add(source_url)

        is_official, source_type, authority = classify_source(source_url)
        (official if is_official else third_party).append(
            {
                "title": _strip_html(source.get("title")),
                "source_url": source_url,
                "authority": authority,
                "official_source": is_official,
                "source_type": source_type,
                "document_type": _nullable(raw.get("document_type")),
                "jurisdiction": _nullable(raw.get("jurisdiction")),
                "publication_date": _valid_date(source.get("published_date"))
                or _valid_date(raw.get("publication_date")),
                "effective_date": _valid_date(raw.get("effective_date")),
                "relevant_sections": _string_list(raw.get("relevant_sections")),
                "citation": _nullable(raw.get("citation")),
                "summary": _nullable(raw.get("summary")),
            }
        )
    return official + third_party


def _parse_cases(payload: dict) -> list[dict]:
    """Maps Indian Kanoon search results into the case schema. Citation is only
    ever taken from the payload; search results do not carry it, so it stays
    null instead of being guessed."""
    docs = payload.get("docs", []) if isinstance(payload, dict) else []
    if not isinstance(docs, list):
        docs = []
    cases: list[dict] = []
    seen: set[str] = set()
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        tid = doc.get("tid")
        key = f"{tid}|{doc.get('title', '')}"
        if key in seen:
            continue
        seen.add(key)
        url = INDIAN_KANOON_DOC_URL.format(tid=tid) if tid else None
        court = KANOON_COURTS.get(str(doc.get("docsource") or "").lower())
        cites = doc.get("citescount")
        cases.append(
            {
                "case_name": _strip_html(doc.get("title")),
                "court": court,
                "citation": None,
                "date": _valid_date(doc.get("publishdate")),
                "summary": _strip_html(
                    doc.get("snippet") or doc.get("headline") or ""
                ),
                "relevance": (
                    f"Cited {cites} times"
                    if isinstance(cites, (int, float)) and cites > 0
                    else None
                ),
                "url": url,
                "source_label": "Indian Kanoon",
                "source_type": "third_party",
            }
        )
    return cases


def _validate_issues(issues: list, available_urls: set[str]) -> list[dict]:
    """Validates the LLM issue extraction. ``basis`` values outside the allowed
    set fall back to inference; ``grounded_in`` is filtered to actually-retrieved
    URLs; a "source"-grounded issue without a surviving URL is downgraded to an
    inference instead of being presented as sourced."""
    valid_bases = {"source", "user_concern", "inference"}
    clean: list[dict] = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        title = str(issue.get("title") or "").strip()
        if not title:
            continue
        basis = str(issue.get("basis") or "inference").strip().lower()
        if basis not in valid_bases:
            basis = "inference"
        grounded = (
            [
                u
                for u in (issue.get("grounded_in") or [])
                if isinstance(u, str) and u.strip() in available_urls
            ]
            if basis == "source"
            else []
        )
        note = ""
        if basis == "source" and not grounded:
            basis = "inference"
            note = " Downgraded to inference: the claimed source URL was not retrieved."
        explanation = str(issue.get("explanation") or "").strip() or title
        clean.append(
            {
                "title": title,
                "category": _nullable(issue.get("category")),
                "basis": basis,
                "grounded_in": grounded,
                "explanation": explanation + note,
                "mitigation": _nullable(issue.get("mitigation")),
                "likelihood": _score(issue.get("likelihood")),
                "severity": _score(issue.get("severity")),
                "urgency": _score(issue.get("urgency")),
            }
        )
    return clean


def _score_issues(issues: list[dict]) -> list[dict]:
    """Deterministic scoring — the LLM never supplies the priority. Missing
    scores default to 1 and out-of-range values are clamped to 1-5 so a single
    odd value can't break or silently change the ranking."""
    for issue in issues:
        score = issue["likelihood"] * issue["severity"] * issue["urgency"]
        issue["priority_score"] = score
        issue["priority"] = (
            "critical"
            if score >= 60
            else "high"
            if score >= 30
            else "medium"
            if score >= 12
            else "low"
        )
    issues.sort(key=lambda i: i["priority_score"], reverse=True)
    return issues


def _available_sources(messages: list[dict]) -> list[dict]:
    """Collects the source URLs actually retrieved earlier in the conversation,
    so the issue register can only ever ground itself in real results."""
    sources: list[dict] = []
    seen: set[str] = set()
    for msg in messages:
        if msg.get("type") == "legal_research":
            for result in msg.get("results") or []:
                url = result.get("source_url")
                if url and url not in seen:
                    seen.add(url)
                    sources.append(
                        {
                            "url": url,
                            "title": result.get("title"),
                            "type": "regulatory",
                        }
                    )
        elif msg.get("type") == "case_search":
            for case in msg.get("cases") or []:
                url = case.get("url")
                if url and url not in seen:
                    seen.add(url)
                    sources.append(
                        {
                            "url": url,
                            "title": case.get("case_name") or url,
                            "type": "case_law",
                        }
                    )
    return sources


def _request_entry(req_type: str, request: str) -> list[dict]:
    return [
        {"role": "USER", "agent": "TOOL", "type": req_type, "content": request}
    ]


def _missing_credentials(message: str) -> list[dict]:
    return [
        {
            "role": "ASSISTANT",
            "agent": "TOOL",
            "type": "missing_credentials",
            "content": f"Sorry, this tool is not configured yet. {message}",
        }
    ]


def _tool_error(message: str) -> list[dict]:
    return [
        {
            "role": "ASSISTANT",
            "agent": "TOOL",
            "type": "tool_error",
            "content": f"I could not complete the search right now. {message}",
        }
    ]


def _score(value) -> int:
    """Coerces an LLM score to 1-5. Missing/garbage defaults to 1 so a single
    odd value can't break a turn or silently skew the ranking."""
    try:
        num = int(value)
    except (TypeError, ValueError):
        return 1
    return max(1, min(num, 5))


def _nullable(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _valid_date(value) -> str | None:
    """Returns a normalized ``YYYY-MM-DD`` when a value starts with a plausible
    date, else None. Keeps source dates safe and never synthesizes one."""
    if not value:
        return None
    match = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", str(value).strip())
    if not match:
        return None
    year, month, day = (int(g) for g in match.groups())
    if month < 1 or month > 12 or day < 1 or day > 31:
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def _strip_html(value) -> str | None:
    if value is None:
        return None
    text = re.sub(r"<[^>]+>", "", str(value))
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").strip()
    return text or None


def _format_research(query: str, results: list[dict]) -> str:
    lines = [f"**Search query:** {query}"]
    for i, result in enumerate(results, start=1):
        kind = "official" if result["official_source"] else "third-party"
        lines.append("")
        lines.append(f"### {i}. {result['title'] or 'Untitled'} — _{kind}_")
        lines.append(f"- **Source:** [{result['source_url']}]({result['source_url']})")
        if result.get("authority"):
            lines.append(f"- **Authority:** {result['authority']}")
        if result.get("document_type"):
            lines.append(f"- **Document type:** {result['document_type']}")
        if result.get("jurisdiction"):
            lines.append(f"- **Jurisdiction:** {result['jurisdiction']}")
        if result.get("publication_date"):
            lines.append(f"- **Published:** {result['publication_date']}")
        if result.get("effective_date"):
            lines.append(f"- **In effect from:** {result['effective_date']}")
        if result.get("relevant_sections"):
            lines.append(
                f"- **Sections:** {', '.join(result['relevant_sections'])}"
            )
        if result.get("citation"):
            lines.append(f"- **Citation:** {result['citation']}")
        if result.get("summary"):
            lines.append(f"- {result['summary']}")
    return "\n".join(lines)


def _format_cases(query: str, cases: list[dict]) -> str:
    lines = [f"**Search query:** {query}"]
    for i, case in enumerate(cases, start=1):
        lines.append("")
        lines.append(f"### {i}. {case['case_name'] or 'Untitled'}")
        if case.get("court"):
            lines.append(f"- **Court:** {case['court']}")
        if case.get("date"):
            lines.append(f"- **Decided:** {case['date']}")
        if case.get("relevance"):
            lines.append(f"- **Relevance:** {case['relevance']}")
        if case.get("url"):
            lines.append(f"- **View:** [{case['url']}]({case['url']})")
        if case.get("summary"):
            lines.append(f"- {case['summary']}")
    return "\n".join(lines)


def _format_issues(issues: list[dict]) -> str:
    if not issues:
        return "No compliance issues were identified from what we have so far."
    lines = []
    for i, issue in enumerate(issues, start=1):
        priority = str(issue.get("priority") or "low").upper()
        lines.append("")
        lines.append(f"### {i}. {issue['title']} — _{priority}_ (score {issue['priority_score']})")
        lines.append(f"- **Basis:** {issue['basis']}")
        if issue.get("category"):
            lines.append(f"- **Category:** {issue['category']}")
        lines.append(f"- {issue['explanation']}")
        if issue.get("mitigation"):
            lines.append(f"- **Suggested action:** {issue['mitigation']}")
        for url in issue.get("grounded_in") or []:
            lines.append(f"- **Source:** <{url}>")
    return "\n".join(lines)
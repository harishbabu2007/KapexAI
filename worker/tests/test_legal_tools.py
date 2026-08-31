import json
import time
import pytest
from types import SimpleNamespace

from conftest import run as _run
from langchain_core.runnables import RunnableLambda

from worker.helpers.cached_http import _cache_key
from worker.helpers.indian_sources import (
    INDIAN_OFFICIAL_SOURCES,
    classify_source,
    official_domains,
)

# NOTE: import order matters. `worker.tools.legal_tools` loads the root `.env`
# (via python-dotenv) before importing `cached_http`, so the redis_service
# client is created against the real REDIS_URL instead of localhost.
from worker.tools import legal_tools as lt
from worker.tools.base import Tool
from worker.tools.registry import get_tool, list_tools

TEST_IDEA = "I want to open a specialty coffee shop in Pune."
TEST_EMAIL = "legal-tools-test@example.com"


def _state(request="What licences does a food business need?", messages=None):
    return {
        "session_id": "s",
        "user_input": request,
        "messages": messages
        or [
            {"role": "USER", "agent": "CHAT", "type": "chat", "content": "I sell packaged snacks in Pune"},
            {
                "role": "ASSISTANT",
                "agent": "TOOL",
                "type": "questionnaire_complete",
                "content": "done",
                "context": {"business_about": "packaged snacks"},
            },
        ],
    }


# ── registry & tool metadata ────────────────────────────────


def test_legal_tools_registered():
    assert get_tool("indian_legal_search") is not None
    assert get_tool("indian_case_search") is not None
    assert get_tool("legal_issue_register") is not None


def test_legal_tools_in_suggestion_listing():
    names = {t["name"] for t in list_tools()}
    assert {"indian_legal_search", "indian_case_search", "legal_issue_register"} <= names
    for tool in list_tools():
        if tool["name"] in {"indian_legal_search", "indian_case_search", "legal_issue_register"}:
            assert tool["description"]
            assert tool["example"]
            assert tool["suggestion"]


def test_legal_tools_do_not_require_context():
    assert lt.IndianLegalSearchTool.requires_context is False
    assert lt.IndianCaseSearchTool.requires_context is False
    assert lt.LegalIssueRegisterTool.requires_context is False


def test_legal_tools_are_tool_subclasses():
    assert issubclass(lt.IndianLegalSearchTool, Tool)
    assert issubclass(lt.IndianCaseSearchTool, Tool)
    assert issubclass(lt.LegalIssueRegisterTool, Tool)


# ── official-domain allowlist ───────────────────────────────


def test_classify_official_urls():
    urls = [
        "https://www.fssai.gov.in/notices/x",
        "https://fssai.gov.in/x",
        "https://sub.rbi.org.in/notifications/y",
        "http://egazette.gov.in/g",
        "https://indiacode.nic.in/acts",
    ]
    for url in urls:
        official, source_type, authority = classify_source(url)
        assert official is True, url
        assert source_type == "official"
        assert authority


def test_classify_third_party_and_missing():
    official, source_type, authority = classify_source("https://taxguru.in/a")
    assert (official, source_type, authority) == (False, "third_party", None)
    assert classify_source("https://example.com/a")[1] == "third_party"
    assert classify_source("")[0] is False
    assert classify_source(None)[0] is False
    assert classify_source("not a url")[1] == "third_party"


def test_official_domains_are_centralized():
    assert "fssai.gov.in" in official_domains()
    assert "indiacode.nic.in" in official_domains()
    assert len(official_domains()) == len(INDIAN_OFFICIAL_SOURCES)


# ── dates ───────────────────────────────────────────────────


def test_valid_date_parser():
    assert lt._valid_date("2025-04-01") == "2025-04-01"
    assert lt._valid_date("2025-4-1") == "2025-04-01"
    assert lt._valid_date("2025-04-01T10:20:00Z") == "2025-04-01"
    assert lt._valid_date("tomorrow") is None
    assert lt._valid_date("") is None
    assert lt._valid_date(None) is None
    assert lt._valid_date("2025-13-01") is None
    assert lt._valid_date("2025-04-32") is None


def test_effective_date_never_derived_from_publication():
    """Regression: a result with a publication date but no explicit effective
    date must have effective_date=None — it must NEVER silently become the
    publication date."""
    items = [
        {
            "title": "FSSAI circular on licensing",
            "url": "https://www.fssai.gov.in/cir.pdf",
            "content": "text",
            "published_date": "2025-03-01T00:00:00Z",
        }
    ]
    extracted = [
        {
            "title": "FSSAI circular on licensing",
            "source_url": "https://www.fssai.gov.in/cir.pdf",
            "document_type": "circular",
            "jurisdiction": "India",
            "publication_date": "2025-03-01",
            "effective_date": None,
            "relevant_sections": [],
            "citation": None,
            "summary": "A circular.",
        }
    ]
    results = lt._validate_research_items(items, extracted)
    assert len(results) == 1
    result = results[0]
    assert result["publication_date"] == "2025-03-01"
    assert result["effective_date"] is None


def test_explicit_effective_date_is_honored():
    items = [
        {
            "title": "Notification",
            "url": "https://egazette.gov.in/n",
            "content": "effective from 1 April 2025",
            "published_date": "2025-02-10T00:00:00Z",
        }
    ]
    extracted = [
        {
            "title": "Notification",
            "source_url": "https://egazette.gov.in/n",
            "document_type": "notification",
            "jurisdiction": None,
            "publication_date": None,
            "effective_date": "2025-04-01",
            "relevant_sections": [],
            "citation": None,
            "summary": "Comes into force 1 April 2025.",
        }
    ]
    results = lt._validate_research_items(items, extracted)
    assert results[0]["publication_date"] == "2025-02-10"
    assert results[0]["effective_date"] == "2025-04-01"


def test_impossible_effective_date_is_nulled():
    items = [
        {
            "title": "Guideline",
            "url": "https://www.sebi.gov.in/g",
            "content": "text",
            "published_date": None,
        }
    ]
    extracted = [
        {
            "title": "Guideline",
            "source_url": "https://www.sebi.gov.in/g",
            "document_type": "guideline",
            "jurisdiction": None,
            "publication_date": None,
            "effective_date": "sometime next year",
            "relevant_sections": [],
            "citation": None,
            "summary": "x",
        }
    ]
    results = lt._validate_research_items(items, extracted)
    assert results[0]["effective_date"] is None


# ── regulatory result validation ────────────────────────────


def test_research_drops_invented_urls():
    items = [
        {"title": "Real source", "url": "https://www.fssai.gov.in/a", "published_date": None}
    ]
    extracted = [
        {
            "title": "Real source",
            "source_url": "https://www.fssai.gov.in/a",
            "document_type": None,
            "jurisdiction": None,
            "publication_date": None,
            "effective_date": None,
            "relevant_sections": [],
            "citation": None,
            "summary": None,
        },
        {
            "title": "Invented source",
            "source_url": "https://example.com/never-retrieved",
            "document_type": None,
            "jurisdiction": None,
            "publication_date": None,
            "effective_date": None,
            "relevant_sections": [],
            "citation": None,
            "summary": None,
        },
    ]
    results = lt._validate_research_items(items, extracted)
    assert [r["source_url"] for r in results] == ["https://www.fssai.gov.in/a"]


def test_research_official_first_and_verbatim_titles():
    items = [
        {"title": "Tax analysis", "url": "https://taxguru.in/art", "published_date": None},
        {"title": "CBDT notification", "url": "https://www.incometax.gov.in/n", "published_date": None},
    ]
    extracted = [
        {
            "title": "Rewritten tax title",
            "source_url": "https://taxguru.in/art",
            "document_type": "article",
            "jurisdiction": None,
            "publication_date": None,
            "effective_date": None,
            "relevant_sections": [],
            "citation": None,
            "summary": "tax",
        },
        {
            "title": "Rewritten gov title",
            "source_url": "https://www.incometax.gov.in/n",
            "document_type": "notification",
            "jurisdiction": "India",
            "publication_date": None,
            "effective_date": None,
            "relevant_sections": [],
            "citation": None,
            "summary": "gov",
        },
    ]
    results = lt._validate_research_items(items, extracted)
    # Official sources come first, titles are taken verbatim from retrieval.
    assert [r["source_url"] for r in results] == [
        "https://www.incometax.gov.in/n",
        "https://taxguru.in/art",
    ]
    assert results[0]["title"] == "CBDT notification"
    assert results[1]["title"] == "Tax analysis"
    assert results[0]["official_source"] is True
    assert results[1]["official_source"] is False
    assert results[1]["source_type"] == "third_party"
    assert results[1]["authority"] is None


# ── case parsing ────────────────────────────────────────────


def test_parse_cases():
    payload = {
        "docs": [
            {
                "tid": 1950282,
                "title": "M/s XYZ <b>Ltd</b> v. State",
                "docsource": "bombay",
                "publishdate": "2020-01-15",
                "snippet": "Some <b>highlight</b> text",
                "citescount": 3,
            },
            {
                "tid": 1950283,
                "title": "ABC v. DEF",
                "docsource": "unknowncode",
                "publishdate": "not-a-date",
                "snippet": "",
                "citescount": 0,
            },
            {
                "tid": 1950282,
                "title": "M/s XYZ <b>Ltd</b> v. State",
                "docsource": "bombay",
                "publishdate": "2020-01-15",
                "snippet": "duplicate",
                "citescount": 3,
            },
            {"title": "No TID", "docsource": "supremecourt", "publishdate": "2021-02-02"},
        ]
    }
    cases = lt._parse_cases(payload)
    assert len(cases) == 3  # the duplicate is dropped

    first = cases[0]
    assert first["case_name"] == "M/s XYZ Ltd v. State"
    assert first["court"] == "High Court of Bombay"
    assert first["url"] == "https://indiankanoon.org/doc/1950282/"
    assert first["date"] == "2020-01-15"
    assert first["summary"] == "Some highlight text"
    assert first["relevance"] == "Cited 3 times"
    # Search results do not carry a citation — it must stay null, never guessed.
    assert first["citation"] is None
    assert first["source_label"] == "Indian Kanoon"
    assert first["source_type"] == "third_party"

    second = cases[1]
    assert second["court"] is None  # unknown docsource → null, not a guess
    assert second["date"] is None
    assert second["relevance"] is None

    third = cases[2]
    assert third["url"] is None  # no tid → no invented URL


# ── issue register validation & scoring ─────────────────────


def test_validate_issues_basis_and_grounding():
    available = {"https://www.fssai.gov.in/x", "https://www.rbi.org.in/y"}
    issues = [
        {
            "title": "FSSAI licence",
            "category": "food safety",
            "basis": "source",
            "grounded_in": ["https://www.fssai.gov.in/x"],
            "explanation": "Needs a licence",
            "mitigation": "Apply",
            "likelihood": 5,
            "severity": 4,
            "urgency": 3,
        },
        {
            "title": "Fake grounding",
            "basis": "source",
            "grounded_in": ["https://evil.example.com/fake"],
            "explanation": "Not retrievable",
            "likelihood": 1,
            "severity": 1,
            "urgency": 1,
        },
        {
            "title": "Weird basis",
            "basis": "totally-made-up",
            "grounded_in": ["https://www.fssai.gov.in/x"],
            "explanation": "Invalid basis",
            "likelihood": 1,
            "severity": 1,
            "urgency": 1,
        },
        {"title": "  ", "explanation": "dropped"},
        {
            "title": "User raised",
            "basis": "user_concern",
            "grounded_in": ["https://www.fssai.gov.in/x"],
            "explanation": "The user asked about it",
            "likelihood": 7,
            "severity": 0,
            "urgency": "banana",
        },
    ]
    cleaned = lt._validate_issues(issues, available)

    assert [i["title"] for i in cleaned] == [
        "FSSAI licence",
        "Fake grounding",
        "Weird basis",
        "User raised",
    ]

    sourced = cleaned[0]
    assert sourced["basis"] == "source"
    assert sourced["grounded_in"] == ["https://www.fssai.gov.in/x"]
    assert sourced["likelihood"] == 5

    downgraded = cleaned[1]
    assert downgraded["basis"] == "inference"
    assert downgraded["grounded_in"] == []
    assert "Downgraded to inference" in downgraded["explanation"]

    weird = cleaned[2]
    assert weird["basis"] == "inference"
    assert weird["grounded_in"] == []  # inference never carries sources

    user = cleaned[3]
    assert user["basis"] == "user_concern"
    assert user["grounded_in"] == []
    # Out-of-range scores are clamped to 1-5, garbage defaults to 1.
    assert user["likelihood"] == 5
    assert user["severity"] == 1
    assert user["urgency"] == 1


def test_score_issues_deterministic():
    issues = [
        {"title": "crit", "likelihood": 5, "severity": 5, "urgency": 5},
        {"title": "high", "likelihood": 5, "severity": 3, "urgency": 2},
        {"title": "medium", "likelihood": 3, "severity": 2, "urgency": 2},
        {"title": "low", "likelihood": 1, "severity": 1, "urgency": 1},
    ]
    scored = lt._score_issues(issues)
    assert [i["priority"] for i in scored] == ["critical", "high", "medium", "low"]
    assert [i["priority_score"] for i in scored] == [125, 30, 12, 1]
    # Sorted highest score first.
    assert scored[0]["title"] == "crit"
    # The LLM never provides the priority — it is always recomputed.
    for issue in scored:
        assert issue["priority_score"] == (
            issue["likelihood"] * issue["severity"] * issue["urgency"]
        )


def test_available_sources_collected_from_messages():
    messages = [
        {
            "role": "ASSISTANT",
            "agent": "TOOL",
            "type": "legal_research",
            "results": [
                {"source_url": "https://www.fssai.gov.in/x", "title": "FSSAI"},
                {"source_url": "https://www.fssai.gov.in/x", "title": "FSSAI dup"},
            ],
        },
        {
            "role": "ASSISTANT",
            "agent": "TOOL",
            "type": "case_search",
            "cases": [{"url": "https://indiankanoon.org/doc/1/", "case_name": "ABC v DEF"}],
        },
        {"role": "USER", "agent": "CHAT", "type": "chat", "content": "hi"},
    ]
    sources = lt._available_sources(messages)
    assert {s["url"] for s in sources} == {
        "https://www.fssai.gov.in/x",
        "https://indiankanoon.org/doc/1/",
    }


# ── token safety & cache keys ───────────────────────────────


def test_cache_key_ignores_headers():
    url = "https://api.example.com/x"
    params = {"q": "same"}
    key_without = _cache_key("POST", url, params, None, None)
    key_with_header = _cache_key("POST", url, params, None, None)
    assert key_without == key_with_header
    assert "TOKEN" not in key_without
    # A different query changes the key — no cross-query collisions.
    assert key_without != _cache_key("POST", url, {"q": "other"}, None, None)
    assert key_without != _cache_key("GET", url, params, None, None)


def test_token_never_leaks_into_output(monkeypatch):
    captured = {}

    async def fake_cached_json(method, url, **kwargs):
        captured["headers"] = kwargs.get("headers", {})
        return {"results": []}

    async def fake_build(self, request, context, transcript):
        return "query"

    async def fake_extract(self, payload, request):
        return []

    monkeypatch.setattr(lt, "cached_json", fake_cached_json)
    monkeypatch.setenv("TAVILY_API_KEY", "SECRETTOKEN123")
    monkeypatch.setattr(lt.IndianLegalSearchTool, "_build_query", fake_build)
    monkeypatch.setattr(lt.IndianLegalSearchTool, "_extract_results", fake_extract)

    tool = lt.IndianLegalSearchTool()
    entries = _run(tool.run(_state()))
    assert captured["headers"]["Authorization"] == "Bearer SECRETTOKEN123"
    assert "SECRETTOKEN123" not in json.dumps(entries)
    key = _cache_key("POST", lt.TAVILY_SEARCH_URL, None, None, None)
    assert "SECRETTOKEN123" not in key


# ── run() unit tests (external calls mocked) ────────────────


def test_legal_search_run_happy_path(monkeypatch):
    captured = {}

    async def fake_build(self, request, context, transcript):
        captured["context"] = context
        captured["transcript"] = transcript
        return "FSSAI food business licence india"

    async def fake_search(self, query):
        assert query == "FSSAI food business licence india"
        return {
            "results": [
                {
                    "title": "FSSAI - Food Safety and Standards",
                    "url": "https://www.fssai.gov.in/reg",
                    "content": "FBO registration details",
                    "published_date": None,
                }
            ]
        }

    async def fake_extract(self, payload, request):
        return [
            {
                "title": "FSSAI - Food Safety and Standards",
                "source_url": "https://www.fssai.gov.in/reg",
                "authority": "Food Safety and Standards Authority of India (FSSAI)",
                "official_source": True,
                "source_type": "official",
                "document_type": "regulation",
                "jurisdiction": "India",
                "publication_date": None,
                "effective_date": None,
                "relevant_sections": ["Section 31"],
                "citation": None,
                "summary": "Food businesses must be licensed.",
            }
        ]

    monkeypatch.setattr(lt.IndianLegalSearchTool, "_build_query", fake_build)
    monkeypatch.setattr(lt.IndianLegalSearchTool, "_search", fake_search)
    monkeypatch.setattr(lt.IndianLegalSearchTool, "_extract_results", fake_extract)

    tool = lt.IndianLegalSearchTool()
    entries = _run(tool.run(_state()))

    assert entries[0] == {
        "role": "USER",
        "agent": "TOOL",
        "type": "legal_request",
        "content": "What licences does a food business need?",
    }
    msg = entries[1]
    assert msg["type"] == "legal_research"
    assert msg["query"] == "FSSAI food business licence india"
    assert len(msg["results"]) == 1
    result = msg["results"][0]
    assert result["official_source"] is True
    assert result["source_type"] == "official"
    assert result["authority"] == "Food Safety and Standards Authority of India (FSSAI)"
    assert result["relevant_sections"] == ["Section 31"]
    assert msg["disclaimer"]
    # Business context and transcript reached the query builder.
    assert "packaged snacks" in json.dumps(captured["context"])
    assert "packaged snacks" in captured["transcript"]


def test_legal_search_run_no_results(monkeypatch):
    async def fake_build(self, request, context, transcript):
        return "query"

    async def fake_search(self, query):
        return {"results": []}

    async def fake_extract(self, payload, request):
        return []

    monkeypatch.setattr(lt.IndianLegalSearchTool, "_build_query", fake_build)
    monkeypatch.setattr(lt.IndianLegalSearchTool, "_search", fake_search)
    monkeypatch.setattr(lt.IndianLegalSearchTool, "_extract_results", fake_extract)

    entries = _run(lt.IndianLegalSearchTool().run(_state()))
    assert entries[1]["type"] == "legal_research"
    assert entries[1]["results"] == []


def test_legal_search_missing_credentials(monkeypatch):
    async def fake_build(self, request, context, transcript):
        return "query"

    monkeypatch.setattr(lt.IndianLegalSearchTool, "_build_query", fake_build)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    entries = _run(lt.IndianLegalSearchTool().run(_state()))
    assert entries[0]["type"] == "legal_request"
    assert entries[1]["type"] == "missing_credentials"
    assert "TAVILY_API_KEY" in entries[1]["content"]


def test_legal_search_service_error(monkeypatch):
    async def fake_build(self, request, context, transcript):
        return "query"

    async def fake_search(self, query):
        raise lt.ToolServiceError("Tavily is unavailable (HTTP 500)")

    monkeypatch.setattr(lt.IndianLegalSearchTool, "_build_query", fake_build)
    monkeypatch.setattr(lt.IndianLegalSearchTool, "_search", fake_search)

    entries = _run(lt.IndianLegalSearchTool().run(_state()))
    assert entries[1]["type"] == "tool_error"
    assert "Tavily is unavailable" in entries[1]["content"]


def test_case_search_run(monkeypatch):
    async def fake_build(self, request, transcript):
        return "food packaging label high court"

    async def fake_search(self, query):
        return {
            "docs": [
                {
                    "tid": 42,
                    "title": "ABC <b>Pvt Ltd</b> v. DEF",
                    "docsource": "delhi",
                    "publishdate": "2019-05-05",
                    "snippet": "Label requirements <b>discussed</b>",
                    "citescount": 2,
                }
            ]
        }

    monkeypatch.setattr(lt.IndianCaseSearchTool, "_build_query", fake_build)
    monkeypatch.setattr(lt.IndianCaseSearchTool, "_search", fake_search)

    entries = _run(lt.IndianCaseSearchTool().run(_state("find cases about labels")))
    assert entries[0]["type"] == "case_search_request"
    msg = entries[1]
    assert msg["type"] == "case_search"
    assert msg["query"] == "food packaging label high court"
    case = msg["cases"][0]
    assert case["case_name"] == "ABC Pvt Ltd v. DEF"
    assert case["court"] == "High Court of Delhi"
    assert case["url"] == "https://indiankanoon.org/doc/42/"
    assert case["date"] == "2019-05-05"
    assert case["summary"] == "Label requirements discussed"
    assert case["citation"] is None
    assert msg["disclaimer"]


def test_case_search_missing_token(monkeypatch):
    async def fake_build(self, request, transcript):
        return "query"

    monkeypatch.setattr(lt.IndianCaseSearchTool, "_build_query", fake_build)
    monkeypatch.delenv("INDIANKANOON_API_TOKEN", raising=False)

    entries = _run(lt.IndianCaseSearchTool().run(_state()))
    assert entries[1]["type"] == "missing_credentials"
    assert "INDIANKANOON_API_TOKEN" in entries[1]["content"]


def test_issue_register_run(monkeypatch):
    state = _state()
    state["messages"] = state["messages"] + [
        {
            "role": "ASSISTANT",
            "agent": "TOOL",
            "type": "legal_research",
            "content": "",
            "results": [
                {"source_url": "https://www.fssai.gov.in/reg", "title": "FSSAI reg"}
            ],
        }
    ]
    llm_output = json.dumps(
        {
            "issues": [
                {
                    "title": "FSSAI licence",
                    "category": "food safety",
                    "basis": "source",
                    "grounded_in": ["https://www.fssai.gov.in/reg"],
                    "explanation": "The business needs a food licence.",
                    "mitigation": "Apply for a licence",
                    "likelihood": 5,
                    "severity": 4,
                    "urgency": 3,
                },
                {
                    "title": "Made-up obligation",
                    "basis": "source",
                    "grounded_in": ["https://invented.example.com/fake"],
                    "explanation": "Not grounded in anything retrieved.",
                    "likelihood": 1,
                    "severity": 1,
                    "urgency": 1,
                },
            ]
        }
    )
    tool = lt.LegalIssueRegisterTool()
    tool.llm = RunnableLambda(lambda inputs: SimpleNamespace(content=llm_output))

    entries = _run(tool.run(state))
    assert entries[0]["type"] == "issue_register_request"
    msg = entries[1]
    assert msg["type"] == "issue_register"
    issues = msg["issues"]
    assert len(issues) == 2

    sourced = issues[0]
    assert sourced["basis"] == "source"
    assert sourced["grounded_in"] == ["https://www.fssai.gov.in/reg"]
    assert sourced["priority"] == "critical"  # 5*4*3 = 60
    assert sourced["priority_score"] == 60

    downgraded = issues[1]
    assert downgraded["basis"] == "inference"
    assert downgraded["grounded_in"] == []
    assert "Downgraded to inference" in downgraded["explanation"]
    assert downgraded["priority"] == "low"
    assert msg["disclaimer"]


# ── prompt rendering smoke tests ────────────────────────────


def test_legal_prompt_templates_render():
    from worker.prompts.legal import (
        INDIAN_CASE_QUERY_TEMPLATE,
        INDIAN_ISSUE_REGISTER_TEMPLATE,
        INDIAN_LEGAL_EXTRACTION_TEMPLATE,
        INDIAN_LEGAL_QUERY_TEMPLATE,
    )

    query = INDIAN_LEGAL_QUERY_TEMPLATE.invoke(
        {"request": "q", "context": "{}", "transcript": "hi"}
    ).to_string()
    assert '{"query"' in query

    extraction = INDIAN_LEGAL_EXTRACTION_TEMPLATE.invoke(
        {"request": "q", "search_results": "[]"}
    ).to_string()
    assert '"results"' in extraction

    case = INDIAN_CASE_QUERY_TEMPLATE.invoke(
        {"request": "q", "transcript": "hi"}
    ).to_string()
    assert '{"query"' in case

    register = INDIAN_ISSUE_REGISTER_TEMPLATE.invoke(
        {"request": "q", "context": "{}", "transcript": "hi", "available_sources": "[]"}
    ).to_string()
    assert '"issues"' in register


# ── end-to-end flow tests (real DB + Redis) ─────────────────

from db_service import db
from redis_service import redis

from worker.agent import build_graph, process_job
from worker.agents.router_agent import RouterAgent
from worker.helpers.persistence import add_message


async def _cleanup(session_id=None):
    if session_id:
        await redis.delete(f"langgraph_state:{session_id}")
        await db.message.delete_many(where={"sessionId": session_id})
        await db.session.delete_many(where={"id": session_id})
    await db.user.delete_many(where={"email": TEST_EMAIL})


async def _make_session():
    await _cleanup()
    user = await db.user.create(data={"email": TEST_EMAIL, "name": "Test User"})
    session = await db.session.create(
        data={"userId": user.id, "business_idea": TEST_IDEA}
    )
    return session


async def _subscribe(session_id):
    ps = redis.pubsub()
    await ps.subscribe(f"stream:{session_id}")
    await ps.get_message(timeout=1)
    return ps


async def _collect(ps, count, timeout=10.0):
    events = []
    deadline = time.time() + timeout
    while len(events) < count and time.time() < deadline:
        msg = await ps.get_message(timeout=1)
        if msg and msg.get("type") == "message":
            events.append(json.loads(msg["data"]))
    return events


async def _seed_completed_questionnaire(sid):
    await add_message(sid, "USER", "CHAT", {"type": "chat", "content": "seed"})
    await add_message(
        sid,
        "ASSISTANT",
        "TOOL",
        {
            "type": "questionnaire_complete",
            "content": "done",
            "context": {"business_about": TEST_IDEA},
        },
    )


def test_legal_search_flow_streams_and_persists(monkeypatch):
    async def fake_classify(self, user_input, messages, tools):
        return {"intent": "tool", "tool": "indian_legal_search"}

    async def fake_build(self, request, context, transcript):
        return "fssai licence"

    async def fake_search(self, query):
        return {
            "results": [
                {
                    "title": "FSSAI reg",
                    "url": "https://www.fssai.gov.in/reg",
                    "content": "licence",
                    "published_date": None,
                }
            ]
        }

    async def fake_extract(self, payload, request):
        return [
            {
                "title": "FSSAI reg",
                "source_url": "https://www.fssai.gov.in/reg",
                "authority": "Food Safety and Standards Authority of India (FSSAI)",
                "official_source": True,
                "source_type": "official",
                "document_type": "regulation",
                "jurisdiction": "India",
                "publication_date": None,
                "effective_date": None,
                "relevant_sections": [],
                "citation": None,
                "summary": "Get a licence.",
            }
        ]

    monkeypatch.setattr(RouterAgent, "classify", fake_classify)
    monkeypatch.setattr(lt.IndianLegalSearchTool, "_build_query", fake_build)
    monkeypatch.setattr(lt.IndianLegalSearchTool, "_search", fake_search)
    monkeypatch.setattr(lt.IndianLegalSearchTool, "_extract_results", fake_extract)

    async def scenario():
        session = await _make_session()
        sid = session.id
        await _seed_completed_questionnaire(sid)
        graph = build_graph()
        ps = await _subscribe(sid)
        try:
            result = await process_job(
                {"session_id": sid, "user_input": "What licences?"}, graph
            )
            events = await _collect(ps, 3)

            assert result["messages"][-1]["type"] == "legal_research"
            assert result["messages"][-1]["results"][0]["official_source"] is True

            assert events[0]["type"] == "legal_research"
            assert events[1]["type"] == "suggestions"
            assert {t["name"] for t in events[1]["tools"]} == {
                "swot",
                "web_search",
                "economics",
                "foresight",
                "finance",
                "astrology",
                "indian_legal_search",
                "indian_case_search",
                "legal_issue_register",
                "indian_finance",
            }
            assert events[2]["type"] == "end"

            msgs = await db.message.find_many(where={"sessionId": sid})
            assert sorted(m.agent for m in msgs) == ["CHAT", "TOOL", "TOOL", "TOOL"]

            await ps.unsubscribe(f"stream:{sid}")
            await ps.close()
        finally:
            await _cleanup(sid)

    _run(scenario())


def test_case_search_flow_runs_without_questionnaire(monkeypatch):
    """The legal tools do not require business context, so they run even before
    the questionnaire is completed."""
    async def fake_classify(self, user_input, messages, tools):
        return {"intent": "tool", "tool": "indian_case_search"}

    async def fake_build(self, request, transcript):
        return "food labels high court"

    async def fake_search(self, query):
        return {
            "docs": [
                {
                    "tid": 7,
                    "title": "Matter of Labels",
                    "docsource": "supremecourt",
                    "publishdate": "2021-01-01",
                    "snippet": "text",
                    "citescount": 1,
                }
            ]
        }

    monkeypatch.setattr(RouterAgent, "classify", fake_classify)
    monkeypatch.setattr(lt.IndianCaseSearchTool, "_build_query", fake_build)
    monkeypatch.setattr(lt.IndianCaseSearchTool, "_search", fake_search)

    async def scenario():
        session = await _make_session()
        sid = session.id
        graph = build_graph()
        ps = await _subscribe(sid)
        try:
            result = await process_job(
                {"session_id": sid, "user_input": "Find judgments"}, graph
            )
            events = await _collect(ps, 2)

            assert result["messages"][-1]["type"] == "case_search"
            assert result["messages"][-1]["cases"][0]["court"] == "Supreme Court of India"

            # No questionnaire was started — the tool does not require context.
            assert not any(m["type"] == "questionnaire_start" for m in result["messages"])
            # Without a completed questionnaire, only `end` streams (no suggestions).
            assert events[0]["type"] == "case_search"
            assert events[1]["type"] == "end"
            assert not any(e["type"] == "suggestions" for e in events)

            await ps.unsubscribe(f"stream:{sid}")
            await ps.close()
        finally:
            await _cleanup(sid)

    _run(scenario())


def test_issue_register_flow(monkeypatch):
    async def fake_classify(self, user_input, messages, tools):
        return {"intent": "tool", "tool": "legal_issue_register"}

    llm_output = json.dumps(
        {
            "issues": [
                {
                    "title": "GST registration",
                    "category": "gst",
                    "basis": "inference",
                    "grounded_in": [],
                    "explanation": "May need GST registration.",
                    "mitigation": "Check GSTN",
                    "likelihood": 3,
                    "severity": 2,
                    "urgency": 2,
                }
            ]
        }
    )
    chain = RunnableLambda(lambda inputs: SimpleNamespace(content=llm_output))
    registered = get_tool("legal_issue_register")
    monkeypatch.setattr(registered, "llm", chain)
    monkeypatch.setattr(RouterAgent, "classify", fake_classify)

    async def scenario():
        session = await _make_session()
        sid = session.id
        await _seed_completed_questionnaire(sid)
        graph = build_graph()
        ps = await _subscribe(sid)
        try:
            result = await process_job(
                {"session_id": sid, "user_input": "List my compliance issues"}, graph
            )
            events = await _collect(ps, 3)

            assert result["messages"][-1]["type"] == "issue_register"
            issue = result["messages"][-1]["issues"][0]
            assert issue["title"] == "GST registration"
            assert issue["priority"] == "medium"  # 3*2*2 = 12
            assert issue["priority_score"] == 12

            assert events[0]["type"] == "issue_register"
            assert events[1]["type"] == "suggestions"
            assert events[2]["type"] == "end"

            await ps.unsubscribe(f"stream:{sid}")
            await ps.close()
        finally:
            await _cleanup(sid)

    _run(scenario())
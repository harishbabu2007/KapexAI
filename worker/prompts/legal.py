"""Prompt templates for the Indian legal tools.

The tools operate only on Indian law: statutes (India Code), delegated
legislation and notifications (eGazette), and the regulations/guidelines of
FSSAI, RBI, SEBI, MCA, Income Tax, GSTN, MeitY and the Labour Ministry. The
extraction template enforces the "only what the source supports" rule — the
tools never let the LLM invent URLs, authorities, effective dates or citations.
"""

from langchain_core.prompts import ChatPromptTemplate

INDIAN_LEGAL_SCOPE = """\
The legal tools research INDIAN law only. Statutes on India Code (indiacode.nic.in), \
gazette notifications (egazette.gov.in), and the regulations/guidelines of FSSAI, RBI, \
SEBI, MCA, Income Tax Department, GSTN, MeitY and the Ministry of Labour & Employment. \
Results on those official domains are labelled official; anything else is labelled as a \
third-party source and is never presented as an official government record. The tools \
return curated leads for compliance awareness — NOT legal advice."""

# ── indian_legal_search ─────────────────────────────────────

INDIAN_LEGAL_QUERY_PROMPT = """\
You are an Indian regulatory research assistant. Build a single web-search query that \
will discover an OFFICIAL Indian government source relevant to the user's request.

Business context:
{context}

Conversation so far:
{transcript}

User's request:
{request}

Rules:
- One concise query, 5-12 words. Name the act/regulation/topic (e.g. "FSSAI food \
business operator licence registration"). Prefer the exact regulator, act or rule the \
user's request implies. Search INDIAN law only.
- Do NOT answer the request. Only produce the query.

Return ONLY valid JSON: {{"query": "<the search query>"}}"""

INDIAN_LEGAL_EXTRACTION_PROMPT = """\
You are an Indian legal research analyst. Below are raw web-search results retrieved from \
official Indian regulatory sources for the user's request.

Request:
{request}

Search results:
{search_results}

Build a structured entry for each search result. Rules:
- Keep ONLY results whose content is genuinely about an Indian regulatory/legal topic \
relevant to the request. Drop off-topic or junk results.
- "title" and "source_url" MUST be copied verbatim from the result. Never rewrite or invent them.
- "document_type": one of act, regulation, rule, notification, circular, guideline, \
gazette, policy, judgment, license, standard, other — ONLY if the result explicitly \
indicates it; otherwise null.
- "jurisdiction": "India" (or "India (central)" / "India (state)" when supported) — ONLY \
if the result supports it; otherwise null.
- "publication_date": ONLY if the result provides one; otherwise null.
- "effective_date": ONLY if the result explicitly states a date on which the law applies \
or comes into force (phrases like "effective from", "comes into force on", "with effect \
from"). NEVER derive it from the publication date. Otherwise null.
- "relevant_sections": only section numbers / rules / clauses explicitly named in the \
content; empty array otherwise.
- "citation": only an explicit official citation present in the content; null otherwise.
- "summary": 1-2 sentence plain-language explanation of what the source means for a business.

Return ONLY valid JSON: {{"results": [{{"title", "source_url", "document_type", "jurisdiction", \
"publication_date", "effective_date", "relevant_sections": [], "citation", "summary"}}]}}"""

# ── indian_case_search ──────────────────────────────────────

INDIAN_CASE_QUERY_PROMPT = """\
You are an Indian legal research assistant. Build a single query for the Indian Kanoon \
case database (which indexes Supreme Court of India and High Court judgments, tribunal \
and commission orders).

User's request:
{request}

Conversation so far:
{transcript}

Rules:
- One concise query, 5-12 words. Name the parties OR the legal topic/act (e.g. "landlord \
tenant eviction madras high court", "TDS section 194C interpretation").
- Search INDIAN case law only. Do NOT answer the request. Only produce the query.

Return ONLY valid JSON: {{"query": "<the query>"}}"""

# ── legal_issue_register ────────────────────────────────────

INDIAN_ISSUE_REGISTER_PROMPT = """\
You are an Indian regulatory-compliance analyst. Identify and prioritize legal/regulatory \
issues for the user's business and prepare a compliance issue register.

Business context:
{context}

Conversation so far:
{transcript}

Retrieved sources (URLs actually retrieved earlier in this conversation; may be an empty list):
{available_sources}

User's request:
{request}

Return a JSON object with an "issues" array. Each issue:
- "title": short issue name (e.g. "FSSAI licence not obtained").
- "category": compliance topic (e.g. "food safety", "goods & services tax", "labour law").
- "basis": one of "source" (grounded in a retrieved source URL), "user_concern" (raised \
directly by the user), or "inference" (a reasonable inference, NOT backed by a retrieved source).
- "grounded_in": array of source URLs from the retrieved list that support this issue. \
Empty for user_concern and inference.
- "explanation": why it matters for this specific business.
- "mitigation": a practical next step (registration, licence, filing, compliance \
check). Do NOT propose litigation or demand payment of fines.
- "likelihood", "severity", "urgency": each an integer 1-5.

Rules:
- If "basis" is "source", "grounded_in" MUST contain at least one URL that is actually in \
the retrieved list — never invent URLs.
- Never fabricate Indian laws. If a legal claim is not backed by a retrieved source or the \
user, mark it "inference".
- Only Indian jurisdiction.
Return ONLY valid JSON: {{"issues": [...]}}"""

INDIAN_LEGAL_QUERY_TEMPLATE = ChatPromptTemplate.from_messages(
    [("human", INDIAN_LEGAL_QUERY_PROMPT)]
)
INDIAN_LEGAL_EXTRACTION_TEMPLATE = ChatPromptTemplate.from_messages(
    [("human", INDIAN_LEGAL_EXTRACTION_PROMPT)]
)
INDIAN_CASE_QUERY_TEMPLATE = ChatPromptTemplate.from_messages(
    [("human", INDIAN_CASE_QUERY_PROMPT)]
)
INDIAN_ISSUE_REGISTER_TEMPLATE = ChatPromptTemplate.from_messages(
    [("human", INDIAN_ISSUE_REGISTER_PROMPT)]
)
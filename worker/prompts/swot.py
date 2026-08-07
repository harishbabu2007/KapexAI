from langchain_core.prompts import ChatPromptTemplate

SWOT_PROMPT = """\
You are a business strategy analyst. Build a SWOT analysis for the user's business.

Known business context:
{context}

User's request:
{request}

Use the business context when available; otherwise work from the request alone. Be specific and practical.

Return ONLY valid JSON with this exact shape, nothing else:
{{"summary": "<one-line takeaway>", "sections": {{"strengths": ["..."], "weaknesses": ["..."], "opportunities": ["..."], "threats": ["..."]}}}}
Each list must contain 3-5 concise items."""

SWOT_TEMPLATE = ChatPromptTemplate.from_messages(
    [("human", SWOT_PROMPT)]
)

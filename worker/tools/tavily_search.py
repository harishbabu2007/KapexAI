from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.tools import tool


@tool
def tavily_search(query: str) -> str:
    """Searches the web with Tavily and returns the top results."""
    results = TavilySearchResults(max_results=3).invoke(query)
    return "\n\n".join(
        f"[{r.get('title', 'No title')}]\n{r.get('content', '')}"
        for r in results
    )

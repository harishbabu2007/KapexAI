from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from langchain_mistralai import ChatMistralAI
from langgraph.prebuilt import create_react_agent

from worker.prompts.research_websearch import RESEARCH_WEBSEARCH_PROMPT
from worker.tools.base import Tool
from worker.tools.tavily_search import tavily_search


class WebSearchTool(Tool):
    name = "web_search"
    description = "Perform live web research on a topic, competitor, market, or any question using internet search."
    example = "Search for my top 3 competitors in Pune"
    suggestion = "Wanna do a web search on your top competitors?"

    def __init__(self) -> None:
        self.llm = ChatMistralAI(model="mistral-small-2506", temperature=0)
        self.agent = create_react_agent(
            self.llm, [tavily_search], prompt=RESEARCH_WEBSEARCH_PROMPT
        )

    def run(self, state: dict) -> list[dict]:
        prompt = str(state.get("user_input") or "")
        result = self.agent.invoke({"messages": [("human", prompt)]})
        content = result["messages"][-1].content
        return [
            {
                "role": "USER",
                "agent": "TOOL",
                "type": "research_request",
                "content": prompt,
            },
            {
                "role": "ASSISTANT",
                "agent": "TOOL",
                "type": "research",
                "content": content,
            },
        ]

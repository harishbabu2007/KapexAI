import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from langchain_mistralai import ChatMistralAI

from worker.helpers.json_utils import parse_json
from worker.helpers.messages import format_transcript
from worker.prompts.router import ROUTER_TEMPLATE


class RouterAgent:
    def __init__(self) -> None:
        self.llm = ChatMistralAI(model="mistral-small-2506", temperature=0)

    async def classify(
        self, user_input: str, messages: list[dict], tools: list[dict]
    ) -> dict:
        chain = ROUTER_TEMPLATE | self.llm
        response = await chain.ainvoke(
            {
                "user_input": user_input,
                "transcript": format_transcript(messages),
                "tools": json.dumps(tools, indent=2),
            }
        )
        data = parse_json(response.content)
        if not isinstance(data, dict):
            raise TypeError(f"Expected a JSON object from router: {response.content}")
        return data

"""Manual script: smoke-test tool calling without LangGraph."""

import asyncio

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from app.agents.finance.react_loop import run_tool_calling_turn
from app.core.llm import get_llm


@tool
def dummy_tool(query: str) -> str:
    """Returns a dummy number."""
    return "The balance is 500000 VND"


async def main() -> None:
    llm = get_llm()
    tools = [dummy_tool]
    messages: list = [HumanMessage(content="How much is my balance?")]
    await run_tool_calling_turn(llm, tools, messages)
    print("MESSAGES:")
    for msg in messages:
        print(f"[{msg.type}] {msg.content}")


if __name__ == "__main__":
    asyncio.run(main())

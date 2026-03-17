from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool
import asyncio

@tool
def dummy_tool(query: str) -> str:
    """Returns a dummy number."""
    return "The balance is 500000 VND"

async def main():
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0)
    # create_react_agent might need explicit force
    agent = create_react_agent(llm.bind_tools([dummy_tool], tool_choice="any"), tools=[dummy_tool])
    
    result = await agent.ainvoke({"messages": [{"role": "user", "content": "How much is my balance?"}]})
    print("MESSAGES:")
    for msg in result["messages"]:
        print(f"[{msg.type}] {msg.content}")

if __name__ == "__main__":
    asyncio.run(main())

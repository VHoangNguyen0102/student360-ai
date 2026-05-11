
import asyncio
import os
import sys

# Add app to path
sys.path.append(os.getcwd())

from app.core.llm.providers.gemini import build_gemini_chat_model
from langchain_core.messages import HumanMessage

async def test():
    # Use a safe model name for Gemini API
    os.environ["GEMINI_LLM_MODEL"] = "gemini-1.5-flash"
    try:
        model = build_gemini_chat_model()
        print(f"Testing Gemini with key...")
        res = await model.ainvoke([HumanMessage(content="Hi")])
        print(f"Success: {res.content}")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test())

import asyncio
from app.agents.finance.agent import get_finance_agent
from langchain_core.messages import HumanMessage
from app.config import settings
import structlog

async def main():
    agent = get_finance_agent()
    config = {"configurable": {"thread_id": "test-123", "user_id": "f80eaa47-c546-4874-937c-6af2a27791ab"}}
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content="Cho tôi xem thống kê tổng thu nhập, tổng chi tiêu và dòng tiền ròng của lọ enjoyment từ trước đến nay")]},
        config=config
    )
    for m in result['messages']:
        print(f"[{type(m).__name__}] {getattr(m, 'content', '')} | tool_calls: {getattr(m, 'tool_calls', '')}")
        if hasattr(m, 'response_metadata') and m.response_metadata:
            print(f"  metadata: {m.response_metadata}")

if __name__ == "__main__":
    asyncio.run(main())

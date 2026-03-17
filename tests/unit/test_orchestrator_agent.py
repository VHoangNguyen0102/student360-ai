import pytest
from langchain_core.messages import HumanMessage

from app.agents.orchestrator.agent import get_orchestrator_agent
from app.models.chat import ContextHint


@pytest.mark.asyncio
async def test_orchestrator_dispatches_to_placeholder_career():
    agent = get_orchestrator_agent()

    result = await agent.ainvoke(
        {
            "messages": [HumanMessage(content="Giúp mình viết CV")],
            "session_id": "s1",
            "user_id": "u1",
            "context_hint": ContextHint.CAREER,
        },
        config={"configurable": {"thread_id": "s1", "user_id": "u1"}},
    )

    assert result.get("agent_used") == ["career"]
    messages = result.get("messages") or []
    assert messages, "Expected at least one message"
    assert "nghề nghiệp" in (messages[-1].content or "").lower()

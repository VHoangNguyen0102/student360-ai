"""
Finance Agent — Phase 1 LangGraph ReAct agent.
Handles 6-Jars chat with automatic tool calling and conversation memory.
"""
from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from app.agents.finance.prompts import get_finance_system_prompt
from app.agents.finance.tools.jars import ALL_JARS_TOOLS
from app.core.llm import get_llm
from app.core.memory import get_checkpointer

# Module-level singleton (lazy init so tests can import without real credentials)
_finance_agent = None


def get_finance_agent():
    """Return the shared Finance ReAct agent instance (created on first call)."""
    global _finance_agent
    if _finance_agent is None:
        llm = get_llm()
        checkpointer = get_checkpointer()
        _finance_agent = create_react_agent(
            model=llm,
            tools=ALL_JARS_TOOLS,
            checkpointer=checkpointer,
            prompt=get_finance_system_prompt(),
        )
    return _finance_agent


"""
Finance Agent — tool-calling chat with in-process session memory.
"""

from __future__ import annotations

from typing import Any

import structlog
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from app.agents.finance.composition import get_finance_system_prompt, get_finance_tools
from app.agents.finance.react_loop import run_tool_calling_turn
from app.core.chat_session_store import run_finance_turn
from app.core.llm import get_llm

logger = structlog.get_logger()

_finance_agent: FinanceToolAgent | None = None


class FinanceToolAgent:
    """LangGraph-free ReAct-style agent with thread-local message history."""

    async def ainvoke(self, input: dict[str, Any], config: RunnableConfig | None = None) -> dict[str, Any]:
        cfg = config or {}
        configurable = (cfg.get("configurable") or {}) if isinstance(cfg, dict) else {}
        thread_id = str(configurable.get("thread_id") or "default")
        user_id = str(configurable.get("user_id") or "")

        incoming: list[BaseMessage] = list(input.get("messages") or [])
        if not incoming:
            return {"messages": [HumanMessage(content="")]}

        tool_cfg: RunnableConfig = {
            "configurable": {
                "thread_id": thread_id,
                "user_id": user_id,
            }
        }
        llm = get_llm()

        tools = get_finance_tools()

        async def _run(hist: list[BaseMessage], tc: RunnableConfig) -> None:
            await run_tool_calling_turn(llm, tools, hist, tool_config=tc)

        tail = await run_finance_turn(
            thread_id,
            incoming,
            get_finance_system_prompt(),
            _run,
            tool_cfg,
        )

        logger.debug("finance_turn_done", thread_id=thread_id, new_messages=len(tail))
        return {"messages": tail}


def get_finance_agent() -> FinanceToolAgent:
    global _finance_agent
    if _finance_agent is None:
        _finance_agent = FinanceToolAgent()
    return _finance_agent

"""
Finance Agent — tool-calling chat with in-process session memory.
Upgraded with intent classification and policy gate for 6 Jars knowledge support.
"""

from __future__ import annotations

from typing import Any

import structlog
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from app.domains.finance.agents.finance.composition import get_finance_tools
from app.domains.finance.agents.finance.react_loop import run_tool_calling_turn
from app.domains.finance.agents.finance.scholarships.prompts import get_scholarship_system_prompt
from app.domains.finance.agents.finance.six_jars.intent_classifier import classify_intent
from app.domains.finance.agents.finance.six_jars.policy_gate import get_tools_for_intent
from app.domains.finance.agents.finance.six_jars.prompts_agent import (
    get_finance_system_prompt,
    get_hybrid_system_prompt,
    get_knowledge_system_prompt,
    get_personal_system_prompt,
)
from app.core.chat_session_store import run_finance_turn
from app.core.llm import get_llm

logger = structlog.get_logger()

_finance_agent: FinanceToolAgent | None = None

# Map intent → answer_mode label (for response metadata)
_INTENT_TO_MODE: dict[str, str] = {
    "knowledge_6jars": "knowledge",
    "personal_finance": "personal",
    "hybrid": "hybrid",
}


def _select_system_prompt(intent: str) -> str:
    """Return the appropriate system prompt based on classified intent."""
    return get_scholarship_system_prompt()
    if intent == "knowledge_6jars":
        return get_knowledge_system_prompt()
    if intent == "personal_finance":
        return get_personal_system_prompt()
    if intent == "hybrid":
        return get_hybrid_system_prompt()
    # Fallback: use the full base prompt for unknown intents
    return get_finance_system_prompt()


class FinanceToolAgent:
    """LangGraph-free ReAct-style agent with thread-local message history.

    Now supports:
    - Intent classification (knowledge_6jars | personal_finance | hybrid)
    - Policy gate: no tool calls for knowledge-only questions
    - Mode-specific system prompts for better answers
    """

    async def ainvoke(self, input: dict[str, Any], config: RunnableConfig | None = None) -> dict[str, Any]:
        cfg = config or {}
        configurable = (cfg.get("configurable") or {}) if isinstance(cfg, dict) else {}
        thread_id = str(configurable.get("thread_id") or "default")
        user_id = str(configurable.get("user_id") or "")

        incoming: list[BaseMessage] = list(input.get("messages") or [])
        if not incoming:
            return {"messages": [HumanMessage(content="")], "intent": "hybrid", "answer_mode": "hybrid"}

        # ── Step 1: Classify intent ──────────────────────────────────────────
        last_human = next(
            (m for m in reversed(incoming) if getattr(m, "type", None) == "human"),
            incoming[-1],
        )
        message_text = str(getattr(last_human, "content", "") or "")

        intent_result = await classify_intent(message_text)
        intent = intent_result.intent
        answer_mode = _INTENT_TO_MODE.get(intent, "hybrid")

        logger.info(
            "finance_agent_intent",
            intent=intent,
            answer_mode=answer_mode,
            confidence=intent_result.confidence,
            route_reason=intent_result.route_reason,
            thread_id=thread_id,
            user_id=user_id,
        )

        # ── Step 2: Select system prompt + tools via policy gate ─────────────
        system_prompt = _select_system_prompt(intent)
        tools = get_tools_for_intent(intent)

        logger.info(
            "finance_agent_policy",
            intent=intent,
            tools_allowed=len(tools),
            tool_names=[t.name for t in tools] if tools else [],
            thread_id=thread_id,
        )

        # ── Step 3: Execute tool-calling loop ────────────────────────────────
        tool_cfg: RunnableConfig = {
            "configurable": {
                "thread_id": thread_id,
                "user_id": user_id,
            }
        }
        llm = get_llm()

        async def _run(hist: list[BaseMessage], tc: RunnableConfig) -> None:
            await run_tool_calling_turn(llm, tools, hist, tool_config=tc)

        tail = await run_finance_turn(
            thread_id,
            incoming,
            system_prompt,
            _run,
            tool_cfg,
        )

        logger.debug(
            "finance_turn_done",
            thread_id=thread_id,
            new_messages=len(tail),
            intent=intent,
            answer_mode=answer_mode,
        )

        return {
            "messages": tail,
            "intent": intent,
            "answer_mode": answer_mode,
        }


def get_finance_agent() -> FinanceToolAgent:
    global _finance_agent
    if _finance_agent is None:
        _finance_agent = FinanceToolAgent()
    return _finance_agent


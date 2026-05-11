"""
Finance Agent — tool-calling chat with in-process session memory.
Upgraded with intent classification and policy gate for 6 Jars knowledge support.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import structlog
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.domains.finance.agents.finance.composition import get_finance_tools
# from app.domains.finance.agents.finance.react_loop import run_tool_calling_turn
from app.domains.finance.agents.finance.scholarships.prompts import get_scholarship_system_prompt
from app.domains.finance.agents.finance.react_loop import (
    run_tool_calling_turn,
    run_tool_calling_turn_stream,
)
from app.domains.finance.agents.finance.six_jars.intent_classifier import classify_intent
from app.domains.finance.agents.finance.six_jars.policy_gate import get_tools_for_intent
from app.domains.finance.agents.finance.six_jars.prompts_agent import (
    get_finance_system_prompt,
    get_hybrid_system_prompt,
    get_knowledge_system_prompt,
    get_personal_system_prompt,
)
from app.core.chat_session_store import (
    _master_lock,
    _sessions,
    _thread_locks,
    _trim_history,
    run_finance_turn,
)
from app.core.llm import get_llm

logger = structlog.get_logger()

_finance_agent: FinanceToolAgent | None = None

# Map intent → answer_mode label (for response metadata)
_INTENT_TO_MODE: dict[str, str] = {
    "knowledge_6jars": "knowledge",
    "personal_finance": "personal",
    "hybrid": "hybrid",
}

# Per-thread last-known intent for follow-up inheritance
_thread_last_intent: dict[str, str] = {}

# Short follow-up threshold: messages under this length without clear new intent signals
# will inherit the previous turn's intent if it was personal/hybrid
_SHORT_FOLLOWUP_MAX_LEN = 40


def _select_system_prompt(intent: str) -> str:
    """Return the appropriate system prompt based on classified intent."""
    return get_scholarship_system_prompt()
    if intent == "knowledge_6jars":
        return get_knowledge_system_prompt()
    if intent == "personal_finance":
        return get_personal_system_prompt()
    if intent == "hybrid":
        return get_hybrid_system_prompt()
    return get_finance_system_prompt()


async def _resolve_intent(message_text: str, thread_id: str) -> tuple[str, float, str]:
    """Classify intent with short follow-up inheritance from previous turn."""
    prev_intent = _thread_last_intent.get(thread_id)

    # For very short follow-ups after a personal/hybrid turn, inherit the previous intent
    # to avoid misclassifying "Còn lọ kia thì sao?" as knowledge_6jars
    if (
        prev_intent in ("personal_finance", "hybrid")
        and len(message_text.strip()) <= _SHORT_FOLLOWUP_MAX_LEN
    ):
        intent_result = await classify_intent(message_text)
        # Only override if classifier returns knowledge for a short follow-up
        if intent_result.intent == "knowledge_6jars" and intent_result.confidence < 0.85:
            logger.info(
                "intent_inherited_from_prev_turn",
                original_intent=intent_result.intent,
                inherited_intent=prev_intent,
                confidence=intent_result.confidence,
                thread_id=thread_id,
            )
            return prev_intent, intent_result.confidence, f"inherited:{prev_intent}"
        return intent_result.intent, intent_result.confidence, intent_result.route_reason

    intent_result = await classify_intent(message_text)
    return intent_result.intent, intent_result.confidence, intent_result.route_reason


class FinanceToolAgent:
    """LangGraph-free ReAct-style agent with thread-local message history.

    Supports:
    - Intent classification (knowledge_6jars | personal_finance | hybrid)
    - Intent inheritance for short follow-up messages
    - Policy gate: knowledge tools only for knowledge intent, all tools for personal/hybrid
    - Mode-specific system prompts updated every turn
    """

    async def ainvoke(
        self,
        input: dict[str, Any],
        config: RunnableConfig | None = None,
        history: list[BaseMessage] | None = None,
    ) -> dict[str, Any]:
        cfg = config or {}
        configurable = (cfg.get("configurable") or {}) if isinstance(cfg, dict) else {}
        thread_id = str(configurable.get("thread_id") or "default")
        user_id = str(configurable.get("user_id") or "")

        incoming: list[BaseMessage] = list(input.get("messages") or [])
        if not incoming:
            return {"messages": [HumanMessage(content="")], "intent": "hybrid", "answer_mode": "hybrid"}

        # ── Step 1: Classify intent (with follow-up inheritance) ─────────────
        last_human = next(
            (m for m in reversed(incoming) if getattr(m, "type", None) == "human"),
            incoming[-1],
        )
        message_text = str(getattr(last_human, "content", "") or "")

        intent, confidence, route_reason = await _resolve_intent(message_text, thread_id)
        answer_mode = _INTENT_TO_MODE.get(intent, "hybrid")
        _thread_last_intent[thread_id] = intent

        logger.info(
            "finance_agent_intent",
            intent=intent,
            answer_mode=answer_mode,
            confidence=confidence,
            route_reason=route_reason,
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
        logger.info("tool_cfg", tool_cfg=tool_cfg)
        llm = get_llm()

        async def _run(hist: list[BaseMessage], tc: RunnableConfig) -> None:
            await run_tool_calling_turn(llm, tools, hist, tool_config=tc)

        tail = await run_finance_turn(
            thread_id,
            incoming,
            system_prompt,
            _run,
            tool_cfg,
            history=history,
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

    async def astream(
        self,
        input: dict[str, Any],
        config: RunnableConfig | None = None,
        history: list[BaseMessage] | None = None,
    ) -> AsyncIterator[tuple[str, str]]:
        """Streaming variant — yields (event_type, data) tuples.

        event_type values: "status" | "token"
        Callers append a "done" event with metadata after the generator exhausts.
        """
        cfg = config or {}
        configurable = (cfg.get("configurable") or {}) if isinstance(cfg, dict) else {}
        thread_id = str(configurable.get("thread_id") or "default")
        user_id = str(configurable.get("user_id") or "")

        incoming: list[BaseMessage] = list(input.get("messages") or [])
        if not incoming:
            return

        last_human = next(
            (m for m in reversed(incoming) if getattr(m, "type", None) == "human"),
            incoming[-1],
        )
        message_text = str(getattr(last_human, "content", "") or "")

        yield ("status", "Đang phân tích câu hỏi...")
        intent, confidence, route_reason = await _resolve_intent(message_text, thread_id)
        answer_mode = _INTENT_TO_MODE.get(intent, "hybrid")
        _thread_last_intent[thread_id] = intent

        logger.info(
            "finance_agent_stream_intent",
            intent=intent,
            answer_mode=answer_mode,
            confidence=confidence,
            route_reason=route_reason,
            thread_id=thread_id,
            user_id=user_id,
        )

        system_prompt = _select_system_prompt(intent)
        tools = get_tools_for_intent(intent)

        tool_cfg: RunnableConfig = {
            "configurable": {"thread_id": thread_id, "user_id": user_id}
        }
        llm = get_llm()

        # Acquire per-thread lock (same as run_finance_turn)
        async with _master_lock:
            if thread_id not in _thread_locks:
                _thread_locks[thread_id] = asyncio.Lock()
            lock = _thread_locks[thread_id]

        async with lock:
            hist = _sessions.setdefault(thread_id, [])
            if not hist:
                if history:
                    hist.extend(history)
                else:
                    hist.append(SystemMessage(content=system_prompt))
            else:
                # Update system prompt when intent changes between turns
                if hist and isinstance(hist[0], SystemMessage):
                    if hist[0].content != system_prompt:
                        hist[0] = SystemMessage(content=system_prompt)
            for m in incoming:
                hist.append(m)

            async for event in run_tool_calling_turn_stream(
                llm, tools, hist, tool_config=tool_cfg
            ):
                yield event

            _trim_history(hist)


def get_finance_agent() -> FinanceToolAgent:
    global _finance_agent
    if _finance_agent is None:
        _finance_agent = FinanceToolAgent()
    return _finance_agent


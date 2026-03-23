"""
Orchestrator — routes to specialist agents (no LangGraph).
"""

from __future__ import annotations

import structlog
from langchain_core.messages import AIMessage, BaseMessage

from app.agents.orchestrator.registry import get_specialist_agent
from app.agents.orchestrator.router import route_agent
from app.models.chat import ContextHint

logger = structlog.get_logger()

_orchestrator = None


def _last_human_message(messages: list[BaseMessage]) -> BaseMessage | None:
    for msg in reversed(messages or []):
        if getattr(msg, "type", None) == "human":
            return msg
    return None


async def _orchestrator_ainvoke(input: dict, config: dict | None = None) -> dict:
    messages: list[BaseMessage] = list(input.get("messages") or [])
    session_id = str(input.get("session_id") or "")
    user_id = str(input.get("user_id") or "")
    context_hint = input.get("context_hint", ContextHint.AUTO)
    if not isinstance(context_hint, ContextHint):
        context_hint = ContextHint.AUTO

    last_human = _last_human_message(messages)
    message_text = str(getattr(last_human, "content", "") if last_human else "")

    selected, route_reason = await route_agent(message_text, context_hint)
    logger.info(
        "orchestrator_route",
        selected_agent=selected,
        route_reason=route_reason,
        context_hint=str(context_hint),
        session_id=session_id,
        user_id=user_id,
    )

    if last_human is None:
        return {
            "messages": [AIMessage(content="Xin lỗi, mình chưa nhận được câu hỏi.")],
            "agent_used": [selected],
        }

    specialist = get_specialist_agent(selected)
    subthread_id = f"{session_id}:{selected}" if session_id else selected
    cfg = config or {}
    configurable = dict(cfg.get("configurable") or {})
    configurable.setdefault("thread_id", subthread_id)
    configurable.setdefault("user_id", user_id)
    merged_config = {**cfg, "configurable": configurable}

    logger.info(
        "orchestrator_dispatch",
        agent_id=selected,
        subthread_id=subthread_id,
        session_id=session_id,
        user_id=user_id,
        route_reason=route_reason,
    )

    result = await specialist.ainvoke({"messages": [last_human]}, config=merged_config)
    spec_messages = result.get("messages", []) if isinstance(result, dict) else []

    if spec_messages:
        first = spec_messages[0]
        if (
            getattr(first, "type", None) == "human"
            and getattr(first, "content", None) == getattr(last_human, "content", None)
        ):
            spec_messages = spec_messages[1:]

    if not spec_messages:
        spec_messages = [AIMessage(content="Xin lỗi, mình chưa thể xử lý yêu cầu lúc này.")]

    return {
        "messages": spec_messages,
        "agent_used": [selected],
    }


class _OrchestratorShim:
    __slots__ = ()

    async def ainvoke(self, input: dict, config: dict | None = None) -> dict:
        return await _orchestrator_ainvoke(input, config)


def get_orchestrator_agent() -> _OrchestratorShim:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = _OrchestratorShim()
    return _orchestrator

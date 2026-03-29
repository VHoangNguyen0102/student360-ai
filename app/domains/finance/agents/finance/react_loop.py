"""Manual tool-calling loop (replaces LangGraph create_react_agent)."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool


def _tool_call_id(tc: Any) -> str:
    if isinstance(tc, dict):
        return str(tc.get("id") or "")
    return str(getattr(tc, "id", None) or "")


def _tool_call_name(tc: Any) -> str:
    if isinstance(tc, dict):
        return str(tc.get("name") or "")
    return str(getattr(tc, "name", None) or "")


def _tool_call_args(tc: Any) -> dict[str, Any]:
    if isinstance(tc, dict):
        a = tc.get("args")
        if a is None and "arguments" in tc:
            a = tc.get("arguments")
        if isinstance(a, str):
            try:
                return json.loads(a)
            except json.JSONDecodeError:
                return {}
        return dict(a) if isinstance(a, dict) else {}
    args = getattr(tc, "args", None)
    return dict(args) if isinstance(args, dict) else {}


async def run_tool_calling_turn(
    llm: BaseChatModel,
    tools: list[BaseTool],
    messages: list[BaseMessage],
    *,
    tool_config: RunnableConfig | None = None,
    max_iterations: int = 15,
) -> list[BaseMessage]:
    """
    Appends model and tool messages to `messages` in place.
    Returns only the list of messages added during this turn.
    """
    llm_with_tools = llm.bind_tools(tools)
    tool_by_name = {t.name: t for t in tools}
    start_len = len(messages)

    cfg = tool_config or {}
    for _ in range(max_iterations):
        ai_msg = await llm_with_tools.ainvoke(messages, config=cfg)
        if not isinstance(ai_msg, AIMessage):
            ai_msg = AIMessage(content=str(getattr(ai_msg, "content", "")))
        messages.append(ai_msg)
        tcalls = getattr(ai_msg, "tool_calls", None) or []
        if not tcalls:
            break
        for tc in tcalls:
            name = _tool_call_name(tc)
            args = _tool_call_args(tc)
            tid = _tool_call_id(tc) or name
            tool_fn = tool_by_name.get(name)
            try:
                if tool_fn is None:
                    out: str = f"Unknown tool: {name}"
                else:
                    raw = await tool_fn.ainvoke(args, config=cfg)
                    if isinstance(raw, str):
                        out = raw
                    elif isinstance(raw, (dict, list)):
                        out = json.dumps(raw, ensure_ascii=False)
                    else:
                        out = str(raw)
            except Exception as exc:
                out = f"Tool error ({name}): {exc}"
            messages.append(ToolMessage(content=out, tool_call_id=tid))

    return messages[start_len:]

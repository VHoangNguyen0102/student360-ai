"""Manual tool-calling loop (replaces LangGraph create_react_agent)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

_TOOL_STATUS_VN: dict[str, str] = {
    "get_jar_balance": "Đang tra cứu số dư ví...",
    "get_jar_allocations": "Đang xem phân bổ các ví...",
    "get_jar_statistics": "Đang tổng hợp thống kê tài chính...",
    "get_recent_transactions": "Đang xem giao dịch gần đây...",
    "get_top_expenses": "Đang phân tích chi tiêu lớn nhất...",
    "search_transactions": "Đang tìm kiếm giao dịch...",
    "get_budget_status": "Đang kiểm tra ngân sách...",
    "get_monthly_summary": "Đang tổng hợp báo cáo tháng...",
    "compare_months": "Đang so sánh các tháng...",
    "get_spending_trend": "Đang phân tích xu hướng chi tiêu...",
    "get_auto_transfers": "Đang kiểm tra chuyển tiền tự động...",
    "can_afford_this": "Đang kiểm tra khả năng chi tiêu...",
}


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


def _scholarship_reply_hint(messages: list[BaseMessage]) -> str | None:
    for msg in reversed(messages):
        if not isinstance(msg, ToolMessage):
            continue
        content = getattr(msg, "content", None)
        if not isinstance(content, str):
            continue
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict) or not isinstance(data.get("scholarship_recommendations"), dict):
            continue
        hint = data.get("reply_hint")
        if isinstance(hint, str) and hint.strip():
            return hint.strip()
        return "Tôi đã tìm thấy một số học bổng phù hợp với bạn. Nhấn vào từng thẻ để xem tóm tắt."
    return None


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
            messages.append(ToolMessage(content=out, tool_call_id=tid, name=name))

    return messages[start_len:]


async def run_tool_calling_turn_stream(
    llm: BaseChatModel,
    tools: list[BaseTool],
    messages: list[BaseMessage],
    *,
    tool_config: RunnableConfig | None = None,
    max_iterations: int = 15,
) -> AsyncIterator[tuple[str, str]]:
    """
    Streaming variant of run_tool_calling_turn.

    Yields (event_type, data) tuples:
      - ("status", "Đang tra cứu số dư ví...") — during each tool call
      - ("token", "<text>")                     — streaming tokens of the final reply

    Mutates `messages` in place the same way as run_tool_calling_turn.
    """
    llm_with_tools = llm.bind_tools(tools) if tools else llm
    tool_by_name = {t.name: t for t in tools}
    cfg = tool_config or {}

    for _ in range(max_iterations):
        ai_msg = await llm_with_tools.ainvoke(messages, config=cfg)
        if not isinstance(ai_msg, AIMessage):
            ai_msg = AIMessage(content=str(getattr(ai_msg, "content", "")))
        messages.append(ai_msg)

        tcalls = getattr(ai_msg, "tool_calls", None) or []
        if not tcalls:
            # Final turn — we already have the full answer in ai_msg.content
            # from the ainvoke call. We try to re-stream it for the visual effect,
            # but we MUST have a fallback in case Vertex flaked on the second call.
            final_content = ai_msg.content or ""
            scholarship_hint = _scholarship_reply_hint(messages)
            if scholarship_hint:
                messages[-1] = AIMessage(content=scholarship_hint)
                yield ("token", scholarship_hint)
                return
            messages.pop()
            
            full_content = ""
            try:
                async for chunk in llm.astream(messages, config=cfg):
                    text = chunk.content if isinstance(chunk.content, str) else ""
                    if text:
                        full_content += text
                        yield ("token", text)
                
                # If astream finished but yielded absolutely nothing (common flakiness)
                if not full_content and final_content:
                    yield ("token", final_content)
                    full_content = final_content
            except Exception as exc:
                # If astream failed (e.g. timeout or safety), fallback to our known answer
                if final_content:
                    yield ("token", final_content)
                    full_content = final_content
                else:
                    raise exc
            
            # Append the full message back to history
            messages.append(AIMessage(content=full_content))
            return

        # Tool-calling turn — emit status and execute each tool.
        for tc in tcalls:
            name = _tool_call_name(tc)
            args = _tool_call_args(tc)
            tid = _tool_call_id(tc) or name
            status = _TOOL_STATUS_VN.get(name, f"Đang xử lý {name}...")
            yield ("status", status)
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
            messages.append(ToolMessage(content=out, tool_call_id=tid, name=name))

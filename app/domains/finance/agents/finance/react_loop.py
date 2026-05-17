"""Manual tool-calling loop (replaces LangGraph create_react_agent)."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from app.domains.finance.models.action_proposal import ActionProposal, ActionType

_ACTION_SCHEMA_ADDON = """
PHẦN BỔ SUNG HỆ THỐNG (ẩn với user):
QUAN TRỌNG: Chỉ thêm block <ACTIONS> khi đây là câu trả lời CUỐI cho user
(không còn tool nào cần gọi thêm). KHÔNG thêm block này ở các bước reasoning
hoặc tool calling trung gian.

Nếu người dùng YÊU CẦU thực hiện hành động tài chính và số tiền đã rõ, thêm block <ACTIONS> VÀO CUỐI phản hồi.

Jar codes: Thiết yếu/Sinh hoạt→essentials | Giáo dục→education | Đầu tư→investment | Hưởng thụ→enjoyment | Dự phòng/Tiết kiệm→reserve | Chia sẻ→sharing

Ví dụ block hợp lệ (điền đúng giá trị từ yêu cầu của user, KHÔNG để trống):

Ví dụ 1 — phân bổ thu nhập + ghi chi:
<ACTIONS>
{"actions": [{"type": "DISTRIBUTE_INCOME", "title": "Phân bổ 10.000.000 VND", "description": "10.000.000 VND • 2026-05-12", "params": {"amount": 10000000, "description": "Thu nhập tháng 5", "transactionDate": "2026-05-12"}, "risk_level": "low"}, {"type": "CREATE_TRANSACTION", "title": "Chi 200.000 VND tiền điện", "description": "200.000 VND • essentials • 2026-05-12", "params": {"type": "EXPENSE", "amount": 200000, "description": "Tiền điện", "jarCode": "essentials", "transactionDate": "2026-05-12"}, "risk_level": "low"}]}
</ACTIONS>

Ví dụ 2 — nhiều giao dịch cùng lúc + chuyển lọ:
<ACTIONS>
{"actions": [{"type": "DISTRIBUTE_INCOME", "title": "Phân bổ 20.000.000 VND", "description": "20.000.000 VND • 2026-05-12", "params": {"amount": 20000000, "description": "Lương tháng 5", "transactionDate": "2026-05-12"}, "risk_level": "low"}, {"type": "CREATE_TRANSACTION", "title": "Chi 5.000.000 VND tiền nhà", "description": "5.000.000 VND • essentials • 2026-05-12", "params": {"type": "EXPENSE", "amount": 5000000, "description": "Tiền nhà", "jarCode": "essentials", "transactionDate": "2026-05-12"}, "risk_level": "low"}, {"type": "TRANSFER_BETWEEN_JARS", "title": "Chuyển 1.000.000 VND Hưởng thụ → Dự phòng", "description": "1.000.000 VND • enjoyment → reserve • 2026-05-12", "params": {"amount": 1000000, "sourceJarCode": "enjoyment", "targetJarCode": "reserve", "description": "Chuyển dư sang tiết kiệm", "transactionDate": "2026-05-12"}, "risk_level": "low"}]}
</ACTIONS>

Quy tắc params:
- CREATE_TRANSACTION: type (EXPENSE/INCOME), amount (int VND), description, jarCode, transactionDate (YYYY-MM-DD)
- DISTRIBUTE_INCOME: amount (int), description, transactionDate
- TRANSFER_BETWEEN_JARS: amount (int), sourceJarCode, targetJarCode, description, transactionDate — LUÔN dùng type này khi user muốn chuyển tiền giữa 2 lọ, KHÔNG tạo 2 CREATE_TRANSACTION riêng

Ràng buộc: tối đa 5 action. Bỏ qua block nếu không có số tiền cụ thể.
"""


def _parse_action_response(text: str) -> tuple[str, list[ActionProposal]]:
    """Extract <ACTIONS> block from text, parse into ActionProposal list.

    Returns (clean_text, actions). Fallback: (original_text, []) on any parse error.
    """
    actions: list[ActionProposal] = []
    match = re.search(r"<ACTIONS>(.*?)</ACTIONS>", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1).strip())
            for item in (data.get("actions") or [])[:5]:
                try:
                    actions.append(
                        ActionProposal(
                            type=ActionType(str(item["type"]).upper()),
                            title=item.get("title", "Hành động đề xuất"),
                            description=item.get("description", ""),
                            params=item.get("params", {}),
                            risk_level=item.get("risk_level", "low"),
                        )
                    )
                except Exception:
                    pass
        except Exception:
            pass
    clean_text = re.sub(r"\s*<ACTIONS>.*?</ACTIONS>\s*", "", text, flags=re.DOTALL).strip()
    if clean_text:
        return clean_text, actions
    # Model generated only <ACTIONS> with no text — return empty so caller uses a default.
    if actions:
        return "", actions
    return text.strip(), []

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
        name = str(tc.get("name") or "")
    else:
        name = str(getattr(tc, "name", None) or "")
    # Gemini / VertexAI sometimes prefixes tool names with "default_api."
    # Strip any namespace prefix so lookups match the registered tool name.
    if "." in name:
        name = name.rsplit(".", 1)[-1]
    return name


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
    enable_actions: bool = False,
) -> list[BaseMessage]:
    """
    Appends model and tool messages to `messages` in place.
    Returns only the list of messages added during this turn.
    """
    llm_with_tools = llm.bind_tools(tools)
    tool_by_name = {t.name: t for t in tools}
    start_len = len(messages)
    cfg = tool_config or {}

    # Pre-inject action schema into system message for this loop only.
    # Restored in finally block so session history stays clean.
    _original_msg0: SystemMessage | None = None
    if enable_actions and messages and isinstance(messages[0], SystemMessage):
        _original_msg0 = messages[0]
        messages[0] = SystemMessage(content=messages[0].content + "\n\n" + _ACTION_SCHEMA_ADDON)

    async def _run_tool(tc: Any) -> tuple[str, str, str]:
        name = _tool_call_name(tc)
        args = _tool_call_args(tc)
        tid = _tool_call_id(tc) or name
        tool_fn = tool_by_name.get(name)
        try:
            if tool_fn is None:
                return tid, name, f"Unknown tool: {name}"
            raw = await tool_fn.ainvoke(args, config=cfg)
            if isinstance(raw, str):
                out: str = raw
            elif isinstance(raw, (dict, list)):
                out = json.dumps(raw, ensure_ascii=False)
            else:
                out = str(raw)
        except Exception as exc:
            out = f"Tool error ({name}): {exc}"
        return tid, name, out

    try:
        for _ in range(max_iterations):
            ai_msg = await llm_with_tools.ainvoke(messages, config=cfg)
            if not isinstance(ai_msg, AIMessage):
                ai_msg = AIMessage(content=str(getattr(ai_msg, "content", "")))
            messages.append(ai_msg)
            tcalls = getattr(ai_msg, "tool_calls", None) or []
            if not tcalls:
                break

            # Execute all tool calls in parallel
            results = await asyncio.gather(*[_run_tool(tc) for tc in tcalls])
            for tid, name, out in results:
                messages.append(ToolMessage(content=out, tool_call_id=tid, name=name))
    finally:
        if _original_msg0 is not None:
            messages[0] = _original_msg0

    return messages[start_len:]


async def run_tool_calling_turn_stream(
    llm: BaseChatModel,
    tools: list[BaseTool],
    messages: list[BaseMessage],
    *,
    tool_config: RunnableConfig | None = None,
    max_iterations: int = 15,
    enable_actions: bool = False,
) -> AsyncIterator[tuple[str, str]]:
    """
    Streaming variant of run_tool_calling_turn.

    Yields (event_type, data) tuples:
      - ("status", "Đang tra cứu số dư ví...") — during each tool call
      - ("token", "<text>")                     — streaming tokens of the final reply
      - ("actions", "<json>")                   — action proposals (when enable_actions=True)

    Mutates `messages` in place the same way as run_tool_calling_turn.
    """
    llm_with_tools = llm.bind_tools(tools) if tools else llm
    tool_by_name = {t.name: t for t in tools}
    cfg = tool_config or {}

    # Pre-inject action schema into system message for this loop only.
    # Using try/finally to restore the original even if the generator is abandoned.
    _original_msg0: SystemMessage | None = None
    if enable_actions and messages and isinstance(messages[0], SystemMessage):
        _original_msg0 = messages[0]
        messages[0] = SystemMessage(content=messages[0].content + "\n\n" + _ACTION_SCHEMA_ADDON)

    async def _run_tool(tc: Any) -> tuple[str, str, str]:
        name = _tool_call_name(tc)
        args = _tool_call_args(tc)
        tid = _tool_call_id(tc) or name
        tool_fn = tool_by_name.get(name)
        try:
            if tool_fn is None:
                return tid, name, f"Unknown tool: {name}"
            raw = await tool_fn.ainvoke(args, config=cfg)
            if isinstance(raw, str):
                out: str = raw
            elif isinstance(raw, (dict, list)):
                out = json.dumps(raw, ensure_ascii=False)
            else:
                out = str(raw)
        except Exception as exc:
            out = f"Tool error ({name}): {exc}"
        return tid, name, out

    try:
        for _ in range(max_iterations):
            ai_msg = await llm_with_tools.ainvoke(messages, config=cfg)
            if not isinstance(ai_msg, AIMessage):
                ai_msg = AIMessage(content=str(getattr(ai_msg, "content", "")))
            messages.append(ai_msg)

            tcalls = getattr(ai_msg, "tool_calls", None) or []
            if not tcalls:
                # Final turn — ai_msg already has the complete answer (with <ACTIONS> if injected).
                final_content = str(ai_msg.content or "")
                messages.pop()

                if enable_actions:
                    # Schema was pre-injected: parse actions directly from this call's output.
                    # No second ainvoke() needed — saves ~3s per request.
                    reply_text, actions = _parse_action_response(final_content)
                    if not reply_text:
                        reply_text = "Tôi sẽ thực hiện các hành động sau cho bạn, vui lòng xác nhận:" if actions else final_content
                    if actions:
                        yield ("actions", json.dumps([a.model_dump() for a in actions], ensure_ascii=False))
                    yield ("token", reply_text)
                    messages.append(AIMessage(content=reply_text))
                    return

                # enable_actions=False: re-stream for visual token-by-token effect.
                full_content = ""
                try:
                    async for chunk in llm.astream(messages, config=cfg):
                        text = chunk.content if isinstance(chunk.content, str) else ""
                        if text:
                            full_content += text
                            yield ("token", text)

                    if not full_content and final_content:
                        yield ("token", final_content)
                        full_content = final_content
                except Exception as exc:
                    if final_content:
                        yield ("token", final_content)
                        full_content = final_content
                    else:
                        raise exc

                messages.append(AIMessage(content=full_content))
                return

            # Tool-calling turn — emit all status messages first (non-blocking),
            # then execute all tool calls in parallel via asyncio.gather().
            for tc in tcalls:
                name = _tool_call_name(tc)
                status = _TOOL_STATUS_VN.get(name, f"Đang xử lý {name}...")
                yield ("status", status)

            results = await asyncio.gather(*[_run_tool(tc) for tc in tcalls])
            for tid, name, out in results:
                messages.append(ToolMessage(content=out, tool_call_id=tid, name=name))
    finally:
        if _original_msg0 is not None:
            messages[0] = _original_msg0

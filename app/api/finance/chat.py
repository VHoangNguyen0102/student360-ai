"""Chat API — POST /api/v1/chat

Directly routes to the in-process Finance agent.

By default it uses the 6-Jars prompt/tools, but you can switch to scholarships
via env `FINANCE_AGENT_MODE=scholarships` (see `app/domains/finance/agents/finance/composition.py`).
Multi-agent orchestration is kept as optional scaffold and is not used at runtime.
"""
from __future__ import annotations

import json
import time
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import HumanMessage

from app.domains.finance.agents.finance.agent import get_finance_agent
from app.domains.finance.models.chat import ChatRequest, ChatResponse, ChatUsage
from app.utils.auth import verify_service_token

logger = structlog.get_logger()
router = APIRouter()


def _format_vnd(amount: object) -> str:
    try:
        if amount is None:
            return "0 VND"
        value_int = int(round(float(amount)))
        return f"{value_int:,}".replace(",", ".") + " VND"
    except Exception:
        return f"{amount} VND"


def _extract_json_obj(text: object) -> dict | None:
    if not isinstance(text, str):
        return None
    s = text.strip()
    if not s:
        return None

    # Common case: raw JSON
    if s.startswith("{") and s.endswith("}"):
        try:
            obj = json.loads(s)
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None

    # Tool outputs like: "Record 1:\n{ ...json... }"
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            obj = json.loads(s[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None
    return None


def _tool_call_name(tool_call: object) -> str | None:
    if tool_call is None:
        return None
    if isinstance(tool_call, dict):
        return tool_call.get("name") or tool_call.get("tool")

    name = getattr(tool_call, "name", None)
    if isinstance(name, str) and name:
        return name

    getter = getattr(tool_call, "get", None)
    if callable(getter):
        try:
            name = getter("name") or getter("tool")
            if isinstance(name, str) and name:
                return name
        except Exception:
            pass

    return None


def _synthesise_reply_from_tools(messages: list) -> str | None:
    """Fallback when the final AI message is empty.

    Gemini tool-calling can sometimes yield an empty final assistant turn.
    When that happens, synthesise a minimal, user-friendly answer
    from the last tool output (special-cased for get_jar_statistics).
    """
    last_tool_content = None
    for msg in reversed(messages):
        if getattr(msg, "type", None) == "tool":
            last_tool_content = getattr(msg, "content", None)
            break

    tool_name = None
    for msg in reversed(messages):
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            tool_name = _tool_call_name(tool_calls[-1])
            break

    data = _extract_json_obj(last_tool_content)
    if not data:
        if isinstance(last_tool_content, str) and last_tool_content.strip():
            return last_tool_content.strip()
        return None

    if isinstance(data.get("error"), str) and data.get("error"):
        return data["error"]

    jar_code = data.get("jar_code")
    jar_name = data.get("name")
    income = data.get("accumulated_income")
    expense = data.get("accumulated_expense")
    net_flow = data.get("net_flow")
    balance = data.get("current_balance")

    # Common fallback for balance lookups.
    if tool_name == "get_jar_balance" and (jar_code is not None or jar_name is not None):
        jar_label = jar_name or jar_code or ""
        reply = f"Số dư lọ {jar_label} hiện tại là {_format_vnd(balance)}."
        if data.get("percentage") is not None:
            reply += f" Tỷ lệ phân bổ: {data.get('percentage')}%."
        return reply

    # Field-based detection: only synthesize if this looks like jar statistics.
    if income is None or expense is None or (jar_code is None and jar_name is None):
        # Generic JSON fallback so users still get useful output
        # when the model returns an empty final message.
        return json.dumps(data, ensure_ascii=False)

    header = "Thống kê" + (f" lọ {jar_name}" if jar_name else "")
    if jar_code:
        header += f" ({jar_code})"
    header += " từ trước đến nay:"

    parts = [
        header,
        f"- Tổng thu: {_format_vnd(income)}",
        f"- Tổng chi: {_format_vnd(expense)}",
    ]
    if net_flow is not None:
        parts.append(f"- Dòng tiền ròng (thu - chi): {_format_vnd(net_flow)}")
    if balance is not None:
        parts.append(f"- Số dư hiện tại: {_format_vnd(balance)}")
    return "\n".join(parts)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    _: str = Depends(verify_service_token),
) -> ChatResponse:
    """Multi-turn chat with Finance agent."""
    session_id = req.session_id or str(uuid.uuid4())
    agent = get_finance_agent()

    config = {
        "configurable": {
            "thread_id": session_id,
            "user_id": req.user_id,
        }
    }

    start = time.monotonic()
    try:
        result = await agent.ainvoke(
            {
                "messages": [HumanMessage(content=req.message)],
            },
            config=config,
        )
    except Exception as exc:
        logger.error("agent_invoke_failed", error=str(exc), user_id=req.user_id)
        err = str(exc)
        if "RESOURCE_EXHAUSTED" in err or "429" in err:
            raise HTTPException(
                status_code=429,
                detail="Gemini API quota exhausted (RESOURCE_EXHAUSTED). Please retry later.",
            ) from exc
        raise HTTPException(status_code=500, detail="AI agent error") from exc

    latency_ms = int((time.monotonic() - start) * 1000)

    # Last message in the graph output is the final AI reply
    messages = result.get("messages", [])
    if not messages:
        raise HTTPException(status_code=500, detail="Agent returned no messages")

    # Logging tool usage and debug
    for msg in messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                tool_name = _tool_call_name(tc)
                if isinstance(tc, dict):
                    args = tc.get("args")
                else:
                    args = getattr(tc, "args", None)
                logger.info("tool_used", tool=tool_name, args=args, user_id=req.user_id)
        logger.info("debug_message", type=msg.type, content_len=len(str(msg.content)), content_preview=str(msg.content)[:100])

    reply = messages[-1].content
    if isinstance(reply, list):
        reply = " ".join([str(block.get("text", "")) for block in reply if isinstance(block, dict) and "text" in block])
    elif not isinstance(reply, str):
        reply = str(reply)

    if not reply or not reply.strip():
        reply = _synthesise_reply_from_tools(messages) or "Xin lỗi, tôi chưa thể tổng hợp kết quả. Vui lòng thử lại."

    # Extract token usage from the last AI message if available
    usage_meta = getattr(messages[-1], "usage_metadata", None)
    usage = None
    if usage_meta:
        usage = ChatUsage(
            tokens_in=usage_meta.get("input_tokens", 0),
            tokens_out=usage_meta.get("output_tokens", 0),
            latency_ms=latency_ms,
        )

    # Finance agent may not populate agent_used; keep response stable.
    agent_used = result.get("agent_used")
    if not isinstance(agent_used, list) or not agent_used:
        agent_used = ["finance"]

    return ChatResponse(
        reply=reply,
        session_id=session_id,
        agent_used=agent_used,
        usage=usage,
    )


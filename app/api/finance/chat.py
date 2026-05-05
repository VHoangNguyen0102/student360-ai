"""
Chat API — POST /api/v1/chat
Directly routes to FinanceAgent (6-Jars context).
Multi-agent orchestration is kept as optional scaffold and is not used at runtime.
"""
from __future__ import annotations

import json
import time
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse, ServerSentEvent
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from app.domains.finance.agents.finance.agent import get_finance_agent
from app.core.llm.runtime_model import llm_model_override
from app.core.llm.runtime_provider import llm_provider_override
from app.config import settings
from app.domains.finance.models.chat import ChatRequest, ChatResponse, ChatUsage
from app.utils.auth import verify_service_token

logger = structlog.get_logger()
router = APIRouter()


def _build_provider_plan(provider_override: str | None) -> list[str]:
    """Build ordered provider attempts, prioritizing requested/default provider first."""
    first = provider_override or settings.LLM_PROVIDER
    if not settings.AI_PROVIDER_FALLBACK_ENABLED:
        return [first] if first in {"vertexai", "gemini", "ollama"} else [settings.LLM_PROVIDER]

    candidates = [first, "vertexai", "gemini", "ollama"]
    seen: set[str] = set()
    ordered: list[str] = []
    for p in candidates:
        if p not in {"vertexai", "gemini", "ollama"}:
            continue
        if p in seen:
            continue
        seen.add(p)
        ordered.append(p)
    return ordered


def _is_retryable_provider_error(error_text: str) -> bool:
    lowered = (error_text or "").lower()
    signals = (
        "resource_exhausted",
        "429",
        "quota",
        "all connection attempts failed",
        "server disconnected without sending a response",
        "name or service not known",
        "connection refused",
        "timed out",
        "temporary failure in name resolution",
    )
    return any(signal in lowered for signal in signals)


def _resolve_model_name(provider: str, model_override: str | None = None) -> str:
    if model_override and model_override.strip():
        return model_override.strip()
    if provider == "ollama":
        return settings.OLLAMA_MODEL
    if provider == "vertexai":
        return settings.VERTEX_LLM_MODEL
    return settings.GEMINI_LLM_MODEL


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
    """Multi-turn chat with Finance agent (6 Jars knowledge + personal data)."""
    session_id = req.session_id or str(uuid.uuid4())
    agent = get_finance_agent()

    config = {
        "configurable": {
            "thread_id": session_id,
            "user_id": req.user_id,
        }
    }

    start = time.monotonic()
    provider_override = req.llm_provider.value if req.llm_provider else None
    model_override = req.llm_model
    provider_plan = _build_provider_plan(provider_override)
    provider_used = provider_plan[0]
    model_used = _resolve_model_name(provider_used, model_override)

    # Convert request history to LangChain messages
    history_messages = []
    if req.history:
        for m in req.history:
            if m.role == "system":
                history_messages.append(SystemMessage(content=m.content))
            elif m.role == "user":
                history_messages.append(HumanMessage(content=m.content))
            elif m.role == "assistant":
                history_messages.append(AIMessage(content=m.content, tool_calls=m.tool_calls or []))
            elif m.role == "tool":
                # Note: tid might be missing in simplified DTO, fallback to name or generic
                history_messages.append(ToolMessage(content=m.content, tool_call_id=str(uuid.uuid4())))

    logger.info(
        "chat_request_started",
        user_id=req.user_id,
        session_id=session_id,
        provider_used=provider_used,
        model_used=model_used,
        provider_plan=provider_plan,
        ollama_base_url=settings.OLLAMA_BASE_URL if provider_used == "ollama" else None,
        message_len=len(req.message or ""),
        history_len=len(history_messages),
    )
    result: dict | None = None
    last_error: Exception | None = None
    for idx, provider in enumerate(provider_plan):
        provider_used = provider
        model_used = _resolve_model_name(provider_used, model_override)
        try:
            with llm_provider_override(provider_used), llm_model_override(model_override):
                result = await agent.ainvoke(
                    {
                        "messages": [HumanMessage(content=req.message)],
                    },
                    config=config,
                    history=history_messages,
                )
            break
        except Exception as exc:
            last_error = exc
            err = str(exc)
            should_retry = idx < len(provider_plan) - 1 and _is_retryable_provider_error(err)
            logger.error(
                "agent_invoke_failed",
                error=err,
                user_id=req.user_id,
                provider=provider_used,
                attempt=idx + 1,
                will_retry=should_retry,
            )
            if should_retry:
                continue

            if "RESOURCE_EXHAUSTED" in err or "429" in err:
                raise HTTPException(
                    status_code=429,
                    detail="AI provider quota exhausted (RESOURCE_EXHAUSTED). Please retry later.",
                ) from exc
            raise HTTPException(status_code=500, detail="AI agent error") from exc

    if result is None:
        err = str(last_error) if last_error else "Unknown AI error"
        if "RESOURCE_EXHAUSTED" in err or "429" in err:
            raise HTTPException(
                status_code=429,
                detail="AI provider quota exhausted (RESOURCE_EXHAUSTED). Please retry later.",
            )
        raise HTTPException(status_code=500, detail="AI agent error")

    latency_ms = int((time.monotonic() - start) * 1000)

    # Last message in the graph output is the final AI reply
    messages = result.get("messages", [])
    if not messages:
        raise HTTPException(status_code=500, detail="Agent returned no messages")

    # Extract intent and answer_mode from agent result (for logging/debug)
    intent: str | None = result.get("intent")
    answer_mode: str | None = result.get("answer_mode")

    logger.info(
        "chat_request_processed",
        user_id=req.user_id,
        session_id=session_id,
        intent=intent,
        answer_mode=answer_mode,
        provider_used=provider_used,
        model_used=model_used,
        latency_ms=latency_ms,
    )

    if provider_used == "ollama" and latency_ms >= 120_000:
        logger.warning(
            "chat_request_slow_local",
            user_id=req.user_id,
            session_id=session_id,
            provider_used=provider_used,
            model_used=model_used,
            latency_ms=latency_ms,
            note="Local model is slow on current hardware or prompt complexity.",
        )

    # Logging tool usage and debug
    for msg in messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                tool_name = _tool_call_name(tc)
                if isinstance(tc, dict):
                    args = tc.get("args")
                else:
                    args = getattr(tc, "args", None)
                logger.info("tool_used", tool=tool_name, args=args, user_id=req.user_id, intent=intent)
        logger.info(
            "debug_message",
            type=msg.type,
            content_len=len(str(msg.content)),
            content_preview=str(msg.content)[:100],
        )

    reply = messages[-1].content
    if isinstance(reply, list):
        reply = " ".join(
            [str(block.get("text", "")) for block in reply if isinstance(block, dict) and "text" in block]
        )
    elif not isinstance(reply, str):
        reply = str(reply)

    if not reply or not reply.strip():
        reply = (
            _synthesise_reply_from_tools(messages)
            or "Xin lỗi, tôi chưa thể tổng hợp kết quả. Vui lòng thử lại."
        )

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
        intent=intent,
        answer_mode=answer_mode,
        provider_used=provider_used,
        model_used=model_used,
    )


@router.post("/chat/stream")
async def chat_stream(
    req: ChatRequest,
    _: str = Depends(verify_service_token),
) -> EventSourceResponse:
    """Streaming variant of /chat — emits SSE events as the agent processes the request.

    SSE event types:
      status  — tool-calling phase progress ("Đang tra cứu số dư ví...")
      token   — individual text tokens of the final reply
      done    — metadata JSON (sessionId, intent, answerMode, providerUsed, modelUsed)
      error   — error detail string
    """
    session_id = req.session_id or str(uuid.uuid4())
    agent = get_finance_agent()

    # Streaming is only supported on vertexai; override to vertexai if needed.
    provider_used = "vertexai"
    model_used = _resolve_model_name(provider_used, req.llm_model)

    config = {
        "configurable": {
            "thread_id": session_id,
            "user_id": req.user_id,
        }
    }

    history_messages = []
    if req.history:
        for m in req.history:
            if m.role == "system":
                history_messages.append(SystemMessage(content=m.content))
            elif m.role == "user":
                history_messages.append(HumanMessage(content=m.content))
            elif m.role == "assistant":
                history_messages.append(AIMessage(content=m.content, tool_calls=m.tool_calls or []))
            elif m.role == "tool":
                history_messages.append(ToolMessage(content=m.content, tool_call_id=str(uuid.uuid4())))

    logger.info(
        "chat_stream_started",
        user_id=req.user_id,
        session_id=session_id,
        provider_used=provider_used,
        model_used=model_used,
    )

    async def event_generator():
        try:
            with llm_provider_override(provider_used), llm_model_override(req.llm_model):
                async for event_type, data in agent.astream(
                    {"messages": [HumanMessage(content=req.message)]},
                    config=config,
                    history=history_messages,
                ):
                    if event_type == "status":
                        yield ServerSentEvent(
                            event="status",
                            data=json.dumps({"message": data}, ensure_ascii=False),
                        )
                    elif event_type == "token":
                        yield ServerSentEvent(
                            event="token",
                            data=json.dumps({"text": data}, ensure_ascii=False),
                        )

            logger.info(
                "chat_stream_completed",
                user_id=req.user_id,
                session_id=session_id,
            )
            yield ServerSentEvent(
                event="done",
                data=json.dumps(
                    {
                        "sessionId": session_id,
                        "intent": None,
                        "answerMode": None,
                        "agentUsed": ["finance"],
                        "providerUsed": provider_used,
                        "modelUsed": model_used,
                    },
                    ensure_ascii=False,
                ),
            )
        except Exception as exc:
            err = str(exc)
            logger.error(
                "chat_stream_error",
                error=err,
                user_id=req.user_id,
                session_id=session_id,
            )
            yield ServerSentEvent(
                event="error",
                data=json.dumps({"detail": "AI agent error. Vui lòng thử lại."}, ensure_ascii=False),
            )

    return EventSourceResponse(event_generator())

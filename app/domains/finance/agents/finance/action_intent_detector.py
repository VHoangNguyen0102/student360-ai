"""ActionIntentDetector — lightweight LLM yes/no classification for action intent.

Replaces the hardcoded _ACTION_KEYWORDS list in chat_stream.
Returns True if the message contains an intention to perform a financial action.
Returns False on any error so the full agent always runs as the safe fallback.
"""
from __future__ import annotations

import asyncio
import time

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm.factory import get_chat_model
from app.core.llm.runtime_provider import llm_provider_override

logger = structlog.get_logger()

_DETECT_TIMEOUT_S = 3.0

_SYSTEM_PROMPT = """\
Bạn là trợ lý phân loại ý định tài chính. Nhiệm vụ duy nhất: xác định tin nhắn \
người dùng có thể hiện ý định thực hiện một HÀNH ĐỘNG tài chính hay không.

Trả lời YES nếu người dùng muốn:
1. Ghi nhận khoản chi hoặc thu vào lọ (vừa chi, mới mua, ăn, uống, thanh toán, ghi chi, ghi thu...)
2. Phân bổ lương/thu nhập vào 6 lọ (nhận lương, có lương, nhận tiền...)
3. Chuyển tiền giữa các lọ
4. Điều chỉnh tỷ lệ phân bổ lọ (tăng/giảm phần trăm lọ nào đó)
5. Tạo lịch chuyển/tiết kiệm định kỳ (mỗi tháng, hàng tuần...)
6. Xóa một lịch tự động
7. Tạm dừng hoặc bật lại lịch tự động
8. Cập nhật lịch tự động (sửa số tiền, ngày, tần suất)
9. Xóa một giao dịch đã ghi

Trả lời NO nếu người dùng chỉ hỏi thông tin, xem số dư, xem báo cáo, hoặc hỏi kiến thức.
Bỏ qua lỗi chính tả và viết tắt. Chỉ trả lời đúng một từ: YES hoặc NO\
"""

_USER_PROMPT = "Tin nhắn người dùng: {message}"


class ActionIntentDetector:
    """Async yes/no classifier for financial action intent.

    Args:
        provider: LLM provider to use (gemini/vertexai/ollama).
                  Applied via llm_provider_override so get_chat_model() picks it up.
                  If None, inherits whatever ContextVar is currently set.
    """

    def __init__(self, provider: str | None = None) -> None:
        self._provider = provider

    async def detect(self, message: str, user_id: str = "") -> bool:
        """Return True if the message contains a financial action intent.

        Never raises — returns False on timeout, LLM error, or unexpected output.
        """
        if not message or not message.strip():
            return False

        start = time.monotonic()
        try:
            result = await asyncio.wait_for(
                self._run_detection(message),
                timeout=_DETECT_TIMEOUT_S,
            )
            logger.info(
                "action_intent_detected",
                user_id=user_id,
                detected=result,
                latency_ms=int((time.monotonic() - start) * 1000),
            )
            return result
        except asyncio.TimeoutError:
            logger.warning(
                "action_intent_detector_timeout",
                user_id=user_id,
                timeout_s=_DETECT_TIMEOUT_S,
            )
            return False
        except Exception as exc:
            logger.error(
                "action_intent_detector_error",
                user_id=user_id,
                error=str(exc),
            )
            return False

    async def _run_detection(self, message: str) -> bool:
        # get_chat_model() reads the ContextVar at call time — model is fully
        # configured before ainvoke(), so ainvoke() can live outside the with block.
        with llm_provider_override(self._provider):
            llm = get_chat_model(temperature=0)

        response = await llm.ainvoke([
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=_USER_PROMPT.format(message=message[:400])),
        ])

        raw = response.content
        if isinstance(raw, list):
            # Gemini sometimes returns a list of content blocks
            raw = " ".join(
                str(b.get("text", "")) for b in raw if isinstance(b, dict)
            )
        return str(raw).strip().upper().startswith("YES")

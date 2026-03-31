"""
Six Jars domain — Intent Classifier.

Classifies user messages into one of 3 intents:
  knowledge_6jars  — câu hỏi kiến thức/nguyên tắc 6 lọ (không cần tool)
  personal_finance — câu hỏi về tài chính cá nhân (cần tool)
  hybrid           — kết hợp kiến thức + cá nhân (cần tool + lời khuyên)

Priority:
  1. Rule-based keyword matching (fast, no LLM cost)
  2. LLM fallback (only when keywords cannot decide)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal

import structlog

logger = structlog.get_logger()

Intent = Literal["knowledge_6jars", "personal_finance", "hybrid"]

# ──────────────────────────────────────────────────────────────────────────────
# Keyword lists
# ──────────────────────────────────────────────────────────────────────────────

# Strong signals → knowledge_6jars (questions about the METHOD itself)
_KNOWLEDGE_KEYWORDS: list[str] = [
    "6 lọ là gì",
    "6 lọ dùng để",
    "phương pháp 6",
    "phương pháp sáu lọ",
    "t. harv eker",
    "harv eker",
    "secrets of the millionaire",
    "lọ essentials là gì",
    "lọ education là gì",
    "lọ investment là gì",
    "lọ enjoyment là gì",
    "lọ reserve là gì",
    "lọ sharing là gì",
    "tỷ lệ 6 lọ",
    "tỉ lệ 6 lọ",
    "ty le 6 lo",
    "nguyên tắc 6 lọ",
    "nguyen tac 6 lo",
    "lợi ích 6 lọ",
    "loi ich 6 lo",
    "cách áp dụng 6 lọ",
    "bắt đầu với 6 lọ",
    "6 lọ hoạt động",
    "6 lọ phù hợp",
    "ý nghĩa lọ",
    "y nghia lo",
    "mục đích lọ",
    "muc dich lo",
    "lọ dự phòng để làm gì",
    "lọ giáo dục để làm gì",
    "lọ chia sẻ để làm gì",
    "thay đổi tỷ lệ",
    "thay doi ty le",
    "có nên dùng 6 lọ",
    "6 lọ cho sinh viên",
    "envelope method",
    "six jars",
    "money jar",
    "xử lý nợ",
    "tra no",
    "vay tiền",
    "thu nhập bấp bênh",
    "thu nhap ko deu",
    "lam part-time",
    "chạy grab",
    "reset ngân sách",
    "lam lai tu dau",
    "mục tiêu tiết kiệm",
    "tiet kiem mua",
    "mẹo sinh viên",
    "meo tai chinh",
]

# Strong signals → personal_finance (questions about THIS user's data)
_PERSONAL_KEYWORDS: list[str] = [
    "số dư của tôi",
    "so du cua toi",
    "lọ của tôi",
    "lo cua toi",
    "tôi đã chi",
    "toi da chi",
    "tôi đã tiêu",
    "toi da tieu",
    "giao dịch gần đây",
    "giao dich gan day",
    "giao dịch của tôi",
    "giao dich cua toi",
    "lịch sử giao dịch",
    "lich su giao dich",
    "ngân sách của tôi",
    "ngan sach cua toi",
    "thu nhập của tôi",
    "thu nhap cua toi",
    "chi tiêu của tôi",
    "chi tieu cua toi",
    "tôi chi bao nhiêu",
    "toi chi bao nhieu",
    "tháng này tôi",
    "thang nay toi",
    "tháng trước tôi",
    "thang truoc toi",
    "tình trạng tài chính của tôi",
    "tinh trang tai chinh cua toi",
    "show my",
    "my balance",
    "my transactions",
    "my budget",
]

# Hybrid signals — personal data + advice/comparison needed
_HYBRID_KEYWORDS: list[str] = [
    "của tôi có đủ",
    "cua toi co du",
    "của tôi có nên",
    "cua toi co nen",
    "của tôi đang",
    "cua toi dang",
    "tôi có đang phân bổ",
    "toi co dang phan bo",
    "tôi nên điều chỉnh",
    "toi nen dieu chinh",
    "tôi nên tăng",
    "toi nen tang",
    "tôi nên giảm",
    "toi nen giam",
    "phân tích tài chính tôi",
    "phan tich tai chinh toi",
    "dựa trên chi tiêu của tôi",
    "dua tren chi tieu cua toi",
    "số dư có đủ",
    "so du co du",
    "có vượt mức",
    "co vuot muc",
    "đang đúng tỷ lệ",
    "dang dung ty le",
    "tôi nên trả nợ thế nào",
    "toi nen tra no the nao",
    "thu nhập của tôi không ổn định",
    "tôi muốn làm lại từ đầu",
    "tôi muốn reset",
]


def _normalize(text: str) -> str:
    return (text or "").lower().strip()


def _has_any(text: str, keywords: list[str]) -> bool:
    t = _normalize(text)
    return any(k in t for k in keywords)


# ──────────────────────────────────────────────────────────────────────────────
# Rule-based classifier
# ──────────────────────────────────────────────────────────────────────────────

def classify_by_rules(message: str) -> tuple[Intent | None, float, str]:
    """
    Return (intent, confidence, reason) or (None, 0.0, '') if inconclusive.

    Priority: hybrid > personal > knowledge
    (hybrid is checked first because it often contains both keyword sets)
    """
    if _has_any(message, _HYBRID_KEYWORDS):
        return "hybrid", 0.88, "rule:hybrid_keywords"

    has_personal = _has_any(message, _PERSONAL_KEYWORDS)
    has_knowledge = _has_any(message, _KNOWLEDGE_KEYWORDS)

    if has_personal and has_knowledge:
        return "hybrid", 0.85, "rule:personal+knowledge"
    if has_personal:
        return "personal_finance", 0.90, "rule:personal_keywords"
    if has_knowledge:
        return "knowledge_6jars", 0.90, "rule:knowledge_keywords"

    return None, 0.0, ""


# ──────────────────────────────────────────────────────────────────────────────
# LLM-based fallback classifier
# ──────────────────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict | None:
    s = (text or "").strip()
    if not s:
        return None
    if s.startswith("{") and s.endswith("}"):
        try:
            return json.loads(s)
        except Exception:
            return None
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(s[start:end + 1])
        except Exception:
            return None
    return None


async def classify_by_llm(message: str) -> tuple[Intent, float, str]:
    """LLM fallback — only called when rule-based is inconclusive."""
    from app.core.llm import get_llm
    from langchain_core.messages import HumanMessage, SystemMessage
    from app.domains.finance.agents.finance.six_jars.intent_prompts import (
        INTENT_CLASSIFIER_SYSTEM_PROMPT,
    )

    try:
        llm = get_llm()
        resp = await llm.ainvoke(
            [
                SystemMessage(content=INTENT_CLASSIFIER_SYSTEM_PROMPT),
                HumanMessage(content=message),
            ]
        )
        raw = str(getattr(resp, "content", "") or "")
        parsed = _extract_json(raw) or {}

        intent_raw = str(parsed.get("intent", "hybrid")).strip().lower()
        if intent_raw not in {"knowledge_6jars", "personal_finance", "hybrid"}:
            intent_raw = "hybrid"

        conf = float(parsed.get("confidence", 0.5))
        conf = max(0.0, min(conf, 1.0))
        reason = str(parsed.get("reason", "llm_fallback"))

        return intent_raw, conf, f"llm:{reason}"  # type: ignore[return-value]

    except Exception as exc:
        logger.warning("intent_llm_fallback_failed", error=str(exc))
        # Safe default: hybrid allows tools + gives advice
        return "hybrid", 0.4, f"llm_error:{type(exc).__name__}"


# ──────────────────────────────────────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class IntentResult:
    intent: Intent
    confidence: float
    route_reason: str


async def classify_intent(message: str, context_hint: str = "auto") -> IntentResult:
    """
    Classify the intent of a finance chat message.

    Args:
        message: The user's message text.
        context_hint: Optional context from the client, e.g. 'finance', 'auto'.

    Returns:
        IntentResult with intent, confidence, and routing reason.
    """
    # Step 1: Rule-based (fast, free)
    intent, confidence, reason = classify_by_rules(message)

    if intent is not None and confidence >= 0.75:
        logger.info(
            "intent_classified",
            intent=intent,
            confidence=confidence,
            reason=reason,
            method="rules",
        )
        return IntentResult(intent=intent, confidence=confidence, route_reason=reason)

    # Step 2: LLM fallback (for ambiguous messages)
    llm_intent, llm_conf, llm_reason = await classify_by_llm(message)

    # Use LLM result if confidence is acceptable
    if llm_conf >= 0.55:
        final_intent = llm_intent
        final_conf = llm_conf
        final_reason = llm_reason
    else:
        # Default: hybrid is safest (has tools + advice)
        final_intent = "hybrid"
        final_conf = llm_conf
        final_reason = f"llm_low_conf:{llm_conf:.2f}_default_hybrid"

    logger.info(
        "intent_classified",
        intent=final_intent,
        confidence=final_conf,
        reason=final_reason,
        method="llm_fallback",
    )
    return IntentResult(intent=final_intent, confidence=final_conf, route_reason=final_reason)

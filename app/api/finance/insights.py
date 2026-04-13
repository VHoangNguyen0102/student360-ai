"""
Finance Insights API — POST /api/v1/insights
Generates a short AI-written monthly financial insight text.
Direct DB fetch + single LLM call (no agent loop).
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.database import get_pool
from app.core.llm import get_llm
from app.domains.finance.agents.finance.six_jars.prompts_insights import INSIGHTS_SYSTEM_PROMPT
from app.utils.auth import verify_service_token

logger = structlog.get_logger()
router = APIRouter()


# ─────────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────────


class InsightsRequest(BaseModel):
    user_id: str
    month: int = Field(..., ge=1, le=12)
    year: int = Field(..., ge=2000, le=2100)


class InsightsResponse(BaseModel):
    insight: str
    month: int
    year: int
    generated_at: str


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

_MONTH_QUERY = """
    SELECT mj.category_type                                           AS jar_code,
           mj.name                                                    AS jar_name,
           SUM(CASE WHEN ft.type = 'income'  THEN ft.amount ELSE 0 END) AS total_income,
           SUM(CASE WHEN ft.type = 'expense' THEN ft.amount ELSE 0 END) AS total_expense,
           COUNT(*)                                                    AS tx_count
    FROM   financial_transactions ft
    JOIN   money_jars mj ON mj.id = ft.money_jar_id
    WHERE  ft.user_id   = $1
      AND  ft.is_deleted = false
      AND  DATE_TRUNC('month', ft.transaction_date) = DATE_TRUNC('month', $2::timestamptz)
    GROUP  BY mj.category_type, mj.name
    ORDER  BY total_expense DESC
"""


def _serialize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    return value


async def _fetch_month(conn: Any, user_id: str, ref: datetime) -> list[dict]:
    rows = await conn.fetch(_MONTH_QUERY, user_id, ref)
    return [_serialize(dict(r)) for r in rows]


def _prev_month(month: int, year: int) -> tuple[int, int]:
    if month == 1:
        return 12, year - 1
    return month - 1, year


def _fmt_summary(rows: list[dict], label: str) -> str:
    if not rows:
        return f"{label}: Không có dữ liệu."
    total_income = sum(r.get("total_income") or 0 for r in rows)
    total_expense = sum(r.get("total_expense") or 0 for r in rows)
    lines = [
        f"{label}:",
        f"  Tổng thu: {total_income:,.0f} VND",
        f"  Tổng chi: {total_expense:,.0f} VND",
        f"  Dòng tiền ròng: {total_income - total_expense:,.0f} VND",
        "  Chi tiết từng lọ:",
    ]
    for r in rows:
        lines.append(
            f"    - {r.get('jar_name', r.get('jar_code'))}: "
            f"thu {r.get('total_income', 0):,.0f} VND / "
            f"chi {r.get('total_expense', 0):,.0f} VND "
            f"({r.get('tx_count', 0)} giao dịch)"
        )
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# Endpoint
# ─────────────────────────────────────────────────────────────


@router.post("/insights", response_model=InsightsResponse)
async def get_insights(
    req: InsightsRequest,
    _: str = Depends(verify_service_token),
) -> InsightsResponse:
    """
    Generate a short AI financial insight paragraph for a given month.
    Fetches current + previous month data from DB, then calls LLM once.
    """
    cur_ref = datetime(req.year, req.month, 1)
    prev_m, prev_y = _prev_month(req.month, req.year)
    prev_ref = datetime(prev_y, prev_m, 1)

    pool = await get_pool()
    async with pool.acquire() as conn:
        cur_rows, prev_rows = await asyncio.gather(
            _fetch_month(conn, req.user_id, cur_ref),
            _fetch_month(conn, req.user_id, prev_ref),
        )

    if not cur_rows:
        return InsightsResponse(
            insight="Chưa có dữ liệu giao dịch trong tháng này để phân tích.",
            month=req.month,
            year=req.year,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    cur_label = f"Tháng {req.month}/{req.year}"
    prev_label = f"Tháng {prev_m}/{prev_y}"

    user_message = (
        f"Dữ liệu tài chính:\n\n"
        f"{_fmt_summary(cur_rows, cur_label)}\n\n"
        f"{_fmt_summary(prev_rows, prev_label)}\n\n"
        f"Hãy viết nhận định tài chính cho {cur_label}."
    )

    llm = get_llm()
    try:
        response = await llm.ainvoke(
            [
                {"role": "system", "content": INSIGHTS_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ]
        )
        insight_text = response.content
        if isinstance(insight_text, list):
            insight_text = " ".join(
                block.get("text", "") for block in insight_text if isinstance(block, dict)
            )
        insight_text = str(insight_text).strip()
    except Exception as exc:
        logger.warning("insights_llm_failed", error=str(exc), user_id=req.user_id)
        raise HTTPException(status_code=503, detail="AI service unavailable, please retry later.") from exc

    if not insight_text:
        insight_text = "Không thể tạo nhận định tài chính lúc này, vui lòng thử lại sau."

    logger.info("insights_generated", user_id=req.user_id, month=req.month, year=req.year)

    return InsightsResponse(
        insight=insight_text,
        month=req.month,
        year=req.year,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

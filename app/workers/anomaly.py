"""
Anomaly Detection Worker — callable detector (external-trigger mode).

Port source reference:
backend/src/modules/jars/ai_integration/anomaly-detection.job.ts
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import structlog

from app.core.database import get_pool

logger = structlog.get_logger()

SPIKE_MULTIPLIER = Decimal("1.5")  # current month > previous month * 1.5
MODULE_TYPE_FINANCE = "finance"
ALERT_TYPE_SPIKE = "spike_expense"
ALERT_TYPE_BUDGET = "budget_exceeded"


@dataclass(slots=True)
class ExpenseRow:
    user_id: str
    money_jar_id: str
    jar_code: str
    jar_name: str
    total_expense: Decimal


@dataclass(slots=True)
class BudgetRow:
    user_id: str
    money_jar_id: str
    jar_code: str
    jar_name: str
    budget_limit: Decimal


def _month_start(value: datetime | None) -> datetime:
    ref = value or datetime.now(timezone.utc)
    return datetime(ref.year, ref.month, 1, tzinfo=timezone.utc)


def _previous_month_start(value: datetime) -> datetime:
    if value.month == 1:
        return datetime(value.year - 1, 12, 1, tzinfo=timezone.utc)
    return datetime(value.year, value.month - 1, 1, tzinfo=timezone.utc)


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value or 0))


def _fmt_money(value: Decimal) -> str:
    return f"{int(value):,}".replace(",", ".")


def _build_spike_description(jar_name: str, cur: Decimal, prev: Decimal, ref: datetime) -> str:
    return (
        f"[{ref.month:02d}/{ref.year}] Chi tiêu lọ {jar_name} tăng đột biến: "
        f"{_fmt_money(cur)} VND, cao hơn tháng trước ({_fmt_money(prev)} VND) quá 50%."
    )


def _build_budget_description(jar_name: str, spent: Decimal, budget: Decimal, ref: datetime) -> str:
    exceeded = spent - budget
    return (
        f"[{ref.month:02d}/{ref.year}] Lọ {jar_name} đã vượt ngân sách: "
        f"chi {_fmt_money(spent)} VND / hạn mức {_fmt_money(budget)} VND "
        f"(vượt {_fmt_money(exceeded)} VND)."
    )


async def _fetch_monthly_expenses(conn: Any, month_ref: datetime) -> list[ExpenseRow]:
    rows = await conn.fetch(
        """
        SELECT ft.user_id::text       AS user_id,
               ft.money_jar_id::text  AS money_jar_id,
               mj.category_type       AS jar_code,
               mj.name                AS jar_name,
               SUM(ft.amount)         AS total_expense
        FROM   financial_transactions ft
        JOIN   money_jars mj ON mj.id = ft.money_jar_id
        WHERE  ft.type = 'expense'
          AND  ft.is_deleted = false
          AND  mj.is_deleted = false
          AND  DATE_TRUNC('month', ft.transaction_date) = DATE_TRUNC('month', $1::timestamptz)
        GROUP BY ft.user_id, ft.money_jar_id, mj.category_type, mj.name
        """,
        month_ref,
    )
    result: list[ExpenseRow] = []
    for row in rows:
        result.append(
            ExpenseRow(
                user_id=str(row["user_id"]),
                money_jar_id=str(row["money_jar_id"]),
                jar_code=str(row["jar_code"]),
                jar_name=str(row["jar_name"]),
                total_expense=_to_decimal(row["total_expense"]),
            )
        )
    return result


async def _fetch_active_monthly_budgets(conn: Any, month_ref: datetime) -> list[BudgetRow]:
    rows = await conn.fetch(
        """
        WITH month_window AS (
            SELECT DATE_TRUNC('month', $1::timestamptz)::date AS month_start,
                   (DATE_TRUNC('month', $1::timestamptz) + INTERVAL '1 month - 1 day')::date AS month_end
        ),
        ranked AS (
            SELECT mj.user_id::text       AS user_id,
                   b.money_jar_id::text   AS money_jar_id,
                   mj.category_type       AS jar_code,
                   mj.name                AS jar_name,
                   b.amount               AS budget_limit,
                   ROW_NUMBER() OVER (
                       PARTITION BY mj.user_id, b.money_jar_id
                       ORDER BY b.period_start DESC
                   ) AS rn
            FROM budgets b
            JOIN money_jars mj ON mj.id = b.money_jar_id
            CROSS JOIN month_window mw
            WHERE b.is_active = true
              AND mj.is_deleted = false
              AND b.period_start <= mw.month_end
              AND (b.period_end IS NULL OR b.period_end >= mw.month_start)
        )
        SELECT user_id, money_jar_id, jar_code, jar_name, budget_limit
        FROM ranked
        WHERE rn = 1
        """,
        month_ref,
    )
    result: list[BudgetRow] = []
    for row in rows:
        result.append(
            BudgetRow(
                user_id=str(row["user_id"]),
                money_jar_id=str(row["money_jar_id"]),
                jar_code=str(row["jar_code"]),
                jar_name=str(row["jar_name"]),
                budget_limit=_to_decimal(row["budget_limit"]),
            )
        )
    return result


async def _insert_alert_if_missing(
    conn: Any,
    *,
    user_id: str,
    alert_type: str,
    target_id: str,
    description: str,
    month_ref: datetime,
) -> bool:
    exists = await conn.fetchval(
        """
        SELECT 1
        FROM ai_anomaly_alerts
        WHERE user_id = $1::uuid
          AND module_type = $2
          AND alert_type = $3
          AND target_id = $4
          AND DATE_TRUNC('month', created_at) = DATE_TRUNC('month', $5::timestamptz)
          AND description = $6
        LIMIT 1
        """,
        user_id,
        MODULE_TYPE_FINANCE,
        alert_type,
        target_id,
        month_ref,
        description,
    )
    if exists:
        return False

    await conn.execute(
        """
        INSERT INTO ai_anomaly_alerts (
            user_id,
            module_type,
            alert_type,
            target_id,
            description,
            is_read
        )
        VALUES ($1::uuid, $2, $3, $4, $5, false)
        """,
        user_id,
        MODULE_TYPE_FINANCE,
        alert_type,
        target_id,
        description,
    )
    return True


async def run_anomaly_detection(reference_month: datetime | None = None) -> dict[str, Any]:
    """
    Detect financial anomalies for one month and store alerts.

    This function is designed for external schedulers (BE/infra) to call directly.
    """
    month_ref = _month_start(reference_month)
    prev_ref = _previous_month_start(month_ref)
    pool = await get_pool()

    summary = {
        "month": f"{month_ref.year:04d}-{month_ref.month:02d}",
        "users_scanned": 0,
        "expense_rows_current": 0,
        "alerts_created": 0,
        "alerts_skipped_duplicate": 0,
        "spike_alerts_created": 0,
        "budget_alerts_created": 0,
    }

    async with pool.acquire() as conn:
        current_rows = await _fetch_monthly_expenses(conn, month_ref)
        previous_rows = await _fetch_monthly_expenses(conn, prev_ref)
        budget_rows = await _fetch_active_monthly_budgets(conn, month_ref)

        summary["expense_rows_current"] = len(current_rows)
        summary["users_scanned"] = len({row.user_id for row in current_rows})

        previous_map = {
            (row.user_id, row.money_jar_id): row.total_expense for row in previous_rows
        }
        budget_map = {
            (row.user_id, row.money_jar_id): row for row in budget_rows
        }

        for cur in current_rows:
            prev = previous_map.get((cur.user_id, cur.money_jar_id), Decimal("0"))
            if prev > 0 and cur.total_expense > (prev * SPIKE_MULTIPLIER):
                description = _build_spike_description(cur.jar_name, cur.total_expense, prev, month_ref)
                created = await _insert_alert_if_missing(
                    conn,
                    user_id=cur.user_id,
                    alert_type=ALERT_TYPE_SPIKE,
                    target_id=cur.money_jar_id,
                    description=description,
                    month_ref=month_ref,
                )
                if created:
                    summary["alerts_created"] += 1
                    summary["spike_alerts_created"] += 1
                else:
                    summary["alerts_skipped_duplicate"] += 1

            budget = budget_map.get((cur.user_id, cur.money_jar_id))
            if budget is not None and budget.budget_limit > 0 and cur.total_expense > budget.budget_limit:
                description = _build_budget_description(
                    cur.jar_name,
                    cur.total_expense,
                    budget.budget_limit,
                    month_ref,
                )
                created = await _insert_alert_if_missing(
                    conn,
                    user_id=cur.user_id,
                    alert_type=ALERT_TYPE_BUDGET,
                    target_id=cur.money_jar_id,
                    description=description,
                    month_ref=month_ref,
                )
                if created:
                    summary["alerts_created"] += 1
                    summary["budget_alerts_created"] += 1
                else:
                    summary["alerts_skipped_duplicate"] += 1

    logger.info("anomaly_detection_completed", **summary)
    return summary


async def detect_anomalies(reference_month: datetime | None = None) -> dict[str, Any]:
    """Compatibility alias for external callers."""
    return await run_anomaly_detection(reference_month=reference_month)

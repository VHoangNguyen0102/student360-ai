"""
Finance Agent — 6-Jars Tools (11 read-only tools)
Port from: backend/src/modules/jars/ai_integration/jars-tools.ts

All tools receive user_id from LangGraph RunnableConfig — the agent never
needs to pass it explicitly.

Tools:
  Balance:      get_jar_balance, get_jar_allocations, get_jar_statistics
  Transactions: get_recent_transactions, get_top_expenses, search_transactions
  Budget:       get_budget_status, get_monthly_summary, compare_months
  Trend:        get_spending_trend
  Schedule:     get_auto_transfers
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import structlog
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from app.core.database import get_pool

logger = structlog.get_logger()


def _serialize(value: object) -> object:
    """Recursively make asyncpg record data JSON-serialisable."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    return value


def _fmt(records: list) -> str:
    if not records:
        return "No records found."
    # Return as a formatted string rather than a JSON array to avoid confusing Gemini 2.5
    result = []
    for i, r in enumerate(records):
        data = _serialize(dict(r))
        result.append(f"Record {i+1}:\n" + json.dumps(data, indent=2, ensure_ascii=False))
    return "\n\n".join(result)


def _uid(config: RunnableConfig) -> str:
    return config["configurable"]["user_id"]


# ─────────────────────────────────────────────────────────────
# 1. Get balance of a single jar
# ─────────────────────────────────────────────────────────────


@tool
async def get_jar_balance(jar_code: str, config: RunnableConfig) -> str:
    """
    Get the current balance and metadata for a specific jar.
    jar_code must be one of: reserve, enjoyment, essentials, education, investment, sharing
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT category_type AS jar_code,
                   name,
                   current_balance,
                   percentage,
                   accumulated_income,
                   accumulated_expense,
                   is_active
            FROM   money_jars
            WHERE  user_id       = $1
              AND  category_type = $2
              AND  is_deleted    = false
            """,
            _uid(config),
            jar_code,
        )
    if row is None:
        return json.dumps({"error": f"Jar '{jar_code}' not found for this user."})
    return json.dumps(_serialize(dict(row)), ensure_ascii=False)


# ─────────────────────────────────────────────────────────────
# 2. Overview of all jars
# ─────────────────────────────────────────────────────────────


@tool
async def get_jar_allocations(config: RunnableConfig) -> str:
    """
    Get all jars with their percentage allocations and current balances.
    Use this for a full overview of the user's 6-Jars setup.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT category_type AS jar_code,
                   name,
                   percentage,
                   current_balance,
                   is_active
            FROM   money_jars
            WHERE  user_id    = $1
              AND  is_deleted = false
            ORDER  BY category_type
            """,
            _uid(config),
        )
    return _fmt(rows)


# ─────────────────────────────────────────────────────────────
# 3. Cumulative jar statistics
# ─────────────────────────────────────────────────────────────


@tool
async def get_jar_statistics(jar_code: str, config: RunnableConfig) -> str:
    """
    Get cumulative income, expense and net flow for a specific jar (all-time).
    jar_code: reserve | enjoyment | essentials | education | investment | sharing
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT category_type                                  AS jar_code,
                   name,
                   accumulated_income,
                   accumulated_expense,
                   accumulated_income - accumulated_expense       AS net_flow,
                   current_balance
            FROM   money_jars
            WHERE  user_id       = $1
              AND  category_type = $2
              AND  is_deleted    = false
            """,
            _uid(config),
            jar_code,
        )
    if row is None:
        return f"Jar '{jar_code}' not found."
    return _fmt([row])


# ─────────────────────────────────────────────────────────────
# 4. Recent transactions
# ─────────────────────────────────────────────────────────────


@tool
async def get_recent_transactions(limit: int, config: RunnableConfig) -> str:
    """
    Get the most recent financial transactions across all jars.
    limit: how many to return (max 50).
    """
    safe_limit = min(max(int(limit), 1), 50)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ft.id,
                   ft.type,
                   ft.amount,
                   ft.description,
                   ft.transaction_date,
                   ft.notes,
                   mj.category_type AS jar_code,
                   mj.name          AS jar_name
            FROM   financial_transactions ft
            JOIN   money_jars mj ON mj.id = ft.money_jar_id
            WHERE  ft.user_id    = $1
              AND  ft.is_deleted = false
            ORDER  BY ft.transaction_date DESC
            LIMIT  $2
            """,
            _uid(config),
            safe_limit,
        )
    return _fmt(rows)


# ─────────────────────────────────────────────────────────────
# 5. Top expenses in last N days
# ─────────────────────────────────────────────────────────────


@tool
async def get_top_expenses(days: int, config: RunnableConfig) -> str:
    """
    Get the 10 largest expense transactions in the last N days.
    days: look-back window (e.g. 30 for last month).
    """
    since = datetime.utcnow() - timedelta(days=max(1, int(days)))
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ft.amount,
                   ft.description,
                   ft.transaction_date,
                   mj.category_type AS jar_code,
                   mj.name          AS jar_name
            FROM   financial_transactions ft
            JOIN   money_jars mj ON mj.id = ft.money_jar_id
            WHERE  ft.user_id         = $1
              AND  ft.type            = 'expense'
              AND  ft.is_deleted      = false
              AND  ft.transaction_date >= $2
            ORDER  BY ft.amount DESC
            LIMIT  10
            """,
            _uid(config),
            since,
        )
    return _fmt(rows)


# ─────────────────────────────────────────────────────────────
# 6. Search transactions by keyword
# ─────────────────────────────────────────────────────────────


@tool
async def search_transactions(keyword: str, config: RunnableConfig) -> str:
    """
    Full-text search across transaction descriptions (case-insensitive).
    Returns up to 20 results ordered by date descending.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ft.id,
                   ft.type,
                   ft.amount,
                   ft.description,
                   ft.transaction_date,
                   mj.category_type AS jar_code
            FROM   financial_transactions ft
            JOIN   money_jars mj ON mj.id = ft.money_jar_id
            WHERE  ft.user_id     = $1
              AND  ft.is_deleted  = false
              AND  ft.description ILIKE $2
            ORDER  BY ft.transaction_date DESC
            LIMIT  20
            """,
            _uid(config),
            f"%{keyword}%",
        )
    return _fmt(rows)


# ─────────────────────────────────────────────────────────────
# 7. Budget status for a jar
# ─────────────────────────────────────────────────────────────


@tool
async def get_budget_status(jar_code: str, config: RunnableConfig) -> str:
    """
    Get the current active budget for a specific jar (budget limit, spent, remaining).
    jar_code: reserve | enjoyment | essentials | education | investment | sharing
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT b.amount          AS budget_limit,
                   b.spent_amount,
                   b.remaining_amount,
                   b.period_type,
                   b.period_start,
                   b.period_end,
                   mj.category_type  AS jar_code,
                   mj.name           AS jar_name
            FROM   budgets b
            JOIN   money_jars mj ON mj.id = b.money_jar_id
            WHERE  mj.user_id        = $1
              AND  mj.category_type  = $2
              AND  b.is_active       = true
              AND  b.period_start   <= CURRENT_DATE
              AND  (b.period_end IS NULL OR b.period_end >= CURRENT_DATE)
            ORDER  BY b.period_start DESC
            LIMIT  1
            """,
            _uid(config),
            jar_code,
        )
    if row is None:
        return json.dumps({"message": f"No active budget for jar '{jar_code}'."})
    return json.dumps(_serialize(dict(row)), ensure_ascii=False)


# ─────────────────────────────────────────────────────────────
# 8. Monthly income/expense summary per jar
# ─────────────────────────────────────────────────────────────


@tool
async def get_monthly_summary(year_month: str, config: RunnableConfig) -> str:
    """
    Get total income and expense per jar for a given month.
    year_month: 'YYYY-MM' (e.g. '2025-03').
    """
    try:
        ref = datetime.strptime(year_month, "%Y-%m")
    except ValueError:
        return json.dumps({"error": "year_month must be 'YYYY-MM' format."})

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT mj.category_type                                          AS jar_code,
                   mj.name                                                   AS jar_name,
                   SUM(CASE WHEN ft.type='income'  THEN ft.amount ELSE 0 END) AS total_income,
                   SUM(CASE WHEN ft.type='expense' THEN ft.amount ELSE 0 END) AS total_expense,
                   COUNT(*)                                                   AS tx_count
            FROM   financial_transactions ft
            JOIN   money_jars mj ON mj.id = ft.money_jar_id
            WHERE  ft.user_id   = $1
              AND  ft.is_deleted = false
              AND  DATE_TRUNC('month', ft.transaction_date) = DATE_TRUNC('month', $2::timestamptz)
            GROUP  BY mj.category_type, mj.name
            ORDER  BY total_expense DESC
            """,
            _uid(config),
            ref,
        )
    return _fmt(rows)


# ─────────────────────────────────────────────────────────────
# 9. Compare two months side by side
# ─────────────────────────────────────────────────────────────


@tool
async def compare_months(month_a: str, month_b: str, config: RunnableConfig) -> str:
    """
    Compare expense and income totals between two months across all jars.
    month_a, month_b: 'YYYY-MM' format.
    """
    results: dict = {}
    for label, ym in (("month_a", month_a), ("month_b", month_b)):
        try:
            ref = datetime.strptime(ym, "%Y-%m")
        except ValueError:
            return json.dumps({"error": f"'{ym}' is not in YYYY-MM format."})
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT mj.category_type AS jar_code,
                       SUM(CASE WHEN ft.type='expense' THEN ft.amount ELSE 0 END) AS expense,
                       SUM(CASE WHEN ft.type='income'  THEN ft.amount ELSE 0 END) AS income
                FROM   financial_transactions ft
                JOIN   money_jars mj ON mj.id = ft.money_jar_id
                WHERE  ft.user_id    = $1
                  AND  ft.is_deleted = false
                  AND  DATE_TRUNC('month', ft.transaction_date) = DATE_TRUNC('month', $2::timestamptz)
                GROUP  BY mj.category_type
                """,
                _uid(config),
                ref,
            )
        results[label] = {"period": ym, "jars": [_serialize(dict(r)) for r in rows]}

    return json.dumps(results, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────
# 10. Spending trend for a jar over last N months
# ─────────────────────────────────────────────────────────────


@tool
async def get_spending_trend(jar_code: str, months: int, config: RunnableConfig) -> str:
    """
    Show monthly expense totals for one jar over the last N months (max 12).
    jar_code: reserve | enjoyment | essentials | education | investment | sharing
    """
    safe_months = max(1, min(int(months), 12))
    since = (datetime.utcnow().replace(day=1) - timedelta(days=safe_months * 31)).replace(day=1)

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DATE_TRUNC('month', ft.transaction_date)                   AS month,
                   SUM(CASE WHEN ft.type='expense' THEN ft.amount ELSE 0 END) AS total_expense,
                   SUM(CASE WHEN ft.type='income'  THEN ft.amount ELSE 0 END) AS total_income
            FROM   financial_transactions ft
            JOIN   money_jars mj ON mj.id = ft.money_jar_id
            WHERE  ft.user_id           = $1
              AND  mj.category_type     = $2
              AND  ft.is_deleted        = false
              AND  ft.transaction_date >= $3
            GROUP  BY DATE_TRUNC('month', ft.transaction_date)
            ORDER  BY month ASC
            """,
            _uid(config),
            jar_code,
            since,
        )
    return _fmt(rows)


# ─────────────────────────────────────────────────────────────
# 11. Active auto-transfer schedules
# ─────────────────────────────────────────────────────────────


@tool
async def get_auto_transfers(config: RunnableConfig) -> str:
    """
    List all active automatic income-allocation schedules for the user.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id,
                   name,
                   amount,
                   frequency,
                   allocation_type,
                   day_of_week,
                   day_of_month,
                   custom_allocations
            FROM   auto_transfer_schedules
            WHERE  user_id   = $1
              AND  is_active = true
            ORDER  BY created_at ASC
            """,
            _uid(config),
        )
    if not rows:
        return json.dumps({"message": "No active auto-transfer schedules."})
    return _fmt(rows)


# ─────────────────────────────────────────────────────────────
# Exported registry consumed by agent.py
# ─────────────────────────────────────────────────────────────

ALL_JARS_TOOLS = [
    get_jar_balance,
    get_jar_allocations,
    get_jar_statistics,
    get_recent_transactions,
    get_top_expenses,
    search_transactions,
    get_budget_status,
    get_monthly_summary,
    compare_months,
    get_spending_trend,
    get_auto_transfers,
]

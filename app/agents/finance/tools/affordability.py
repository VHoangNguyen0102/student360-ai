"""
Affordability Check Tool — Finance Agent Tool
Evaluates if a student can afford an intended purchase.

Tools:
  can_afford_this: Quickly validate if purchase is affordable given current jar balance and spending patterns.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import structlog
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from app.core.database import get_pool
from app.core.llm import get_llm
from app.agents.finance.six_jars.prompts_affordability import get_affordability_check_prompt

logger = structlog.get_logger()


def _uid(config: RunnableConfig) -> str:
    return config["configurable"]["user_id"]


async def _get_jar_data(user_id: str, jar_code: str) -> dict | None:
    """Get jar balance and statistics from database."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT category_type AS jar_code,
                   name,
                   current_balance,
                   percentage,
                   accumulated_income,
                   accumulated_expense
            FROM   money_jars
            WHERE  user_id       = $1
              AND  category_type = $2
              AND  is_deleted    = false
            """,
            user_id,
            jar_code,
        )
    return dict(row) if row else None


async def _classify_purchase(user_id: str, description: str, amount: float) -> tuple[str, float]:
    """Classify the purchase into a jar using simple heuristics and LLM."""
    # TODO: Use actual classify pipeline when available
    # For now, default to essentials
    return "essentials", 0.7


async def _get_recent_transactions(user_id: str, jar_code: str, limit: int = 10) -> str:
    """Get recent transactions for a jar formatted for LLM context."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ft.description,
                   ft.amount,
                   ft.transaction_date
            FROM   financial_transactions ft
            JOIN   money_jars mj ON mj.id = ft.money_jar_id
            WHERE  mj.user_id    = $1
              AND  mj.category_type = $2
              AND  ft.is_deleted = false
            ORDER  BY ft.transaction_date DESC
            LIMIT  $3
            """,
            user_id,
            jar_code,
            limit,
        )
    
    if not rows:
        return "Không có giao dịch gần đây"
    
    result = []
    for i, r in enumerate(rows[:10], 1):
        data = dict(r)
        desc = data.get("description", "N/A")
        amount = data.get("amount", 0)
        result.append(f"  {i}. {desc}: {amount:,.0f} VND")
    return "\n".join(result)


async def _calculate_monthly_average(user_id: str, jar_code: str) -> float:
    """Calculate average monthly spending for a jar in last 3 months."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT COALESCE(AVG(monthly_total), 0) AS avg_monthly
            FROM (
                SELECT DATE_TRUNC('month', ft.transaction_date)::date AS month,
                       SUM(ft.amount) AS monthly_total
                FROM   financial_transactions ft
                JOIN   money_jars mj ON mj.id = ft.money_jar_id
                WHERE  mj.user_id    = $1
                  AND  mj.category_type = $2
                  AND  ft.is_deleted = false
                  AND  ft.transaction_date >= NOW() - INTERVAL '3 months'
                GROUP  BY DATE_TRUNC('month', ft.transaction_date)
            ) monthly_stats
            """,
            user_id,
            jar_code,
        )
    return float(row["avg_monthly"]) if row else 0.0


@tool
async def can_afford_this(
    description: str,
    amount: float,
    context: str = "",
    config: RunnableConfig = None,
) -> str:
    """
    Quick affordability check for an intended purchase.
    
    Args:
        description: What the user wants to buy (e.g., "mechanical keyboard for gaming")
        amount: Purchase amount in VND
        context: Additional context (e.g., "I have an exam next week")
        config: LangGraph RunnableConfig (automatically provided by agent)
    
    Returns:
        JSON string with recommendation (yes/no/wait), reason, suggested jar, and balance.
    """
    user_id = _uid(config)
    
    try:
        logger.info(
            "can_afford_this_start",
            user_id=user_id,
            description=description,
            amount=amount,
        )
        
        # Step 1: Classify the purchase into a jar
        suggested_jar, confidence = await _classify_purchase(user_id, description, amount)
        
        # Step 2: Get jar data & spending patterns
        jar_data = await _get_jar_data(user_id, suggested_jar)
        if jar_data is None:
            return json.dumps(
                {
                    "recommendation": "no",
                    "reason": f"Lọ '{suggested_jar}' không tìm thấy. Vui lòng kiểm tra lại cấu hình 6 Lọ.",
                    "suggested_jar": suggested_jar,
                    "jar_balance": 0,
                    "confidence": 0.0,
                },
                ensure_ascii=False,
            )
        
        jar_balance = jar_data.get("current_balance", 0)
        jar_name = jar_data.get("name", suggested_jar)
        
        # Get monthly allocation and spending
        monthly_income_allocated = 0  # TODO: Get from user profile
        recent_avg_expense = await _calculate_monthly_average(user_id, suggested_jar)
        recent_txns = await _get_recent_transactions(user_id, suggested_jar, limit=10)
        
        logger.info(
            "can_afford_jar_data_loaded",
            user_id=user_id,
            jar_balance=jar_balance,
            recent_avg_expense=recent_avg_expense,
        )
        
        # Step 3: Call LLM to evaluate affordability
        system_prompt, user_message = get_affordability_check_prompt(
            description=description,
            amount=amount,
            jar_code=suggested_jar,
            jar_name=jar_name,
            current_balance=jar_balance,
            monthly_balance=monthly_income_allocated,
            recent_avg_monthly_expense=recent_avg_expense,
            recent_transactions=recent_txns,
            user_context=context,
        )
        
        llm = get_llm()
        response = await llm.ainvoke(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]
        )
        content = response.content
        
        # Step 4: Parse LLM response
        recommendation = "wait"
        reason = "Không thể đánh giá lúc này"
        
        try:
            # Find JSON in response
            for start in range(len(content)):
                if content[start] == "{":
                    try:
                        parsed = json.loads(content[start:])
                        rec_str = str(parsed.get("recommendation", "wait")).lower()
                        if rec_str in ["yes", "no", "wait"]:
                            recommendation = rec_str
                        reason = str(parsed.get("reason", reason))
                        break
                    except json.JSONDecodeError:
                        continue
        except Exception as exc:
            logger.warning("can_afford_parse_failed", error=str(exc))
        
        logger.info(
            "can_afford_evaluated",
            user_id=user_id,
            recommendation=recommendation,
            jar=suggested_jar,
        )
        
        return json.dumps(
            {
                "recommendation": recommendation,
                "reason": reason,
                "suggested_jar": suggested_jar,
                "jar_balance": jar_balance,
                "confidence": confidence,
            },
            ensure_ascii=False,
        )
        
    except Exception as exc:
        logger.error("can_afford_this_failed", error=str(exc), user_id=user_id)
        return json.dumps(
            {
                "recommendation": "wait",
                "reason": f"Lỗi đánh giá: {str(exc)}",
                "suggested_jar": "unknown",
                "jar_balance": 0,
                "confidence": 0.0,
            },
            ensure_ascii=False,
        )

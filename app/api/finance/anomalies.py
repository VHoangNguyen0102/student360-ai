"""
Anomaly Alerts API — GET /api/v1/anomalies, PATCH /api/v1/anomalies/{id}/read
Read from the ai_anomaly_alerts table (written by the anomaly detection worker).
"""
from __future__ import annotations

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.database import get_pool
from app.utils.auth import verify_service_token

logger = structlog.get_logger()
router = APIRouter()


class AnomalyAlert(BaseModel):
    id: str
    user_id: str
    module_type: str
    alert_type: str
    target_id: Optional[str] = None
    description: str
    is_read: bool
    created_at: str


@router.get("/anomalies", response_model=list[AnomalyAlert])
async def get_anomaly_alerts(
    user_id: str,
    module_type: Optional[str] = None,
    is_read: Optional[bool] = None,
    _: str = Depends(verify_service_token),
) -> list[AnomalyAlert]:
    """Return anomaly alerts for a user (newest first, max 50)."""
    query = """
        SELECT id::text,
               user_id::text,
               module_type,
               alert_type,
               target_id,
               description,
               is_read,
               created_at::text
        FROM   ai_anomaly_alerts
        WHERE  user_id = $1
    """
    params: list = [user_id]

    if module_type is not None:
        params.append(module_type)
        query += f" AND module_type = ${len(params)}"

    if is_read is not None:
        params.append(is_read)
        query += f" AND is_read = ${len(params)}"

    query += " ORDER BY created_at DESC LIMIT 50"

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)

    return [AnomalyAlert(**dict(r)) for r in rows]


@router.patch("/anomalies/{alert_id}/read", status_code=204)
async def mark_alert_read(
    alert_id: str,
    user_id: str,
    _: str = Depends(verify_service_token),
) -> None:
    """Mark an anomaly alert as read.  Requires user_id for ownership check."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE ai_anomaly_alerts
            SET    is_read = true
            WHERE  id = $1::uuid
              AND  user_id = $2::uuid
            """,
            alert_id,
            user_id,
        )
    # asyncpg execute returns 'UPDATE N' string
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Alert not found")

"""
Classify API — POST /api/v1/classify, POST /api/v1/classify/override
3-step pipeline: exact keyword match → vector similarity → LLM fallback.
Port from: backend/src/modules/jars/ai_integration/classify.service.ts
"""
from __future__ import annotations

import asyncio
import json

import structlog
from fastapi import APIRouter, Depends, HTTPException

from app.agents.finance.prompts import CLASSIFY_SYSTEM_PROMPT
from app.core.database import get_pool
from app.core.embeddings import embed_query, embed_text
from app.core.llm import get_llm
from app.core.vector_store import find_similar_transaction, save_transaction_embedding
from app.models.classify import (
    ClassifyOverrideRequest,
    ClassifyRequest,
    ClassifyResponse,
    ClassifySource,
)
from app.utils.auth import verify_service_token

logger = structlog.get_logger()
router = APIRouter()

CONFIDENCE_THRESHOLD = 0.6


@router.post("/classify", response_model=ClassifyResponse)
async def classify(
    req: ClassifyRequest,
    _: str = Depends(verify_service_token),
) -> ClassifyResponse:
    """
    Classify a transaction description into a jar code.
    Priority: preference table → vector similarity → LLM.
    """
    keyword = req.description.lower().strip()

    # ────────────────────────────────────────────
    # Step 1: Exact keyword match (zero latency)
    # ────────────────────────────────────────────
    pool = await get_pool()
    async with pool.acquire() as conn:
        pref = await conn.fetchrow(
            "SELECT jar_code FROM ai_user_preferences_6jars WHERE user_id=$1 AND keyword=$2",
            req.user_id,
            keyword,
        )
    if pref:
        logger.debug("classify_preference_hit", keyword=keyword, jar_code=pref["jar_code"])
        return ClassifyResponse(
            suggested_jar_code=pref["jar_code"],
            confidence=1.0,
            source=ClassifySource.PREFERENCE,
        )

    # ────────────────────────────────────────────
    # Step 2: Vector similarity
    # ────────────────────────────────────────────
    query_vec = await embed_query(req.description)
    if query_vec:
        match = await find_similar_transaction(req.user_id, query_vec)
        if match:
            logger.debug(
                "classify_vector_hit",
                jar_code=match["jar_code"],
                similarity=match["similarity"],
                confirmed_by=match["confirmed_by"],
            )
            return ClassifyResponse(
                suggested_jar_code=match["jar_code"],
                confidence=match["similarity"],
                source=ClassifySource.VECTOR,
            )

    # ────────────────────────────────────────────
    # Step 3: LLM fallback
    # ────────────────────────────────────────────
    user_message = (
        f'Phân loại giao dịch sau vào đúng lọ:\n'
        f'Mô tả: "{req.description}"'
    )
    if req.amount:
        user_message += f"\nSố tiền: {req.amount} VND"

    llm = get_llm()
    try:
        response = await llm.ainvoke(
            [
                {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ]
        )
        content = response.content
    except Exception as exc:
        logger.warning("classify_llm_failed", error=str(exc))
        return ClassifyResponse(
            suggested_jar_code="essentials",
            confidence=0.0,
            source=ClassifySource.AI,
        )

    # Parse JSON response
    jar_code, confidence = "essentials", 0.0
    try:
        match_json = None
        for start in range(len(content)):
            if content[start] == "{":
                try:
                    parsed = json.loads(content[start:])
                    match_json = parsed
                    break
                except json.JSONDecodeError:
                    continue
        if match_json:
            jar_code = match_json.get("jar_code", "essentials")
            confidence = float(match_json.get("confidence", 0.0))
    except Exception:
        pass

    if confidence < CONFIDENCE_THRESHOLD:
        return ClassifyResponse(
            suggested_jar_code=None,
            confidence=confidence,
            source=ClassifySource.AI,
        )

    # Fire-and-forget: save embedding for future vector hits
    if query_vec:
        asyncio.ensure_future(
            save_transaction_embedding(req.user_id, req.description, jar_code, query_vec, "ai")
        )

    return ClassifyResponse(
        suggested_jar_code=jar_code,
        confidence=confidence,
        source=ClassifySource.AI,
    )


@router.post("/classify/override", status_code=204)
async def classify_override(
    req: ClassifyOverrideRequest,
    _: str = Depends(verify_service_token),
) -> None:
    """
    Save a user-confirmed jar for a keyword.
    Updates both preference table and transaction_embeddings with confirmed_by='user'.
    """
    keyword = req.keyword.lower().strip()
    pool = await get_pool()

    # Update preference table
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT id, count FROM ai_user_preferences_6jars WHERE user_id=$1 AND keyword=$2",
            req.user_id,
            keyword,
        )
        if existing:
            await conn.execute(
                "UPDATE ai_user_preferences_6jars SET jar_code=$1, count=$2 WHERE id=$3",
                req.jar_code,
                existing["count"] + 1,
                existing["id"],
            )
        else:
            await conn.execute(
                "INSERT INTO ai_user_preferences_6jars (user_id, keyword, jar_code, count) VALUES ($1,$2,$3,1)",
                req.user_id,
                keyword,
                req.jar_code,
            )

    # Save user-confirmed embedding (async, best-effort)
    async def _save_embedding():
        vec = await embed_text(req.keyword)
        if vec:
            await save_transaction_embedding(req.user_id, req.keyword, req.jar_code, vec, "user")

    asyncio.ensure_future(_save_embedding())


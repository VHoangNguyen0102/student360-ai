"""
Vector Store — raw asyncpg queries against pgvector tables.
Shares the same PostgreSQL as NestJS; no ORM.

Tables targeted:
  transaction_embeddings  — per-user transaction classification cache
"""
from __future__ import annotations

import structlog

from app.core.database import get_pool

logger = structlog.get_logger()

# Cosine similarity thresholds (mirror NestJS classify.service.ts)
USER_THRESHOLD = 0.92
AI_THRESHOLD = 0.88


def _vec_literal(embedding: list[float]) -> str:
    """Convert a Python list to a pgvector-compatible string: '[0.1,0.2,...]'."""
    return "[" + ",".join(f"{v:.8f}" for v in embedding) + "]"


async def find_similar_transaction(
    user_id: str,
    embedding: list[float],
    user_threshold: float = USER_THRESHOLD,
    ai_threshold: float = AI_THRESHOLD,
) -> dict | None:
    """
    Look up a similar transaction embedding for this user.
    Returns {'jar_code': str, 'similarity': float, 'confirmed_by': str} or None.
    """
    if not embedding:
        return None

    pool = await get_pool()
    vec = _vec_literal(embedding)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT jar_code,
                   confirmed_by,
                   1 - (embedding::vector <=> $1::vector) AS similarity
            FROM   transaction_embeddings
            WHERE  user_id = $2
            ORDER  BY embedding::vector <=> $1::vector
            LIMIT  1
            """,
            vec,
            user_id,
        )

    if row is None:
        return None

    sim = float(row["similarity"])
    threshold = user_threshold if row["confirmed_by"] == "user" else ai_threshold
    if sim >= threshold:
        return {
            "jar_code": row["jar_code"],
            "similarity": sim,
            "confirmed_by": row["confirmed_by"],
        }
    return None


async def save_transaction_embedding(
    user_id: str,
    description: str,
    jar_code: str,
    embedding: list[float],
    confirmed_by: str = "ai",
) -> None:
    """Insert a transaction embedding row; silently skip duplicates."""
    if not embedding:
        return

    pool = await get_pool()
    vec = _vec_literal(embedding)

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO transaction_embeddings
                    (user_id, description, jar_code, confirmed_by, embedding)
                VALUES ($1, $2, $3, $4, $5::vector)
                ON CONFLICT DO NOTHING
                """,
                user_id,
                description,
                jar_code,
                confirmed_by,
                vec,
            )
    except Exception as exc:
        logger.warning("save_embedding_failed", error=str(exc))


"""
Embedding Provider — uses gemini-embedding-001 (3072 dims) via google.genai SDK.
"""
from __future__ import annotations

from google import genai
from google.genai import types
import structlog

from app.config import settings

logger = structlog.get_logger()


def _get_client():
    return genai.Client(api_key=settings.GEMINI_API_KEY)


async def embed_text(text: str) -> list[float]:
    """Embed a single text string.  Returns [] on failure."""
    try:
        client = _get_client()
        result = client.models.embed_content(
            model=settings.GEMINI_EMBEDDING_MODEL,
            contents=text,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
            ),
        )
        return result.embeddings[0].values
    except Exception as exc:
        logger.warning("embedding_failed", error=str(exc), text_preview=text[:80])
        return []


async def embed_query(text: str) -> list[float]:
    """Embed a search query (task_type differs from document embedding)."""
    try:
        client = _get_client()
        result = client.models.embed_content(
            model=settings.GEMINI_EMBEDDING_MODEL,
            contents=text,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
            ),
        )
        return result.embeddings[0].values
    except Exception as exc:
        logger.warning("query_embedding_failed", error=str(exc))
        return []


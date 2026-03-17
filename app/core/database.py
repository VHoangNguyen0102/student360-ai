"""
asyncpg connection pool — shared across all request handlers.
Lazily initialised on first use so tests can skip the DB entirely.
"""
from __future__ import annotations

import asyncpg

from app.config import settings

_pool: asyncpg.Pool | None = None


def _dsn() -> str:
    """Convert SQLAlchemy-style URL to plain asyncpg DSN."""
    return (
        settings.DATABASE_URL
        .replace("postgresql+asyncpg://", "postgresql://")
        .replace("postgres+asyncpg://", "postgresql://")
    )


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            _dsn(),
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None

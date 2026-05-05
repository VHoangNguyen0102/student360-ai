from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator

_model_override: ContextVar[str | None] = ContextVar(
    "llm_model_override",
    default=None,
)


def get_model_override() -> str | None:
    return _model_override.get()


@contextmanager
def llm_model_override(model: str | None) -> Iterator[None]:
    normalized = (model or "").strip() or None
    token: Token[str | None] = _model_override.set(normalized)
    try:
        yield
    finally:
        _model_override.reset(token)

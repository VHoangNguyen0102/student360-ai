from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator, Literal

LlmProviderName = Literal["gemini", "vertexai", "ollama"]

_provider_override: ContextVar[LlmProviderName | None] = ContextVar(
    "llm_provider_override",
    default=None,
)


def get_provider_override() -> LlmProviderName | None:
    return _provider_override.get()


@contextmanager
def llm_provider_override(provider: str | None) -> Iterator[None]:
    if provider not in {"gemini", "vertexai", "ollama"}:
        # Invalid/unknown values are ignored to preserve backward compatibility.
        yield
        return

    token: Token[LlmProviderName | None] = _provider_override.set(provider)
    try:
        yield
    finally:
        _provider_override.reset(token)

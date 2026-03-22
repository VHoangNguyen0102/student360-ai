from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from app.core.llm.factory import get_chat_model


def get_llm(model: str | None = None, *, temperature: float = 0.1) -> BaseChatModel:
    """Return configured chat model (Gemini or Ollama per settings)."""
    return get_chat_model(model=model, temperature=temperature)


__all__ = ["get_chat_model", "get_llm", "BaseChatModel"]

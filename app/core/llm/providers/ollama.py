"""Local Ollama chat model via LangChain."""

from __future__ import annotations

from langchain_ollama import ChatOllama

from app.config import settings


def build_ollama_chat_model(model: str | None = None, temperature: float = 0.1) -> ChatOllama:
    return ChatOllama(
        model=model or settings.OLLAMA_MODEL,
        base_url=settings.OLLAMA_BASE_URL,
        temperature=temperature,
    )

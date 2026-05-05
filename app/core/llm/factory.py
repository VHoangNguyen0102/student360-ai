"""Select chat model implementation from settings (Gemini vs Ollama)."""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from app.config import settings
from app.core.llm.runtime_model import get_model_override
from app.core.llm.runtime_provider import get_provider_override
from app.core.llm.providers.gemini import build_gemini_chat_model
from app.core.llm.providers.ollama import build_ollama_chat_model
from app.core.llm.providers.vertexai import build_vertexai_chat_model


def get_chat_model(model: str | None = None, *, temperature: float = 0.1) -> BaseChatModel:
    provider = get_provider_override() or settings.LLM_PROVIDER
    selected_model = model or get_model_override()

    if provider == "ollama":
        return build_ollama_chat_model(model=selected_model, temperature=temperature)
    elif provider == "vertexai":
        return build_vertexai_chat_model(model=selected_model, temperature=temperature)
    return build_gemini_chat_model(model=selected_model, temperature=temperature)

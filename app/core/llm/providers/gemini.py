"""Gemini chat model via LangChain."""

from __future__ import annotations

from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import settings


def build_gemini_chat_model(model: str | None = None, temperature: float = 0.1) -> ChatGoogleGenerativeAI:
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is required when LLM_PROVIDER=gemini")
    return ChatGoogleGenerativeAI(
        model=model or settings.GEMINI_LLM_MODEL,
        google_api_key=settings.GEMINI_API_KEY,
        temperature=temperature,
    )

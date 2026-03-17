"""
LLM Provider — wraps Google Gemini via LangChain.
"""
from langchain_google_genai import ChatGoogleGenerativeAI
from app.config import settings


def get_llm(model: str | None = None) -> ChatGoogleGenerativeAI:
    """Return a configured Gemini LLM instance."""
    return ChatGoogleGenerativeAI(
        model=model or settings.GEMINI_LLM_MODEL,
        google_api_key=settings.GEMINI_API_KEY,
        temperature=0.1,
    )


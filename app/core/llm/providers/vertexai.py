from langchain_google_genai import ChatGoogleGenerativeAI
from app.config import settings

def build_vertexai_chat_model(model: str | None = None, temperature: float = 0.1) -> ChatGoogleGenerativeAI:
    """Build chat model using Vertex API key only."""
    vertex_api_key = (settings.VERTEX_API_KEY or "").strip()
    model_name = model or settings.VERTEX_LLM_MODEL

    if not vertex_api_key:
        raise ValueError("VERTEX_API_KEY is required when LLM_PROVIDER=vertexai")

    return ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=vertex_api_key,
        temperature=temperature,
    )

from langchain_google_vertexai import ChatVertexAI
from app.config import settings

def build_vertexai_chat_model(model: str | None = None, temperature: float = 0.1) -> ChatVertexAI:
    """Build Vertex AI chat model using service account."""
    if not settings.VERTEX_AI_PROJECT:
        raise ValueError("VERTEX_AI_PROJECT is required when LLM_PROVIDER=vertexai")

    if not settings.GOOGLE_APPLICATION_CREDENTIALS:
        raise ValueError("GOOGLE_APPLICATION_CREDENTIALS is required when LLM_PROVIDER=vertexai")

    model_name = model or settings.VERTEX_LLM_MODEL
    
    return ChatVertexAI(
        model_name=model_name,
        project=settings.VERTEX_AI_PROJECT,
        location=settings.VERTEX_AI_LOCATION,
        temperature=temperature,
        max_output_tokens=2048,
        streaming=True
    )

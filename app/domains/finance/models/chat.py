"""Pydantic request/response models for chat endpoints."""
from pydantic import BaseModel
from typing import Optional
from enum import Enum


class ContextHint(str, Enum):
    FINANCE = "finance"
    CAREER = "career"
    CONTENT = "content"
    AUTO = "auto"


class LlmProvider(str, Enum):
    GEMINI = "gemini"
    VERTEX_AI = "vertexai"
    OLLAMA = "ollama"


class ChatMessage(BaseModel):
    role: str
    content: str
    tool_calls: Optional[list] = None


class ChatRequest(BaseModel):
    user_id: str
    session_id: Optional[str] = None
    message: str
    history: Optional[list[ChatMessage]] = None
    context_hint: ContextHint = ContextHint.AUTO
    llm_provider: Optional[LlmProvider] = None
    llm_model: Optional[str] = None
    metadata: Optional[dict] = None


class ChatUsage(BaseModel):
    tokens_in: int
    tokens_out: int
    latency_ms: int


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    agent_used: list[str]
    usage: Optional[ChatUsage] = None
    # Intent classification metadata (for logging/debug — not used by frontend rendering)
    intent: Optional[str] = None        # knowledge_6jars | personal_finance | hybrid
    answer_mode: Optional[str] = None   # knowledge | personal | hybrid
    provider_used: Optional[str] = None
    model_used: Optional[str] = None


"""Pydantic request/response models for chat endpoints."""
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum

from app.domains.finance.models.action_proposal import ActionProposal


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
    enable_actions: bool = False


class ChatUsage(BaseModel):
    tokens_in: int
    tokens_out: int
    latency_ms: int


class ScholarshipRequirements(BaseModel):
    gpa: Optional[str] = None
    language: Optional[str] = None
    year_level: Optional[str] = None
    other: list[str] = Field(default_factory=list)


class ScholarshipRecommendationItem(BaseModel):
    id: str
    title: str
    country: Optional[str] = None
    university: Optional[str] = None
    provider: Optional[str] = None
    category: Optional[str] = None
    majors: list[str] = Field(default_factory=list)
    coverage: Optional[str] = None
    important_requirement: Optional[str] = None
    requirements: ScholarshipRequirements = Field(default_factory=ScholarshipRequirements)
    benefits: list[str] = Field(default_factory=list)
    deadline: Optional[str] = None
    target_audience: list[str] = Field(default_factory=list)
    match_reason: Optional[str] = None
    match_level: str
    match_score: Optional[float] = None


class ScholarshipRecommendations(BaseModel):
    kind: str = "scholarship_recommendations"
    basis: str = "profile_match"
    items: list[ScholarshipRecommendationItem] = Field(default_factory=list)


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
    actions: Optional[list[ActionProposal]] = None
    scholarship_recommendations: Optional[ScholarshipRecommendations] = None


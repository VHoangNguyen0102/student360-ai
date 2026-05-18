"""Pydantic models for scholarship fit analysis."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ScholarshipFitLevel = Literal["high", "medium", "low", "impossible"]
ScholarshipFitReasonSeverity = Literal[
    "positive",
    "warning",
    "improvable",
    "blocker",
    "unknown",
]
ScholarshipFitActionPriority = Literal["high", "medium", "low"]


class ScholarshipRecommendationSnapshot(BaseModel):
    id: str | None = None
    title: str | None = None
    match_level: str | None = None
    match_score: float | None = None
    match_reason: str | None = None
    important_requirement: str | None = None


class ScholarshipFitAnalysisRequest(BaseModel):
    user_id: str
    session_id: str | None = None
    recommendation_snapshot: ScholarshipRecommendationSnapshot | None = None
    force_refresh: bool = False


class ScholarshipFitReason(BaseModel):
    code: str
    severity: ScholarshipFitReasonSeverity
    message: str
    evidence: str | None = None


class ScholarshipFitAction(BaseModel):
    code: str
    priority: ScholarshipFitActionPriority
    message: str


class ScholarshipFitAnalysis(BaseModel):
    kind: str = "scholarship_fit_analysis"
    analysis_id: str
    scholarship_id: str
    user_id: str
    session_id: str | None = None
    fit_level: ScholarshipFitLevel
    fit_label: str
    fit_score: int = Field(ge=0, le=100)
    summary: str
    reasons: list[ScholarshipFitReason] = Field(default_factory=list)
    actions: list[ScholarshipFitAction] = Field(default_factory=list)
    hard_blockers: list[ScholarshipFitReason] = Field(default_factory=list)
    profile_snapshot: dict[str, Any] = Field(default_factory=dict)
    scholarship_snapshot: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime
    expires_at: datetime | None = None
    cached: bool = False

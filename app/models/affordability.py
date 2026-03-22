"""Pydantic models for affordability check endpoints."""
from pydantic import BaseModel
from typing import Optional
from enum import Enum


class AffordabilityRecommendation(str, Enum):
    YES = "yes"           # Safe to buy
    NO = "no"             # Will cause financial stress
    WAIT = "wait"         # Consider delaying


class AffordabilityCheckRequest(BaseModel):
    user_id: str
    description: str      # e.g., "New mechanical keyboard"
    amount: float         # VND
    context: Optional[str] = None  # e.g., "I have an exam next week"


class AffordabilityCheckResponse(BaseModel):
    recommendation: AffordabilityRecommendation
    reason: str           # Explanation for the recommendation
    suggested_jar: str    # Which jar this would come from
    jar_balance: float    # Current balance of that jar
    confidence: float     # 0.0 - 1.0

"""Pydantic models for transaction classify endpoints."""
from pydantic import BaseModel
from typing import Optional
from enum import Enum


class JarCode(str, Enum):
    ESSENTIALS = "essentials"
    ENJOYMENT = "enjoyment"
    EDUCATION = "education"
    INVESTMENT = "investment"
    RESERVE = "reserve"
    SHARING = "sharing"


class ClassifySource(str, Enum):
    PREFERENCE = "preference"   # exact keyword match
    VECTOR = "vector"           # user vector similarity
    AI = "ai"                   # LLM fallback


class ClassifyRequest(BaseModel):
    user_id: str
    description: str
    amount: Optional[float] = None


class ClassifyResponse(BaseModel):
    suggested_jar_code: Optional[JarCode]
    confidence: float
    source: ClassifySource


class ClassifyOverrideRequest(BaseModel):
    user_id: str
    keyword: str
    jar_code: JarCode

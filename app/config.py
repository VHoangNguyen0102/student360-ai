from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    ENV: Literal["local", "staging", "production"] = "local"

    # LLM provider: gemini, vertexai, or ollama
    LLM_PROVIDER: Literal["gemini", "vertexai", "ollama"] = "gemini"
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_MODEL: str = "qwen2.5:3b"

    # Gemini (used when LLM_PROVIDER=gemini)
    # Supports multiple keys for quota rotation: GEMINI_API_KEY=key1,key2,key3
    GEMINI_API_KEY: str = ""
    GEMINI_LLM_MODEL: str = "gemini-2.0-flash-lite"

    # Vertex AI (used when LLM_PROVIDER=vertexai)
    VERTEX_AI_PROJECT: str = ""
    VERTEX_AI_LOCATION: str = "us-central1"
    VERTEX_LLM_MODEL: str = "gemini-2.5-flash-lite"
    VERTEX_API_KEY: str = ""

    # PostgreSQL (shared with NestJS backend)
    DATABASE_URL: str  # postgresql+asyncpg://user:pass@host/db

    # Redis (shared with NestJS BullMQ)
    REDIS_URL: str = "redis://localhost:6379"

    # NestJS backend (internal service calls)
    BACKEND_URL: str = "http://localhost:3000"
    BACKEND_INTERNAL_API_KEY: str

    # Service auth (NestJS → this service)
    AI_SERVICE_SECRET: str

    # Rate limiting
    DAILY_CHAT_LIMIT: int = 50
    MINUTE_CHAT_LIMIT: int = 20

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

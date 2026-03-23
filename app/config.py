from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    ENV: Literal["local", "staging", "production"] = "local"

    # LLM provider: gemini (cloud) or ollama (local)
    LLM_PROVIDER: Literal["gemini", "ollama"] = "gemini"
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_MODEL: str = "qwen2.5:3b"

    # Gemini (used when LLM_PROVIDER=gemini)
    GEMINI_API_KEY: str = ""
    GEMINI_LLM_MODEL: str = "gemini-2.5-flash-lite"
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-001"

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

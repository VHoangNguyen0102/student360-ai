from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ENV: Literal["local", "staging", "production"] = "local"

    # LLM provider: gemini, vertexai, or ollama
    LLM_PROVIDER: Literal["gemini", "vertexai", "ollama"] = "vertexai"
    AI_PROVIDER_FALLBACK_ENABLED: bool = False
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_MODEL: str = "qwen2.5:3b"

    # Gemini (used when LLM_PROVIDER=gemini)
    # Supports multiple keys for quota rotation: GEMINI_API_KEY=key1,key2,key3
    GEMINI_API_KEY: str = ""
    GEMINI_LLM_MODEL: str = "gemini-2.0-flash-lite"

    # Vertex AI (used when LLM_PROVIDER=vertexai)
    VERTEX_AI_PROJECT: str = ""
    VERTEX_AI_LOCATION: str = "us-central1"
    # Optional endpoint host override, e.g. aiplatform.googleapis.com
    # If empty, host is derived from VERTEX_AI_LOCATION.
    VERTEX_AI_ENDPOINT_HOST: str = ""
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

    @property
    def GEMINI_API_KEYS(self) -> list[str]:
        """Backward-compatible list format for single or comma-separated Gemini keys."""
        raw = (self.GEMINI_API_KEY or "").strip()
        if not raw:
            return []
        return [k.strip() for k in raw.split(",") if k.strip()]


settings = Settings()

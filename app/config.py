"""Cấu hình ứng dụng (Settings) được đọc từ biến môi trường và file `.env`.

Ý tưởng chính:
- Dùng `pydantic-settings` để map ENV VAR → thuộc tính Python có type hint.
- Có default cho nhiều biến để chạy local dễ hơn.
- Một số biến *bắt buộc* (không có default). Thiếu là app sẽ lỗi ngay khi import.

File `.env`:
- Được đọc tự động nhờ `Settings.Config.env_file = ".env"`.
- Đường dẫn là *tương đối theo current working directory*.
    Vì vậy khi chạy uvicorn, nên chạy từ thư mục root `student360-ai/` (nơi có `.env`).

Gợi ý đọc nhanh:
- Nhìn biến nào KHÔNG có default (ví dụ `DATABASE_URL`) ⇒ bắt buộc phải set.
- Nhìn `LLM_PROVIDER` ⇒ quyết định gọi Gemini (cloud) hay Ollama (local).
"""

from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Môi trường triển khai. Thường dùng để bật/tắt logging, strictness, v.v.
    ENV: Literal["local", "staging", "production"] = "local"

    # LLM provider: gemini, vertexai, or ollama
    LLM_PROVIDER: Literal["gemini", "vertexai", "ollama"] = "gemini"
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"

    # Tên model Ollama (ví dụ: qwen2.5:3b). Phải được `ollama pull` sẵn.
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

    # PostgreSQL (shared với NestJS backend)
    # BẮT BUỘC: không có default ⇒ thiếu là app sẽ error khi tạo Settings().
    # Format thường dùng với SQLAlchemy asyncio + asyncpg:
    #   postgresql+asyncpg://user:pass@host:5432/dbname
    DATABASE_URL: str

    # Redis (shared với NestJS BullMQ). Có default để chạy local dễ.
    REDIS_URL: str = "redis://localhost:6379"

    # NestJS backend (nơi AI service gọi nội bộ để lấy dữ liệu, đồng bộ, v.v.)
    BACKEND_URL: str = "http://localhost:3000"

    # BẮT BUỘC: API key nội bộ để gọi vào NestJS backend.
    BACKEND_INTERNAL_API_KEY: str

    # BẮT BUỘC: secret để xác thực chiều ngược lại (NestJS → AI service).
    # Thường được gửi như header/bearer tùy `app/utils/auth.py` đang kiểm.
    AI_SERVICE_SECRET: str

    # Chọn sub-agent/prompt cho domain Finance.
    # - six_jars: trợ lý 6 lọ (mặc định)
    # - scholarships: trợ lý học bổng (scaffold)
    # - combined: ghép prompt + tools của cả hai
    FINANCE_AGENT_MODE: Literal["six_jars", "scholarships", "combined"] = "six_jars"

    # Giới hạn rate (logic rate-limit thường nằm ở middleware/dependency).
    DAILY_CHAT_LIMIT: int = 50
    MINUTE_CHAT_LIMIT: int = 20

    class Config:
        # Tự load biến môi trường từ file `.env`.
        # Có thể override bằng env var thật của OS/container nếu trùng tên.
        env_file = ".env"
        env_file_encoding = "utf-8"


# Singleton settings: import ở mọi nơi.
# Lưu ý: dòng này chạy ngay khi module import ⇒ thiếu biến bắt buộc là fail sớm.
settings = Settings()

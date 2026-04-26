"""Entry point (ASGI) cho ứng dụng FastAPI.

File này chịu trách nhiệm:
- Khởi tạo `FastAPI` app.
- Khai báo vòng đời app (startup/shutdown) qua `lifespan`.
- Gắn (include) các router API từ các module con.
- Cung cấp endpoint kiểm tra sức khoẻ (`/health`).

Thường bạn sẽ chạy app thông qua uvicorn trỏ tới `app.main:app`.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from app.api.finance import anomalies, chat, classify, insights
from app.api.career import router as career_router
from app.api.elearning import router as elearning_router

# Cấu hình chạy app (ENV, keys, v.v.) lấy từ `app.config.settings`.
from app.config import settings

# Đóng connection pool DB khi app shutdown để tránh leak connection.
from app.core.database import close_pool

# Logger theo chuẩn structured logging.
import structlog

# Tạo logger dùng xuyên suốt file.
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "student360-ai starting",
        env=settings.ENV,
        llm_provider_default=settings.LLM_PROVIDER,
        gemini_model=settings.GEMINI_LLM_MODEL,
        vertex_model=settings.VERTEX_LLM_MODEL,
        ollama_model=settings.OLLAMA_MODEL,
        ollama_base_url=settings.OLLAMA_BASE_URL,
    )
    yield

    # Shutdown: đóng DB pool để giải phóng tài nguyên.
    await close_pool()
    logger.info("student360-ai shutting down")


# Khởi tạo đối tượng FastAPI (ASGI app).
# - `title`, `version` dùng cho OpenAPI/Swagger UI
# - `lifespan` gắn lifecycle handler ở trên
app = FastAPI(
    title="student360-ai",
    version="0.1.0",
    lifespan=lifespan,
)

# Gắn các router vào app.
# `prefix` quyết định base path cho nhóm endpoint.
# `tags` dùng để nhóm endpoint trong Swagger UI.
#
# Phase 1 — 6 Jars (tên phase/feature trong dự án)
app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
app.include_router(classify.router, prefix="/api/v1", tags=["classify"])
app.include_router(anomalies.router, prefix="/api/v1", tags=["anomalies"])
app.include_router(insights.router, prefix="/api/v1", tags=["insights"])
app.include_router(career_router, prefix="/api/v1/career", tags=["career"])
app.include_router(elearning_router, prefix="/api/v1/elearning", tags=["elearning"])


@app.get("/health")
async def health():
    # Endpoint đơn giản để:
    # - load balancer/k8s probe kiểm tra service sống
    # - CI/CD hoặc monitoring ping nhanh
    return {"status": "ok", "version": "0.1.0"}

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

# Import các router/endpoint theo từng domain.
# Ở đây `chat/classify/anomalies` nằm trong nhóm finance API v1.
from app.api.finance import anomalies, chat, classify

# Router cho career và elearning được export dưới tên `router` trong từng package.
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
    """Lifecycle hook cho FastAPI.

    FastAPI sẽ gọi hàm này:
    - Trước khi nhận request đầu tiên (startup)
    - Và khi server chuẩn bị dừng (shutdown)

    Quy ước của `asynccontextmanager`:
    - Code trước `yield` chạy ở startup
    - `yield` giao quyền cho app xử lý request
    - Code sau `yield` chạy ở shutdown
    """

    # Startup: log môi trường đang chạy (dev/staging/prod...)
    logger.info("student360-ai starting", env=settings.ENV)

    # Ở đây không mở DB pool vì pool thường được lazy-init ở nơi khác.
    # Nếu dự án cần init tài nguyên ở startup, đây là nơi phù hợp.
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

# Hai router dưới đây tự có prefix riêng cấp module (career/elearning)
# nên ở đây prefix đã bao gồm luôn phần path con.
app.include_router(career_router, prefix="/api/v1/career", tags=["career"])
app.include_router(elearning_router, prefix="/api/v1/elearning", tags=["elearning"])


@app.get("/health")
async def health():
    # Endpoint đơn giản để:
    # - load balancer/k8s probe kiểm tra service sống
    # - CI/CD hoặc monitoring ping nhanh
    return {"status": "ok", "version": "0.1.0"}

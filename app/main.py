from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.v1 import anomalies, chat, classify
from app.config import settings
from app.core.database import close_pool
import structlog

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("student360-ai starting", env=settings.ENV)
    yield
    await close_pool()
    logger.info("student360-ai shutting down")


app = FastAPI(
    title="student360-ai",
    version="0.1.0",
    lifespan=lifespan,
)

# Phase 1 — 6 Jars
app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
app.include_router(classify.router, prefix="/api/v1", tags=["classify"])
app.include_router(anomalies.router, prefix="/api/v1", tags=["anomalies"])

# Phase B+ (uncomment when ready)
# from app.api.v1 import career, content, receipt, feed, internal
# app.include_router(career.router, prefix="/api/v1", tags=["career"])
# app.include_router(content.router, prefix="/api/v1", tags=["content"])


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}

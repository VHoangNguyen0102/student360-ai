from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.finance import anomalies, chat, classify, insights
from app.api.career import router as career_router
from app.api.elearning import router as elearning_router
from app.config import settings
from app.core.database import close_pool
import structlog

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
app.include_router(insights.router, prefix="/api/v1", tags=["insights"])
app.include_router(career_router, prefix="/api/v1/career", tags=["career"])
app.include_router(elearning_router, prefix="/api/v1/elearning", tags=["elearning"])


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}

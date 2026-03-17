# Internal webhook endpoints — called by NestJS after async tasks complete
# TODO: Phase 1C — implement /internal/anomaly-done, /internal/embedding-done
from fastapi import APIRouter
router = APIRouter()

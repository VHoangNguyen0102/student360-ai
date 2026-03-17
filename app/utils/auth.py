"""Service-to-service authentication middleware."""
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.config import settings

security = HTTPBearer()


def verify_service_token(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> str:
    if credentials.credentials != settings.AI_SERVICE_SECRET:
        raise HTTPException(status_code=401, detail="Invalid service token")
    return credentials.credentials

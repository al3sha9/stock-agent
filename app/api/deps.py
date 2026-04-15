from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
from app.core.config import get_settings

settings = get_settings()

api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=True)

def get_api_key(api_key: str = Security(api_key_header)) -> str:
    """Validate the incoming API key against the configured settings."""
    if not settings.API_KEY or api_key != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate API key",
        )
    return api_key

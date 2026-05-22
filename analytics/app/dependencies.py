"""
Shared FastAPI dependencies — auth, cache, rate limiting.
"""

from __future__ import annotations

from typing import Annotated, Optional

import structlog
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from core.auth import get_current_user, verify_api_key, verify_jwt_token
from core.cache import cache

logger = structlog.get_logger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


# ── Auth dependencies ─────────────────────────────────────────────────────────

async def get_api_key(
    x_api_key: Annotated[Optional[str], Header(alias="X-API-Key")] = None,
) -> str:
    """Validate X-API-Key header."""
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_REQUIRED", "message": "X-API-Key header is required."},
        )
    tier = await verify_api_key(x_api_key)
    if tier is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_REQUIRED", "message": "Invalid API key."},
        )
    return x_api_key


async def get_jwt_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer_scheme)] = None,
) -> dict:
    """Validate Bearer JWT token."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_REQUIRED", "message": "Bearer token is required."},
        )
    payload = verify_jwt_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_REQUIRED", "message": "Invalid or expired token."},
        )
    return payload


async def get_optional_auth(
    x_api_key: Annotated[Optional[str], Header(alias="X-API-Key")] = None,
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer_scheme)] = None,
) -> Optional[str]:
    """Accept either API key or JWT — returns API key string or None."""
    if x_api_key:
        tier = await verify_api_key(x_api_key)
        if tier:
            return x_api_key
    if credentials:
        payload = verify_jwt_token(credentials.credentials)
        if payload:
            return payload.get("sub")
    return None


# ── Cache dependency ──────────────────────────────────────────────────────────

def get_cache():
    return cache


# ── Type aliases for cleaner endpoint signatures ──────────────────────────────

ApiKeyDep = Annotated[str, Depends(get_api_key)]
JwtUserDep = Annotated[dict, Depends(get_jwt_user)]
OptionalAuthDep = Annotated[Optional[str], Depends(get_optional_auth)]

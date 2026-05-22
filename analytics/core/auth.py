"""
Authentication: JWT bridge (QuantDinger ↔ Analytics) + API key validation.

Two JWT token types are accepted:
  1. QuantDinger JWT — issued by QuantDinger Flask backend, verified with
     QUANTDINGER_JWT_SECRET (shared HS256 secret).  Enabled only when
     settings.QUANTDINGER_JWT_SECRET is non-empty.
  2. Analytics-native JWT — issued by this service via create_analytics_jwt(),
     verified with JWT_SECRET_KEY.

FastAPI dependency ``get_current_user`` accepts both token types and returns a
normalised ``User`` dict.  Master API key (MASTER_API_KEY) bypasses JWT checks
for admin operations.

See design.md "Auth flow chia sẻ" and requirements.md §0.3.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

import structlog
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import settings
from core.cache import cache

logger = structlog.get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

API_KEY_PREFIX = "fincept_"
TIER_FREE = "free"
TIER_PAID = "paid"
TIER_ADMIN = "admin"

# Cache TTL for user lookups (seconds) — Requirement 0.3 §4
_USER_CACHE_TTL = 300  # 5 minutes

# Cache TTL for JWT verification results (seconds) — Requirement 1.6
_JWT_CACHE_TTL = 300  # 5 minutes

# Token source tag stored in the normalised User dict
_SOURCE_QUANTDINGER = "quantdinger"
_SOURCE_ANALYTICS = "analytics"
_SOURCE_MASTER_KEY = "master_key"


# ── User model (dict schema) ──────────────────────────────────────────────────
#
# get_current_user always returns a dict with at least:
#   sub       : str   — user identifier (UUID string from QuantDinger or Analytics)
#   role      : str   — "user" | "admin" | "paid" | …
#   source    : str   — which auth path was used
#   email     : str   — optional, may be empty string
#   exp       : int   — expiry epoch (0 for master key)


# ── API Key helpers ───────────────────────────────────────────────────────────

def generate_api_key(tier: str = TIER_FREE) -> str:
    """Generate a new API key for the given tier."""
    random_part = secrets.token_hex(32)
    return f"{API_KEY_PREFIX}{tier}_{random_part}"


def _hash_key(api_key: str) -> str:
    """Hash an API key for storage (never store raw keys)."""
    return hashlib.sha256(api_key.encode()).hexdigest()


async def verify_api_key(api_key: str) -> Optional[str]:
    """
    Verify an API key and return its tier, or None if invalid.

    Master API key (MASTER_API_KEY) is always valid as admin tier.
    Other well-formed keys are accepted as their embedded tier (dev/test only).
    """
    if not api_key or not api_key.startswith(API_KEY_PREFIX):
        return None

    # Master key bypass — admin tier
    if settings.MASTER_API_KEY and api_key == settings.MASTER_API_KEY:
        return TIER_ADMIN

    # Check Redis cache for known keys
    cache_key = f"{settings.REDIS_KEY_PREFIX}apikey:{_hash_key(api_key)}"
    cached_tier = await cache.get(cache_key)
    if cached_tier:
        return cached_tier

    # TODO: In production, check database here.
    # For now, accept any well-formed key as its embedded tier.
    parts = api_key.split("_")
    if len(parts) >= 3:
        tier = parts[1]
        if tier in (TIER_FREE, TIER_PAID, TIER_ADMIN):
            await cache.set(cache_key, tier, ttl=300)
            return tier

    return None


async def register_api_key(api_key: str, tier: str) -> bool:
    """Register an API key in the cache (for testing/dev)."""
    cache_key = f"{settings.REDIS_KEY_PREFIX}apikey:{_hash_key(api_key)}"
    return await cache.set(cache_key, tier, ttl=86400)  # 24 h


# ── Analytics-native JWT ──────────────────────────────────────────────────────

def create_analytics_jwt(
    user_id: str,
    role: str = "user",
    email: str = "",
    extra_claims: Optional[dict] = None,
    expire_minutes: Optional[int] = None,
) -> str:
    """
    Create an Analytics-native JWT token.

    Args:
        user_id:        Subject identifier (UUID string).
        role:           User role — "user" | "admin" | "paid".
        email:          Optional email claim.
        extra_claims:   Additional claims merged into the payload.
        expire_minutes: Override default expiry (JWT_EXPIRE_MINUTES).

    Returns:
        Signed HS256 JWT string.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expire_minutes if expire_minutes is not None else settings.JWT_EXPIRE_MINUTES
    )
    payload: dict = {
        "sub": user_id,
        "role": role,
        "email": email,
        "source": _SOURCE_ANALYTICS,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


# Keep backward-compatible alias used by existing code / tests
def create_jwt_token(
    subject: str,
    extra_claims: Optional[dict] = None,
    expire_minutes: Optional[int] = None,
) -> str:
    """Backward-compatible wrapper around create_analytics_jwt."""
    return create_analytics_jwt(
        user_id=subject,
        extra_claims=extra_claims,
        expire_minutes=expire_minutes,
    )


def verify_analytics_jwt(token: str) -> Optional[dict]:
    """
    Verify an Analytics-native JWT and return its payload, or None if invalid.

    Uses JWT_SECRET_KEY / JWT_ALGORITHM from settings.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except JWTError as exc:
        logger.debug("analytics_jwt.verify_failed", error=str(exc))
        return None


# Keep backward-compatible alias
def verify_jwt_token(token: str) -> Optional[dict]:
    """Backward-compatible alias for verify_analytics_jwt."""
    return verify_analytics_jwt(token)


# ── QuantDinger JWT bridge ────────────────────────────────────────────────────

def verify_quantdinger_jwt(token: str) -> Optional[dict]:
    """
    Verify a JWT issued by QuantDinger Flask backend.

    Uses QUANTDINGER_JWT_SECRET / QUANTDINGER_JWT_ALGORITHM from settings.
    Returns the decoded claims dict, or None if the bridge is disabled or the
    token is invalid.

    The bridge is disabled (returns None immediately) when
    settings.QUANTDINGER_JWT_SECRET is empty — callers should fall through to
    the Analytics-native verifier in that case.

    Expected QuantDinger JWT payload (confirm against Flask source):
        sub   : user UUID string
        email : user email
        role  : "user" | "admin" | …
        exp   : expiry epoch
    """
    if not settings.quantdinger_jwt_enabled:
        return None

    try:
        payload = jwt.decode(
            token,
            settings.QUANTDINGER_JWT_SECRET,
            algorithms=[settings.QUANTDINGER_JWT_ALGORITHM],
        )
        return payload
    except JWTError as exc:
        logger.debug("quantdinger_jwt.verify_failed", error=str(exc))
        return None


# ── Normalise claims → User dict ──────────────────────────────────────────────

def _normalise_user(claims: dict, source: str) -> dict:
    """
    Normalise raw JWT claims into a consistent User dict regardless of source.

    QuantDinger and Analytics JWTs may use slightly different claim names.
    This function produces a stable shape for downstream code.

    For QuantDinger JWTs:
      - ``sub`` is the username (e.g. "quantdinger") — NOT a unique user id.
      - ``user_id`` is the actual unique integer user id from qd_users.id.
      - We use ``str(user_id)`` as the internal identifier (``sub`` in User dict).

    For Analytics-native JWTs:
      - ``sub`` is already the user identifier (UUID string).
    """
    if source == _SOURCE_QUANTDINGER:
        # QD JWT: prefer user_id (integer) as the unique identifier
        raw_user_id = claims.get("user_id") or claims.get("id") or claims.get("sub") or ""
        sub = str(raw_user_id)
    else:
        # Analytics-native or other: use sub directly
        sub = str(
            claims.get("sub")
            or claims.get("user_id")
            or claims.get("id")
            or ""
        )

    role = claims.get("role") or claims.get("tier") or "user"
    email = claims.get("email") or ""
    exp = claims.get("exp") or 0

    return {
        "sub": sub,
        "role": str(role),
        "email": str(email),
        "source": source,
        "exp": int(exp),
        # Preserve all original claims for downstream use
        "_raw": claims,
    }


# ── Redis user-lookup cache ───────────────────────────────────────────────────

async def _cache_user(user_id: str, user: dict) -> None:
    """Cache a normalised user dict in Redis for _USER_CACHE_TTL seconds."""
    key = f"{settings.REDIS_KEY_PREFIX}user:{user_id}"
    await cache.set(key, user, ttl=_USER_CACHE_TTL)


async def _get_cached_user(user_id: str) -> Optional[dict]:
    """Return a cached user dict, or None on miss."""
    key = f"{settings.REDIS_KEY_PREFIX}user:{user_id}"
    return await cache.get(key)


# ── Redis JWT verification cache ──────────────────────────────────────────────
# Requirement 1.6: Cache verified JWT results to avoid re-verifying every request.
# Key format: analytics:jwt_cache:{first 16 chars of SHA256(token)}
# Only successful verifications are cached. Expired/invalid tokens are NOT cached.


def _jwt_cache_key(token: str) -> str:
    """Build Redis cache key for a JWT token using first 16 chars of SHA256."""
    token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
    return f"{settings.REDIS_KEY_PREFIX}jwt_cache:{token_hash}"


async def _get_cached_jwt_user(token: str) -> Optional[dict]:
    """
    Return cached verified user dict for a JWT token, or None on miss.

    Also checks that the cached result has not expired (exp claim) to prevent
    serving stale tokens from cache after they've expired.
    """
    key = _jwt_cache_key(token)
    cached = await cache.get(key)
    if cached is None:
        return None

    # Safety check: ensure the token hasn't expired since it was cached
    exp = cached.get("exp", 0)
    if exp and exp < int(datetime.now(timezone.utc).timestamp()):
        # Token expired — evict from cache and return None
        await cache.delete(key)
        logger.debug("jwt_cache.expired_evict", key=key)
        return None

    return cached


async def _cache_jwt_user(token: str, user: dict) -> None:
    """
    Cache a verified+normalised user dict keyed by token hash.

    TTL is _JWT_CACHE_TTL (300s) but will also be bounded by the token's
    own expiry to avoid serving expired tokens from cache.
    """
    exp = user.get("exp", 0)
    now_ts = int(datetime.now(timezone.utc).timestamp())

    if exp and exp <= now_ts:
        # Token already expired — do NOT cache
        return

    if exp and exp > now_ts:
        # Use the lesser of _JWT_CACHE_TTL and time-until-expiry
        remaining = exp - now_ts
        ttl = min(_JWT_CACHE_TTL, remaining)
    else:
        # No exp claim (exp == 0) — use default TTL
        ttl = _JWT_CACHE_TTL

    if ttl <= 0:
        return

    key = _jwt_cache_key(token)
    await cache.set(key, user, ttl=ttl)


# ── FastAPI dependency ────────────────────────────────────────────────────────

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Annotated[
        Optional[HTTPAuthorizationCredentials], Depends(_bearer_scheme)
    ] = None,
    x_api_key: Annotated[Optional[str], Header(alias="X-API-Key")] = None,
) -> dict:
    """
    FastAPI dependency — resolve the current authenticated user.

    Resolution order:
      1. Master API key (X-API-Key header == MASTER_API_KEY) → admin user bypass.
      2. Bearer JWT verified as QuantDinger token (when bridge is enabled).
      3. Bearer JWT verified as Analytics-native token.
      4. Any other X-API-Key (non-master) → tier-based pseudo-user.

    On success returns a normalised User dict (see _normalise_user).
    On failure raises HTTP 401 with code AUTH_REQUIRED.

    Requirement 0.3: JWT invalid → 401 AUTH_REQUIRED.
    Requirement 0.3: Cache user lookup in Redis 5 min.
    """
    # ── 1. Master API key bypass ──────────────────────────────────────────────
    if x_api_key and settings.MASTER_API_KEY and x_api_key == settings.MASTER_API_KEY:
        logger.debug("auth.master_key_bypass")
        return {
            "sub": "master",
            "role": TIER_ADMIN,
            "email": "",
            "source": _SOURCE_MASTER_KEY,
            "exp": 0,
            "_raw": {},
        }

    # ── 2 & 3. Bearer JWT ─────────────────────────────────────────────────────
    if credentials:
        token = credentials.credentials

        # Check JWT verification cache first (Requirement 1.6)
        # This avoids re-verifying the same token on every request.
        cached_jwt_user = await _get_cached_jwt_user(token)
        if cached_jwt_user is not None:
            logger.debug(
                "auth.jwt_cache_hit",
                user_id=cached_jwt_user.get("sub"),
                source=cached_jwt_user.get("source"),
            )
            return cached_jwt_user

        # Try QuantDinger bridge first (when configured)
        claims = verify_quantdinger_jwt(token)
        if claims is not None:
            user = _normalise_user(claims, _SOURCE_QUANTDINGER)
            user_id = user["sub"]
            # Cache by token hash (Requirement 1.6 — TTL 300s)
            await _cache_jwt_user(token, user)
            # Also cache by user_id for other lookups
            await _cache_user(user_id, user)
            logger.debug("auth.quantdinger_jwt_ok", user_id=user_id)
            return user

        # Try Analytics-native JWT
        claims = verify_analytics_jwt(token)
        if claims is not None:
            user = _normalise_user(claims, _SOURCE_ANALYTICS)
            user_id = user["sub"]
            # Cache by token hash (TTL 300s)
            await _cache_jwt_user(token, user)
            # Also cache by user_id for other lookups
            await _cache_user(user_id, user)
            logger.debug("auth.analytics_jwt_ok", user_id=user_id)
            return user

        # Token present but invalid — do NOT cache failures
        logger.info("auth.invalid_token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "AUTH_REQUIRED",
                "message": "Invalid or expired token.",
            },
        )

    # ── 4. Non-master API key ─────────────────────────────────────────────────
    if x_api_key:
        tier = await verify_api_key(x_api_key)
        if tier:
            return {
                "sub": f"apikey:{_hash_key(x_api_key)[:12]}",
                "role": tier,
                "email": "",
                "source": "api_key",
                "exp": 0,
                "_raw": {},
            }

    # ── No credentials ────────────────────────────────────────────────────────
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "AUTH_REQUIRED",
            "message": "Authentication required. Provide a Bearer token or X-API-Key.",
        },
    )


# ── Role / scope helpers ──────────────────────────────────────────────────────

def require_role(*roles: str):
    """
    Return a FastAPI dependency that enforces one of the given roles.

    Usage::

        @router.post("/admin/action")
        async def admin_action(user: dict = Depends(require_role("admin"))):
            ...
    """
    async def _check(user: Annotated[dict, Depends(get_current_user)]) -> dict:
        if user["role"] not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "FORBIDDEN",
                    "message": f"Role '{user['role']}' is not authorised. Required: {list(roles)}.",
                },
            )
        return user

    return _check


# ── Type alias for cleaner endpoint signatures ────────────────────────────────

CurrentUser = Annotated[dict, Depends(get_current_user)]

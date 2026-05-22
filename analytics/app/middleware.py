"""
ASGI middleware: structured logging, rate limiting, audit logging.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Callable

import structlog
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from core.cache import cache
from core.metrics import HTTP_IN_FLIGHT, record_request
from core.security import RateLimiter, get_endpoint_rate_limit

logger = structlog.get_logger(__name__)

# Module-level RateLimiter singleton (shares the cache singleton)
_rate_limiter = RateLimiter(cache)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Attach request_id, log every request with latency."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        start = time.perf_counter()
        HTTP_IN_FLIGHT.inc()
        try:
            response = await call_next(request)
        finally:
            HTTP_IN_FLIGHT.dec()

        latency_ms = round((time.perf_counter() - start) * 1000, 2)

        logger.info(
            "http.request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            latency_ms=latency_ms,
            request_id=request_id,
            client=request.client.host if request.client else "unknown",
        )

        # Record Prometheus metric
        record_request(request.method, request.url.path, response.status_code, latency_ms / 1000)

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{latency_ms}ms"
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding-window rate limiter backed by Redis.

    Limits are per authenticated user_id (JWT ``sub`` claim).
    Falls back to client IP when no JWT is present (unauthenticated requests).

    Limits per Requirement 6.1:
      - Default:   60 req/min
      - Agent run: 10 req/min
      - Heavy job:  1 req/min  (ML training)

    Response headers on every request:
      X-RateLimit-Limit     — applicable limit for this endpoint
      X-RateLimit-Remaining — remaining requests in current window

    Additional header on 429:
      Retry-After — seconds until the window resets
    """

    EXEMPT_PATHS = {"/health", "/", "/docs", "/redoc", "/openapi.json"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        # ── Resolve user_id from JWT (best-effort, no hard auth here) ─────────
        # The middleware runs before route auth dependencies, so we attempt a
        # lightweight JWT decode.  On failure we fall back to client IP so that
        # unauthenticated requests are still rate-limited.
        user_id = self._extract_user_id(request)

        # ── Check rate limit via RateLimiter ──────────────────────────────────
        allowed, limit, remaining, retry_after = await _rate_limiter.check(
            user_id=user_id,
            path=request.url.path,
            default_limit=settings.RATE_LIMIT_FREE,
        )

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": f"Rate limit exceeded. Max {limit} requests/minute.",
                        "details": {"limit": limit, "window": "1m"},
                    }
                },
                headers={
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "Retry-After": str(retry_after),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_user_id(request: Request) -> str:
        """
        Extract user_id from the Bearer JWT without raising on failure.

        Resolution order:
          1. Bearer JWT → ``sub`` claim (QuantDinger or Analytics token).
          2. Client IP address as fallback for unauthenticated requests.

        This is intentionally lightweight — full auth validation happens in
        route dependencies.  We only need a stable identifier for bucketing.
        """
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                # Try Analytics-native JWT first (most common path)
                from core.auth import verify_analytics_jwt, verify_quantdinger_jwt

                claims = verify_analytics_jwt(token)
                if claims is None and settings.quantdinger_jwt_enabled:
                    claims = verify_quantdinger_jwt(token)
                if claims:
                    sub = (
                        claims.get("sub")
                        or claims.get("user_id")
                        or claims.get("id")
                    )
                    if sub:
                        return str(sub)
            except Exception:
                pass  # Fall through to IP fallback

        # Fallback: use client IP (rate-limits unauthenticated callers by IP)
        return request.client.host if request.client else "unknown"


# ── Audit methods that must be logged ────────────────────────────────────────
_AUDIT_METHODS = {"POST", "DELETE"}


class AuditLogMiddleware(BaseHTTPMiddleware):
    """
    Intercept every POST and DELETE request and write an entry to
    analytics.audit_log after the response is sent.

    The write is fire-and-forget (asyncio.create_task) so it never adds
    latency to the response path.

    Fields recorded per Requirement 0.8:
      user_id    — JWT ``sub`` claim (extracted from request.state if set by
                   a prior auth dependency, otherwise None)
      action     — "<METHOD> <path>", e.g. "POST /api/v1/agents/run"
      resource   — request path
      request_id — UUID set by LoggingMiddleware on request.state
      ip         — client IP
      ts         — set by the DB server_default (now())

    Exempt paths (health, docs, metrics) are skipped.
    """

    EXEMPT_PATHS = {"/health", "/", "/docs", "/redoc", "/openapi.json", "/metrics"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        if request.method not in _AUDIT_METHODS:
            return response

        if request.url.path in self.EXEMPT_PATHS:
            return response

        # Collect fields — all are best-effort; failures must not crash.
        try:
            from core.audit import record_audit  # local import avoids circular deps

            # request_id is set by LoggingMiddleware which runs before us
            request_id: str | None = getattr(request.state, "request_id", None)

            # user_id is set by auth dependencies on individual routes.
            # The middleware runs before route handlers, so we can only read
            # it if a previous middleware or dependency already resolved it.
            # For most cases it will be None here; the audit entry is still
            # useful for IP/action tracking even without a user_id.
            user_id: str | None = None
            user = getattr(request.state, "user", None)
            if user and isinstance(user, dict):
                user_id = user.get("sub")

            ip: str | None = request.client.host if request.client else None
            action = f"{request.method} {request.url.path}"
            resource = request.url.path

            # Fire-and-forget — do not await
            asyncio.create_task(
                record_audit(
                    action=action,
                    resource=resource,
                    user_id=user_id,
                    request_id=request_id,
                    ip=ip,
                )
            )
        except Exception as exc:
            logger.error("audit_middleware.error", error=str(exc))

        return response

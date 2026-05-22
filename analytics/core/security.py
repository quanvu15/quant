"""
Security hardening utilities — P6-T3.

- Input sanitization (strip dangerous chars from string inputs)
- HMAC request signing for sensitive endpoints
- Per-endpoint rate limit overrides (per user_id, not API key)
- API key rotation helpers
- RateLimiter: sliding-window per user_id backed by Redis
"""
from __future__ import annotations

import hashlib
import hmac
import re
import time
from typing import Any, Dict, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)

# ── Input sanitization ────────────────────────────────────────────────────────

# Characters that could be dangerous in subprocess args or log injection
_DANGEROUS_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")  # control chars
_SCRIPT_INJECTION = re.compile(r"[;&|`$<>]")  # shell metacharacters


def sanitize_string(value: str, max_length: int = 10000) -> str:
    """
    Strip control characters and limit length.
    Does NOT strip shell metacharacters from query text (LLM queries need them).
    """
    if not isinstance(value, str):
        return str(value)[:max_length]
    cleaned = _DANGEROUS_PATTERN.sub("", value)
    return cleaned[:max_length]


def sanitize_symbol(symbol: str) -> str:
    """Sanitize a ticker symbol — only allow alphanumeric, dot, dash, caret."""
    cleaned = re.sub(r"[^A-Za-z0-9.\-^]", "", symbol)
    return cleaned[:20].upper()


def sanitize_script_arg(value: str) -> str:
    """
    Sanitize a value that will be passed as a subprocess argument.
    Strips shell metacharacters.
    """
    cleaned = _DANGEROUS_PATTERN.sub("", value)
    cleaned = _SCRIPT_INJECTION.sub("", cleaned)
    return cleaned[:500]


def sanitize_dict(data: Dict[str, Any], max_depth: int = 5) -> Dict[str, Any]:
    """Recursively sanitize string values in a dict."""
    if max_depth <= 0:
        return {}
    result = {}
    for k, v in data.items():
        safe_key = sanitize_string(str(k), max_length=100)
        if isinstance(v, str):
            result[safe_key] = sanitize_string(v)
        elif isinstance(v, dict):
            result[safe_key] = sanitize_dict(v, max_depth - 1)
        elif isinstance(v, list):
            result[safe_key] = [
                sanitize_string(i) if isinstance(i, str) else i
                for i in v[:1000]  # cap list length
            ]
        else:
            result[safe_key] = v
    return result


# ── HMAC request signing ──────────────────────────────────────────────────────

def sign_request(payload: str, secret: str, timestamp: Optional[int] = None) -> str:
    """
    Generate HMAC-SHA256 signature for a request payload.

    Signature format: `t={timestamp},v1={hmac_hex}`
    """
    ts = timestamp or int(time.time())
    message = f"{ts}.{payload}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def verify_signature(
    payload: str,
    signature_header: str,
    secret: str,
    tolerance_seconds: int = 300,
) -> bool:
    """
    Verify HMAC-SHA256 signature from `X-Fincept-Signature` header.
    Rejects requests older than `tolerance_seconds`.
    """
    try:
        parts = dict(p.split("=", 1) for p in signature_header.split(","))
        ts = int(parts["t"])
        provided_sig = parts["v1"]
    except (KeyError, ValueError):
        logger.warning("security.invalid_signature_format")
        return False

    # Check timestamp freshness
    if abs(time.time() - ts) > tolerance_seconds:
        logger.warning("security.signature_expired", age_seconds=int(time.time() - ts))
        return False

    # Recompute expected signature
    message = f"{ts}.{payload}".encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()

    # Constant-time comparison
    return hmac.compare_digest(expected, provided_sig)


# ── Per-endpoint rate limit overrides ────────────────────────────────────────

# Endpoint group names used in Redis key: analytics:rate:{user_id}:{group}
# Groups map to a rate limit (req/min) per Requirement 6.1:
#   - "default"   : 60 req/min
#   - "agent_run" : 10 req/min  (LLM agent calls)
#   - "heavy_job" : 1  req/min  (ML training)

RATE_LIMIT_DEFAULT = 60   # req/min — general endpoints
RATE_LIMIT_AGENT_RUN = 10  # req/min — agent run endpoints
RATE_LIMIT_HEAVY_JOB = 1   # req/min — training / heavy compute

# Endpoints that are more expensive get stricter limits (req/min)
# Value is (limit, group_name) — group_name is used in the Redis key
ENDPOINT_RATE_LIMITS: Dict[str, Tuple[int, str]] = {
    # AI Agents — expensive (LLM calls) → agent_run group
    "/api/v1/agents/run": (RATE_LIMIT_AGENT_RUN, "agent_run"),
    "/api/v1/agents/run/stream": (RATE_LIMIT_AGENT_RUN, "agent_run"),
    "/api/v1/agents/team/run": (RATE_LIMIT_AGENT_RUN, "agent_run"),
    "/api/v1/agents/multi/run": (RATE_LIMIT_AGENT_RUN, "agent_run"),
    "/api/v1/agents/plan/execute": (RATE_LIMIT_AGENT_RUN, "agent_run"),
    "/api/v1/agents/analyze/stock": (RATE_LIMIT_AGENT_RUN, "agent_run"),
    "/api/v1/agents/analyze/portfolio": (RATE_LIMIT_AGENT_RUN, "agent_run"),
    "/api/v1/agents/analyze/risk": (RATE_LIMIT_AGENT_RUN, "agent_run"),
    "/api/v1/agents/analyze/macro": (RATE_LIMIT_AGENT_RUN, "agent_run"),
    "/api/v1/agents/analyze/earnings": (RATE_LIMIT_AGENT_RUN, "agent_run"),
    "/api/v1/agents/analyze/sector-rotation": (RATE_LIMIT_AGENT_RUN, "agent_run"),
    # Quant Lab — very expensive (ML training) → heavy_job group
    "/api/v1/quant-lab/backtest": (2, "agent_run"),
    "/api/v1/quant-lab/models/train": (RATE_LIMIT_HEAVY_JOB, "heavy_job"),
    "/api/v1/quant-lab/rl/train": (RATE_LIMIT_HEAVY_JOB, "heavy_job"),
    # Portfolio optimization
    "/api/v1/portfolio/optimize": (RATE_LIMIT_AGENT_RUN, "agent_run"),
    "/api/v1/portfolio/backtest": (RATE_LIMIT_AGENT_RUN, "agent_run"),
    # Batch endpoints
    "/api/v1/market/quotes/batch": (20, "default"),
    "/api/v1/quant/option/batch-greeks": (RATE_LIMIT_AGENT_RUN, "agent_run"),
}


def get_endpoint_rate_limit(path: str, default: int = RATE_LIMIT_DEFAULT) -> int:
    """
    Return the rate limit (req/min) for a specific endpoint path.

    Kept for backward compatibility — returns only the integer limit.
    Use get_endpoint_rate_limit_info() for the full (limit, group) tuple.
    """
    limit, _group = get_endpoint_rate_limit_info(path, default=default)
    return limit


def get_endpoint_rate_limit_info(
    path: str, default: int = RATE_LIMIT_DEFAULT
) -> Tuple[int, str]:
    """
    Return (limit, group_name) for a specific endpoint path.

    group_name is used as the suffix in the Redis key:
        analytics:rate:{user_id}:{group_name}

    This allows per-group sliding windows so that hitting the agent_run
    limit does not consume the user's default quota.
    """
    # Exact match first
    if path in ENDPOINT_RATE_LIMITS:
        return ENDPOINT_RATE_LIMITS[path]
    # Prefix match for path params (e.g. /api/v1/agents/sessions/xxx)
    for pattern, info in ENDPOINT_RATE_LIMITS.items():
        if path.startswith(pattern.rstrip("/")):
            return info
    return (default, "default")


# ── Per-user sliding-window rate limiter ──────────────────────────────────────

class RateLimiter:
    """
    Sliding-window rate limiter backed by Redis, keyed per user_id.

    Redis key pattern: analytics:rate:{user_id}:{endpoint_group}
    Window: 60 seconds (fixed 1-minute bucket, TTL 120s for safety).

    Usage::

        limiter = RateLimiter(cache_instance)
        allowed, limit, remaining, retry_after = await limiter.check(
            user_id="abc123",
            path="/api/v1/agents/run",
        )
        if not allowed:
            # return 429 with headers
    """

    # Redis key prefix for rate limit counters — must use analytics:rate: prefix
    KEY_PREFIX = "analytics:rate:"

    def __init__(self, cache_layer) -> None:
        """
        Args:
            cache_layer: An instance of CacheLayer (core.cache.CacheLayer).
        """
        self._cache = cache_layer

    async def check(
        self,
        user_id: str,
        path: str,
        default_limit: int = RATE_LIMIT_DEFAULT,
    ) -> Tuple[bool, int, int, int]:
        """
        Check whether the request is within the rate limit.

        Args:
            user_id:       Authenticated user identifier (JWT ``sub`` claim).
            path:          Request path, used to look up per-endpoint override.
            default_limit: Fallback limit when no endpoint override exists.

        Returns:
            Tuple of (allowed, limit, remaining, retry_after_seconds):
              - allowed        : True if the request should proceed.
              - limit          : The applicable limit for this endpoint.
              - remaining      : Requests remaining in the current window.
              - retry_after    : Seconds until the window resets (0 when allowed).
        """
        limit, group = get_endpoint_rate_limit_info(path, default=default_limit)

        # Sliding window bucket: 1-minute granularity
        window_bucket = int(time.time()) // 60
        redis_key = f"{self.KEY_PREFIX}{user_id}:{group}:{window_bucket}"

        try:
            count = await self._cache.incr(redis_key)
            if count == 1:
                # First request in this window — set TTL (2 min for safety)
                await self._cache.expire(redis_key, 120)

            remaining = max(0, limit - count)
            allowed = count <= limit

            # retry_after: seconds until the next 1-minute bucket starts
            retry_after = 60 - (int(time.time()) % 60) if not allowed else 0

            logger.debug(
                "rate_limit.check",
                user_id=user_id,
                group=group,
                count=count,
                limit=limit,
                allowed=allowed,
            )
            return allowed, limit, remaining, retry_after

        except Exception as exc:
            # Redis unavailable — fail open (never block requests)
            logger.warning("rate_limit.redis_error", error=str(exc))
            return True, limit, limit, 0


# ── API key helpers ───────────────────────────────────────────────────────────

def mask_api_key(key: str) -> str:
    """Return a masked version of an API key for logging (never log full keys)."""
    if not key or len(key) < 8:
        return "***"
    return f"{key[:7]}...{key[-4:]}"


def is_valid_api_key_format(key: str) -> bool:
    """Check if a key matches the expected format: fincept_{tier}_{32hex}"""
    pattern = re.compile(r"^fincept_(free|paid|admin)_[a-f0-9]{32,}$")
    return bool(pattern.match(key))

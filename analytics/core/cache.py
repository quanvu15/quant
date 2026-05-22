"""
Redis cache layer with TTL-based caching.

Cache key format: {REDIS_KEY_PREFIX}{module}:{action}:{hash(params)}
All keys are automatically prefixed with settings.REDIS_KEY_PREFIX ("analytics:")
to ensure namespace isolation from QuantDinger's Redis keys (which use "qd:").
Mirrors DataHub TTL policies from fincept-qt.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

import structlog
from redis.asyncio import Redis, from_url

from app.config import settings

logger = structlog.get_logger(__name__)


class CacheLayer:
    """
    Async Redis cache wrapper.

    Usage::

        await cache.connect()

        # Set with TTL
        await cache.set("market:quote:AAPL", data, ttl=5)

        # Get
        value = await cache.get("market:quote:AAPL")

        # Build key from params
        key = cache.build_key("market", "history", symbol="AAPL", interval="1d")
    """

    def __init__(self):
        self._redis: Optional[Redis] = None

    async def connect(self) -> None:
        """Initialize Redis connection pool."""
        try:
            self._redis = from_url(
                settings.REDIS_URL,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
                decode_responses=False,  # We handle encoding ourselves
            )
            await self._redis.ping()
            logger.info("cache.connected", url=settings.REDIS_URL)
        except Exception as exc:
            logger.warning("cache.connect_failed", error=str(exc))
            self._redis = None

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.aclose()
            self._redis = None

    async def ping(self) -> bool:
        """Check Redis connectivity."""
        if not self._redis:
            return False
        try:
            return await self._redis.ping()
        except Exception:
            return False

    async def get(self, key: str) -> Optional[Any]:
        """Get a cached value. Returns None on miss or error."""
        if not self._redis:
            return None
        try:
            raw = await self._redis.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as exc:
            logger.debug("cache.get_error", key=key, error=str(exc))
            return None

    async def set(self, key: str, value: Any, ttl: int = 60) -> bool:
        """Set a value with TTL (seconds). Returns True on success."""
        if not self._redis:
            return False
        try:
            serialized = json.dumps(value, default=str)
            await self._redis.setex(key, ttl, serialized)
            return True
        except Exception as exc:
            logger.debug("cache.set_error", key=key, error=str(exc))
            return False

    async def delete(self, key: str) -> bool:
        """Delete a key. Returns True if key existed."""
        if not self._redis:
            return False
        try:
            result = await self._redis.delete(key)
            return result > 0
        except Exception as exc:
            logger.debug("cache.delete_error", key=key, error=str(exc))
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching a pattern. Returns count deleted."""
        if not self._redis:
            return 0
        try:
            keys = await self._redis.keys(pattern)
            if keys:
                return await self._redis.delete(*keys)
            return 0
        except Exception as exc:
            logger.debug("cache.delete_pattern_error", pattern=pattern, error=str(exc))
            return 0

    async def incr(self, key: str) -> int:
        """Increment a counter. Returns new value."""
        if not self._redis:
            return 0
        return await self._redis.incr(key)

    async def expire(self, key: str, ttl: int) -> bool:
        """Set TTL on existing key."""
        if not self._redis:
            return False
        return await self._redis.expire(key, ttl)

    async def get_or_set(
        self,
        key: str,
        factory,
        ttl: int = 60,
    ) -> Any:
        """
        Cache-aside pattern: return cached value or call factory() and cache result.

        Args:
            key: Cache key.
            factory: Async callable that returns the value to cache.
            ttl: TTL in seconds.
        """
        cached = await self.get(key)
        if cached is not None:
            logger.debug("cache.hit", key=key)
            return cached

        logger.debug("cache.miss", key=key)
        value = await factory()
        await self.set(key, value, ttl=ttl)
        return value

    # ── Key builders ──────────────────────────────────────────────────────────

    @staticmethod
    def build_key(module: str, action: str, **params) -> str:
        """
        Build a cache key in the format: {REDIS_KEY_PREFIX}{module}:{action}:{hash(params)}

        The prefix (settings.REDIS_KEY_PREFIX, default "analytics:") is prepended
        automatically to ensure namespace isolation from QuantDinger keys.

        Example::
            key = CacheLayer.build_key("market", "history", symbol="AAPL", interval="1d")
            # → "analytics:market:history:a3f2..."
        """
        prefix = settings.REDIS_KEY_PREFIX
        if params:
            params_str = json.dumps(params, sort_keys=True, default=str)
            params_hash = hashlib.sha256(params_str.encode()).hexdigest()[:16]
            return f"{prefix}{module}:{action}:{params_hash}"
        return f"{prefix}{module}:{action}"

    @staticmethod
    def quote_key(symbol: str) -> str:
        return f"{settings.REDIS_KEY_PREFIX}market:quote:{symbol.upper()}"

    @staticmethod
    def history_key(symbol: str, interval: str, start: str, end: str) -> str:
        h = hashlib.sha256(f"{symbol}{interval}{start}{end}".encode()).hexdigest()[:12]
        return f"{settings.REDIS_KEY_PREFIX}market:history:{symbol.upper()}:{interval}:{h}"

    @staticmethod
    def equity_info_key(symbol: str) -> str:
        return f"{settings.REDIS_KEY_PREFIX}equity:info:{symbol.upper()}"

    @staticmethod
    def agents_list_key(category: str = "") -> str:
        suffix = f":{category}" if category else ""
        return f"{settings.REDIS_KEY_PREFIX}agents:list{suffix}"


# TTL constants (seconds) — mirrors DataHub TTL policies
class TTL:
    QUOTE = 5
    INTRADAY = 30
    DAILY_HISTORY = 300
    EQUITY_INFO = 3600
    DCF = 1800
    NEWS = 300
    AGENTS_LIST = 300
    AGENTS_DISCOVER = 300
    FRED_SERIES = 3600
    GEOPOLITICS_EVENTS = 120
    MARITIME_VESSEL = 60
    OPTION_PRICE = 60
    ECONOMIC_CALENDAR = 300
    CENTRAL_BANK = 3600
    GOV_DATA = 3600
    ENERGY = 3600
    ENVIRONMENT = 86400  # 24h


# Module-level singleton
cache = CacheLayer()

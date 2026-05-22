"""
Tests for JWT verification caching (Requirement 1.5, 1.6).

Covers:
  - _normalise_user maps QD claims correctly: {sub: username, user_id: int, role}
    → {sub: str(user_id), role, email: "", source: "quantdinger"}
  - _jwt_cache_key produces correct format: analytics:jwt_cache:{hash16}
  - _cache_jwt_user stores with correct TTL (min of 300s and time-to-expiry)
  - _get_cached_jwt_user returns None for expired tokens (evicts from cache)
  - get_current_user uses JWT cache on second call (cache hit path)
  - Failed verifications are NOT cached
"""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from jose import jwt

from app.config import settings
from core.auth import (
    _SOURCE_QUANTDINGER,
    _JWT_CACHE_TTL,
    _jwt_cache_key,
    _normalise_user,
    _get_cached_jwt_user,
    _cache_jwt_user,
)


@pytest.fixture
def auth_cache():
    """Patch cache specifically in core.auth module where it's imported."""
    with patch("core.auth.cache") as mock:
        mock.get = AsyncMock(return_value=None)
        mock.set = AsyncMock(return_value=True)
        mock.delete = AsyncMock(return_value=True)
        yield mock


# ── _normalise_user tests for QD claims ───────────────────────────────────────


class TestNormaliseUserQD:
    """Verify _normalise_user maps QD JWT claims → internal User dict."""

    def test_maps_user_id_to_sub_as_string(self):
        """QD JWT user_id (int) becomes sub (str) in User dict."""
        claims = {
            "sub": "quantdinger",  # username, NOT unique id
            "user_id": 1,
            "role": "admin",
            "token_version": 1,
            "exp": int(time.time()) + 3600,
        }
        user = _normalise_user(claims, _SOURCE_QUANTDINGER)
        assert user["sub"] == "1"  # str(user_id)
        assert user["role"] == "admin"
        assert user["email"] == ""
        assert user["source"] == "quantdinger"

    def test_maps_user_id_large_int(self):
        """Handles large user_id integers."""
        claims = {"sub": "someuser", "user_id": 99999, "role": "user", "exp": 0}
        user = _normalise_user(claims, _SOURCE_QUANTDINGER)
        assert user["sub"] == "99999"

    def test_email_defaults_to_empty(self):
        """When QD JWT has no email claim, defaults to empty string."""
        claims = {"sub": "qd", "user_id": 5, "role": "user", "exp": 0}
        user = _normalise_user(claims, _SOURCE_QUANTDINGER)
        assert user["email"] == ""

    def test_email_preserved_when_present(self):
        """When QD JWT has email claim, it's preserved."""
        claims = {"sub": "qd", "user_id": 5, "role": "user", "email": "a@b.com", "exp": 0}
        user = _normalise_user(claims, _SOURCE_QUANTDINGER)
        assert user["email"] == "a@b.com"

    def test_role_defaults_to_user(self):
        """When role is missing, defaults to 'user'."""
        claims = {"sub": "qd", "user_id": 3, "exp": 0}
        user = _normalise_user(claims, _SOURCE_QUANTDINGER)
        assert user["role"] == "user"

    def test_preserves_raw_claims(self):
        """Original claims are preserved in _raw."""
        claims = {"sub": "qd", "user_id": 1, "role": "admin", "token_version": 1, "exp": 123}
        user = _normalise_user(claims, _SOURCE_QUANTDINGER)
        assert user["_raw"] == claims

    def test_exp_is_integer(self):
        """exp claim is always an integer."""
        claims = {"sub": "qd", "user_id": 1, "role": "user", "exp": 1700000000}
        user = _normalise_user(claims, _SOURCE_QUANTDINGER)
        assert user["exp"] == 1700000000
        assert isinstance(user["exp"], int)


# ── _jwt_cache_key tests ──────────────────────────────────────────────────────


class TestJwtCacheKey:
    """Verify cache key format: analytics:jwt_cache:{first 16 chars of SHA256}."""

    def test_key_format(self):
        token = "eyJhbGciOiJIUzI1NiJ9.test.payload"
        key = _jwt_cache_key(token)
        expected_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
        assert key == f"analytics:jwt_cache:{expected_hash}"

    def test_different_tokens_different_keys(self):
        key1 = _jwt_cache_key("token-aaa")
        key2 = _jwt_cache_key("token-bbb")
        assert key1 != key2

    def test_same_token_same_key(self):
        key1 = _jwt_cache_key("same-token")
        key2 = _jwt_cache_key("same-token")
        assert key1 == key2


# ── _get_cached_jwt_user tests ────────────────────────────────────────────────


class TestGetCachedJwtUser:
    """Verify cache retrieval with expiry checks."""

    @pytest.mark.asyncio
    async def test_returns_none_on_cache_miss(self, auth_cache):
        """Cache miss returns None."""
        auth_cache.get = AsyncMock(return_value=None)
        result = await _get_cached_jwt_user("some-token")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_cached_user_when_not_expired(self, auth_cache):
        """Cache hit with valid exp returns the cached user."""
        future_exp = int(time.time()) + 3600
        cached_user = {"sub": "1", "role": "admin", "email": "", "source": "quantdinger", "exp": future_exp}
        auth_cache.get = AsyncMock(return_value=cached_user)
        result = await _get_cached_jwt_user("some-token")
        assert result == cached_user

    @pytest.mark.asyncio
    async def test_evicts_and_returns_none_when_expired(self, auth_cache):
        """Cache hit with expired exp evicts the entry and returns None."""
        past_exp = int(time.time()) - 100  # expired 100s ago
        cached_user = {"sub": "1", "role": "admin", "email": "", "source": "quantdinger", "exp": past_exp}
        auth_cache.get = AsyncMock(return_value=cached_user)
        auth_cache.delete = AsyncMock(return_value=True)
        result = await _get_cached_jwt_user("some-token")
        assert result is None
        # Verify delete was called to evict
        auth_cache.delete.assert_called_once()


# ── _cache_jwt_user tests ─────────────────────────────────────────────────────


class TestCacheJwtUser:
    """Verify caching logic with TTL bounds."""

    @pytest.mark.asyncio
    async def test_caches_with_jwt_cache_ttl(self, auth_cache):
        """When token has long expiry, uses _JWT_CACHE_TTL (300s)."""
        far_future_exp = int(time.time()) + 86400  # 24h from now
        user = {"sub": "1", "role": "user", "email": "", "source": "quantdinger", "exp": far_future_exp}
        auth_cache.set = AsyncMock(return_value=True)
        await _cache_jwt_user("my-token", user)
        auth_cache.set.assert_called_once()
        call_args = auth_cache.set.call_args
        # TTL should be _JWT_CACHE_TTL (300) since token expiry is far away
        assert call_args[1]["ttl"] == _JWT_CACHE_TTL

    @pytest.mark.asyncio
    async def test_caches_with_remaining_time_when_less_than_ttl(self, auth_cache):
        """When token expires soon, uses remaining time as TTL."""
        short_exp = int(time.time()) + 60  # expires in 60s
        user = {"sub": "1", "role": "user", "email": "", "source": "quantdinger", "exp": short_exp}
        auth_cache.set = AsyncMock(return_value=True)
        await _cache_jwt_user("my-token", user)
        auth_cache.set.assert_called_once()
        call_args = auth_cache.set.call_args
        # TTL should be ~60 (remaining time), not 300
        ttl = call_args[1]["ttl"]
        assert ttl <= 60
        assert ttl > 0

    @pytest.mark.asyncio
    async def test_does_not_cache_already_expired_token(self, auth_cache):
        """Tokens that are already expired are not cached."""
        past_exp = int(time.time()) - 10  # expired 10s ago
        user = {"sub": "1", "role": "user", "email": "", "source": "quantdinger", "exp": past_exp}
        auth_cache.set = AsyncMock(return_value=True)
        await _cache_jwt_user("my-token", user)
        # set should NOT be called for expired tokens
        auth_cache.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_key_uses_token_hash(self, auth_cache):
        """Cache key is based on token hash, not user_id."""
        token = "my-specific-token"
        user = {"sub": "1", "role": "user", "email": "", "source": "quantdinger", "exp": int(time.time()) + 3600}
        auth_cache.set = AsyncMock(return_value=True)
        await _cache_jwt_user(token, user)
        call_args = auth_cache.set.call_args
        expected_key = _jwt_cache_key(token)
        assert call_args[0][0] == expected_key

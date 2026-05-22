"""Phase 6 — Security hardening tests."""
from __future__ import annotations
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from core.security import (
    RATE_LIMIT_AGENT_RUN,
    RATE_LIMIT_DEFAULT,
    RATE_LIMIT_HEAVY_JOB,
    RateLimiter,
    get_endpoint_rate_limit,
    get_endpoint_rate_limit_info,
    is_valid_api_key_format,
    mask_api_key,
    sanitize_dict,
    sanitize_string,
    sanitize_symbol,
    sign_request,
    verify_signature,
)


class TestInputSanitization:
    def test_sanitize_string_strips_control_chars(self):
        dirty = "hello\x00world\x1f!"
        assert "\x00" not in sanitize_string(dirty)
        assert "\x1f" not in sanitize_string(dirty)
        assert "hello" in sanitize_string(dirty)

    def test_sanitize_string_max_length(self):
        long_str = "a" * 20000
        result = sanitize_string(long_str, max_length=100)
        assert len(result) == 100

    def test_sanitize_string_normal_text_unchanged(self):
        text = "Analyze AAPL stock — give me a buy/sell recommendation!"
        assert sanitize_string(text) == text

    def test_sanitize_symbol_strips_dangerous(self):
        # Semicolons, spaces, slashes stripped — letters/digits/dash remain
        result = sanitize_symbol("AAPL; rm -rf /")
        assert ";" not in result
        assert "/" not in result
        assert " " not in result
        assert result.startswith("AAPL")
        # Clean symbols pass through unchanged
        assert sanitize_symbol("MSFT") == "MSFT"
        assert sanitize_symbol("BRK-B") == "BRK-B"
        assert sanitize_symbol("aapl") == "AAPL"
        # Pipe stripped
        assert "|" not in sanitize_symbol("AAPL|MSFT")

    def test_sanitize_symbol_max_length(self):
        assert len(sanitize_symbol("A" * 50)) <= 20

    def test_sanitize_dict_recursive(self):
        data = {
            "query": "hello\x00world",
            "nested": {"key": "value\x1f"},
            "list": ["item1\x00", "item2"],
        }
        result = sanitize_dict(data)
        assert "\x00" not in result["query"]
        assert "\x1f" not in result["nested"]["key"]
        assert "\x00" not in result["list"][0]

    def test_sanitize_dict_max_depth(self):
        # Deep nesting should be truncated
        deep = {"a": {"b": {"c": {"d": {"e": {"f": "deep"}}}}}}
        result = sanitize_dict(deep, max_depth=3)
        assert isinstance(result, dict)


class TestHMACSigning:
    SECRET = "test-secret-key"

    def test_sign_and_verify(self):
        payload = '{"action": "run", "query": "test"}'
        sig = sign_request(payload, self.SECRET)
        assert verify_signature(payload, sig, self.SECRET)

    def test_verify_wrong_secret(self):
        payload = '{"action": "run"}'
        sig = sign_request(payload, self.SECRET)
        assert not verify_signature(payload, sig, "wrong-secret")

    def test_verify_tampered_payload(self):
        payload = '{"action": "run"}'
        sig = sign_request(payload, self.SECRET)
        assert not verify_signature('{"action": "tampered"}', sig, self.SECRET)

    def test_verify_expired_signature(self):
        payload = '{"action": "run"}'
        old_ts = int(time.time()) - 400  # 400s ago, tolerance is 300s
        sig = sign_request(payload, self.SECRET, timestamp=old_ts)
        assert not verify_signature(payload, sig, self.SECRET, tolerance_seconds=300)

    def test_verify_invalid_format(self):
        assert not verify_signature("payload", "invalid-sig-format", self.SECRET)

    def test_sign_includes_timestamp(self):
        sig = sign_request("payload", self.SECRET)
        assert sig.startswith("t=")
        assert "v1=" in sig


class TestRateLimits:
    def test_agent_run_stricter_limit(self):
        limit = get_endpoint_rate_limit("/api/v1/agents/run")
        assert limit < 60  # stricter than default

    def test_model_train_very_strict(self):
        limit = get_endpoint_rate_limit("/api/v1/quant-lab/models/train")
        assert limit <= 2

    def test_health_uses_default(self):
        limit = get_endpoint_rate_limit("/health", default=60)
        assert limit == 60

    def test_unknown_path_uses_default(self):
        limit = get_endpoint_rate_limit("/unknown/path", default=60)
        assert limit == 60

    def test_batch_greeks_stricter(self):
        limit = get_endpoint_rate_limit("/api/v1/quant/option/batch-greeks")
        assert limit <= 20

    # ── New tests for Requirement 6.1 ─────────────────────────────────────────

    def test_default_limit_is_60(self):
        """Requirement 6.1: default 60 req/min."""
        assert RATE_LIMIT_DEFAULT == 60

    def test_agent_run_limit_is_10(self):
        """Requirement 6.1: agent run endpoints 10 req/min."""
        assert RATE_LIMIT_AGENT_RUN == 10

    def test_heavy_job_limit_is_1(self):
        """Requirement 6.1: heavy job (training) 1 req/min."""
        assert RATE_LIMIT_HEAVY_JOB == 1

    def test_get_endpoint_rate_limit_info_returns_tuple(self):
        limit, group = get_endpoint_rate_limit_info("/api/v1/agents/run")
        assert limit == RATE_LIMIT_AGENT_RUN
        assert group == "agent_run"

    def test_get_endpoint_rate_limit_info_heavy_job(self):
        limit, group = get_endpoint_rate_limit_info("/api/v1/quant-lab/models/train")
        assert limit == RATE_LIMIT_HEAVY_JOB
        assert group == "heavy_job"

    def test_get_endpoint_rate_limit_info_rl_train(self):
        limit, group = get_endpoint_rate_limit_info("/api/v1/quant-lab/rl/train")
        assert limit == RATE_LIMIT_HEAVY_JOB
        assert group == "heavy_job"

    def test_get_endpoint_rate_limit_info_default_group(self):
        limit, group = get_endpoint_rate_limit_info("/api/v1/news")
        assert limit == RATE_LIMIT_DEFAULT
        assert group == "default"

    def test_prefix_match_for_path_params(self):
        """Paths with trailing segments should match the base pattern."""
        limit, group = get_endpoint_rate_limit_info("/api/v1/agents/run/some-session-id")
        assert limit == RATE_LIMIT_AGENT_RUN
        assert group == "agent_run"

    def test_backward_compat_get_endpoint_rate_limit(self):
        """get_endpoint_rate_limit() still returns just the integer."""
        assert get_endpoint_rate_limit("/api/v1/agents/run") == RATE_LIMIT_AGENT_RUN
        assert get_endpoint_rate_limit("/api/v1/news") == RATE_LIMIT_DEFAULT


class TestRateLimiterClass:
    """Tests for the RateLimiter class — Validates: Requirement 6.1."""

    def _make_limiter(self, incr_return: int = 1):
        """Create a RateLimiter with a mocked cache layer."""
        mock_cache = MagicMock()
        mock_cache.incr = AsyncMock(return_value=incr_return)
        mock_cache.expire = AsyncMock(return_value=True)
        return RateLimiter(mock_cache), mock_cache

    @pytest.mark.asyncio
    async def test_first_request_is_allowed(self):
        limiter, _ = self._make_limiter(incr_return=1)
        allowed, limit, remaining, retry_after = await limiter.check(
            user_id="user-123", path="/api/v1/news"
        )
        assert allowed is True
        assert limit == RATE_LIMIT_DEFAULT
        assert remaining == RATE_LIMIT_DEFAULT - 1
        assert retry_after == 0

    @pytest.mark.asyncio
    async def test_request_at_limit_is_allowed(self):
        """The request that hits exactly the limit is still allowed."""
        limiter, _ = self._make_limiter(incr_return=RATE_LIMIT_DEFAULT)
        allowed, limit, remaining, _ = await limiter.check(
            user_id="user-123", path="/api/v1/news"
        )
        assert allowed is True
        assert remaining == 0

    @pytest.mark.asyncio
    async def test_request_over_limit_is_blocked(self):
        """The request that exceeds the limit is blocked with 429 info."""
        limiter, _ = self._make_limiter(incr_return=RATE_LIMIT_DEFAULT + 1)
        allowed, limit, remaining, retry_after = await limiter.check(
            user_id="user-123", path="/api/v1/news"
        )
        assert allowed is False
        assert remaining == 0
        assert retry_after > 0

    @pytest.mark.asyncio
    async def test_agent_run_uses_agent_run_group(self):
        """Agent run endpoints use the agent_run group and 10 req/min limit."""
        limiter, mock_cache = self._make_limiter(incr_return=1)
        allowed, limit, remaining, _ = await limiter.check(
            user_id="user-abc", path="/api/v1/agents/run"
        )
        assert allowed is True
        assert limit == RATE_LIMIT_AGENT_RUN
        # Redis key should contain "agent_run"
        call_args = mock_cache.incr.call_args[0][0]
        assert "agent_run" in call_args
        assert "user-abc" in call_args
        assert call_args.startswith("analytics:rate:")

    @pytest.mark.asyncio
    async def test_heavy_job_uses_heavy_job_group(self):
        """Training endpoints use the heavy_job group and 1 req/min limit."""
        limiter, mock_cache = self._make_limiter(incr_return=1)
        allowed, limit, remaining, _ = await limiter.check(
            user_id="user-xyz", path="/api/v1/quant-lab/models/train"
        )
        assert allowed is True
        assert limit == RATE_LIMIT_HEAVY_JOB
        call_args = mock_cache.incr.call_args[0][0]
        assert "heavy_job" in call_args
        assert "user-xyz" in call_args

    @pytest.mark.asyncio
    async def test_redis_key_uses_analytics_rate_prefix(self):
        """Redis key must use analytics:rate: prefix per Requirement 6.1."""
        limiter, mock_cache = self._make_limiter(incr_return=1)
        await limiter.check(user_id="user-123", path="/api/v1/news")
        call_args = mock_cache.incr.call_args[0][0]
        assert call_args.startswith("analytics:rate:")

    @pytest.mark.asyncio
    async def test_redis_key_includes_user_id(self):
        """Redis key must include user_id for per-user isolation."""
        limiter, mock_cache = self._make_limiter(incr_return=1)
        await limiter.check(user_id="unique-user-id-999", path="/api/v1/news")
        call_args = mock_cache.incr.call_args[0][0]
        assert "unique-user-id-999" in call_args

    @pytest.mark.asyncio
    async def test_different_users_have_different_keys(self):
        """Two users must get different Redis keys (no cross-user pollution)."""
        limiter, mock_cache = self._make_limiter(incr_return=1)
        await limiter.check(user_id="alice", path="/api/v1/news")
        key_alice = mock_cache.incr.call_args[0][0]
        await limiter.check(user_id="bob", path="/api/v1/news")
        key_bob = mock_cache.incr.call_args[0][0]
        assert key_alice != key_bob

    @pytest.mark.asyncio
    async def test_redis_failure_fails_open(self):
        """When Redis is unavailable, requests must be allowed (fail open)."""
        mock_cache = MagicMock()
        mock_cache.incr = AsyncMock(side_effect=Exception("Redis connection refused"))
        limiter = RateLimiter(mock_cache)
        allowed, limit, remaining, retry_after = await limiter.check(
            user_id="user-123", path="/api/v1/news"
        )
        assert allowed is True
        assert retry_after == 0

    @pytest.mark.asyncio
    async def test_ttl_set_on_first_request(self):
        """expire() must be called when count == 1 (first request in window)."""
        limiter, mock_cache = self._make_limiter(incr_return=1)
        await limiter.check(user_id="user-123", path="/api/v1/news")
        mock_cache.expire.assert_called_once()
        # TTL should be 120s (2-minute safety window)
        _, ttl_arg = mock_cache.expire.call_args[0]
        assert ttl_arg == 120

    @pytest.mark.asyncio
    async def test_ttl_not_set_on_subsequent_requests(self):
        """expire() must NOT be called when count > 1."""
        limiter, mock_cache = self._make_limiter(incr_return=5)
        await limiter.check(user_id="user-123", path="/api/v1/news")
        mock_cache.expire.assert_not_called()


class TestApiKeyHelpers:
    def test_valid_free_key(self):
        key = "fincept_free_" + "a" * 32
        assert is_valid_api_key_format(key)

    def test_valid_paid_key(self):
        key = "fincept_paid_" + "b" * 40
        assert is_valid_api_key_format(key)

    def test_valid_admin_key(self):
        key = "fincept_admin_" + "c" * 32
        assert is_valid_api_key_format(key)

    def test_invalid_prefix(self):
        assert not is_valid_api_key_format("sk-openai-key")
        assert not is_valid_api_key_format("Bearer token")

    def test_invalid_tier(self):
        assert not is_valid_api_key_format("fincept_enterprise_" + "a" * 32)

    def test_mask_api_key(self):
        key = "fincept_free_abcdef1234567890"
        masked = mask_api_key(key)
        assert masked.startswith("fincept")
        assert "abcdef1234567890" not in masked
        assert "..." in masked

    def test_mask_short_key(self):
        assert mask_api_key("abc") == "***"
        assert mask_api_key("") == "***"


class TestMetricsEndpoint:
    def test_metrics_endpoint_accessible(self, client):
        r = client.get("/metrics")
        assert r.status_code == 200

    def test_metrics_content_type(self, client):
        r = client.get("/metrics")
        # Either prometheus format or plain text fallback
        assert "text/" in r.headers.get("content-type", "text/plain")

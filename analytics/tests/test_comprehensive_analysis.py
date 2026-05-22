"""
Tests for task 4.1 — Comprehensive analysis endpoint.

POST /api/v1/analytics/comprehensive/{symbol}

Validates: Requirement 4.5
  1. Endpoint aggregates quote + info + DCF + technicals + news sections.
  2. Concurrent calls via asyncio.gather (all sections present in response).
  3. Cache aggregated result with TTL 60s.
  4. Graceful partial failure: one section error does not fail the whole response.
  5. Agent opinion section only included when llm_config is provided.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_jwt_user
from app.main import app

# ── Fixtures ──────────────────────────────────────────────────────────────────

MOCK_USER = {"sub": "user-123", "email": "test@example.com", "role": "user"}

QUOTE_RESP = {"success": True, "data": {"symbol": "AAPL", "price": 150.0, "change": 1.5}}
INFO_RESP = {"success": True, "data": {"sector": "Technology", "marketCap": 2_500_000_000_000}}
DCF_RESP = {"success": True, "data": {"intrinsic_value": 180.0, "current_price": 150.0}}
TECH_RESP = {"success": True, "data": {"RSI": 55.0, "MACD": {"macd": 1.2, "signal": 0.8}}}
NEWS_RESP = {"success": True, "articles": [{"title": "AAPL hits record", "sentiment": 0.8}]}
AGENT_RESP = {"success": True, "response": "AAPL looks undervalued based on DCF analysis."}


def _mock_runner(rv: dict) -> MagicMock:
    """Create a mock runner that returns rv from run()."""
    m = MagicMock()
    m.run = AsyncMock(return_value=rv)
    return m


@pytest.fixture
def client():
    """Test client with JWT auth bypassed."""
    async def _mock_jwt():
        return MOCK_USER

    app.dependency_overrides[get_jwt_user] = _mock_jwt
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── Helper: patch all sub-runners ─────────────────────────────────────────────

def _patch_runners(
    quote=QUOTE_RESP,
    info=INFO_RESP,
    dcf=DCF_RESP,
    tech=TECH_RESP,
    news=NEWS_RESP,
):
    """
    Patch get_runner to return different responses based on script key.

    The comprehensive endpoint calls _run() with different script keys:
      market.yfinance → quote, info, dcf
      technical.compute → technicals
      equity.news → news
    """
    call_count = {"n": 0}
    responses = [quote, info, dcf, tech, news]

    def _side_effect(*args, **kwargs):
        idx = call_count["n"]
        call_count["n"] += 1
        rv = responses[idx] if idx < len(responses) else {"success": True}
        return _mock_runner(rv)

    return patch("app.routers.analytics.get_runner", side_effect=_side_effect)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestComprehensiveEndpoint:
    """Tests for POST /api/v1/analytics/comprehensive/{symbol}."""

    def test_returns_all_sections(self, client):
        """All 5 sections (quote, info, dcf, technicals, news) must be present."""
        with (
            patch("app.routers.analytics.cache.get", AsyncMock(return_value=None)),
            patch("app.routers.analytics.cache.set", AsyncMock(return_value=True)),
            patch("app.routers.analytics.cache.build_key", return_value="test:key"),
            patch("app.routers.analytics.cache.quote_key", return_value="test:quote"),
            patch("app.routers.analytics.cache.equity_info_key", return_value="test:info"),
            _patch_runners(),
        ):
            r = client.post("/api/v1/analytics/comprehensive/AAPL", json={})

        assert r.status_code == 200
        data = r.json()
        assert data["symbol"] == "AAPL"
        assert "quote" in data
        assert "info" in data
        assert "dcf" in data
        assert "technicals" in data
        assert "news" in data

    def test_no_agent_opinion_without_llm_config(self, client):
        """agent_opinion section must NOT be present when llm_config is omitted."""
        with (
            patch("app.routers.analytics.cache.get", AsyncMock(return_value=None)),
            patch("app.routers.analytics.cache.set", AsyncMock(return_value=True)),
            patch("app.routers.analytics.cache.build_key", return_value="test:key"),
            patch("app.routers.analytics.cache.quote_key", return_value="test:quote"),
            patch("app.routers.analytics.cache.equity_info_key", return_value="test:info"),
            _patch_runners(),
        ):
            r = client.post("/api/v1/analytics/comprehensive/AAPL", json={})

        assert r.status_code == 200
        assert "agent_opinion" not in r.json()

    def test_symbol_uppercased(self, client):
        """Symbol in response must be uppercased regardless of input case."""
        with (
            patch("app.routers.analytics.cache.get", AsyncMock(return_value=None)),
            patch("app.routers.analytics.cache.set", AsyncMock(return_value=True)),
            patch("app.routers.analytics.cache.build_key", return_value="test:key"),
            patch("app.routers.analytics.cache.quote_key", return_value="test:quote"),
            patch("app.routers.analytics.cache.equity_info_key", return_value="test:info"),
            _patch_runners(),
        ):
            r = client.post("/api/v1/analytics/comprehensive/aapl", json={})

        assert r.status_code == 200
        assert r.json()["symbol"] == "AAPL"

    def test_cache_hit_returns_cached_response(self, client):
        """When cache has a hit, the runner must NOT be called."""
        cached_response = {
            "symbol": "AAPL",
            "quote": QUOTE_RESP,
            "info": INFO_RESP,
            "dcf": DCF_RESP,
            "technicals": TECH_RESP,
            "news": NEWS_RESP,
            "generated_at": "2025-01-01T00:00:00Z",
            "elapsed_ms": 100.0,
            "_cached": False,
        }
        with (
            patch("app.routers.analytics.cache.get", AsyncMock(return_value=cached_response)),
            patch("app.routers.analytics.cache.build_key", return_value="test:key"),
            patch("app.routers.analytics.get_runner") as mock_runner,
        ):
            r = client.post("/api/v1/analytics/comprehensive/AAPL", json={})

        assert r.status_code == 200
        data = r.json()
        assert data["_cached"] is True
        mock_runner.assert_not_called()

    def test_cache_set_called_on_success(self, client):
        """Cache.set must be called with TTL=60 after a successful response."""
        mock_set = AsyncMock(return_value=True)
        with (
            patch("app.routers.analytics.cache.get", AsyncMock(return_value=None)),
            patch("app.routers.analytics.cache.set", mock_set),
            patch("app.routers.analytics.cache.build_key", return_value="test:key"),
            patch("app.routers.analytics.cache.quote_key", return_value="test:quote"),
            patch("app.routers.analytics.cache.equity_info_key", return_value="test:info"),
            _patch_runners(),
        ):
            r = client.post("/api/v1/analytics/comprehensive/AAPL", json={})

        assert r.status_code == 200
        # Find the call that sets the aggregated result (ttl=60)
        ttl_60_calls = [c for c in mock_set.call_args_list if c.kwargs.get("ttl") == 60]
        assert len(ttl_60_calls) >= 1, "cache.set with ttl=60 must be called for aggregated result"

    def test_partial_failure_graceful(self, client):
        """If one section (DCF) fails, the rest must still be returned."""
        from core.python_runner import PythonRunnerError

        call_count = {"n": 0}

        def _side_effect_with_dcf_error(*args, **kwargs):
            idx = call_count["n"]
            call_count["n"] += 1
            if idx == 2:  # DCF is the 3rd call
                m = MagicMock()
                m.run = AsyncMock(side_effect=PythonRunnerError("DCF script failed"))
                return m
            responses = [QUOTE_RESP, INFO_RESP, TECH_RESP, NEWS_RESP]
            rv = responses[idx] if idx < len(responses) else {"success": True}
            return _mock_runner(rv)

        with (
            patch("app.routers.analytics.cache.get", AsyncMock(return_value=None)),
            patch("app.routers.analytics.cache.set", AsyncMock(return_value=True)),
            patch("app.routers.analytics.cache.build_key", return_value="test:key"),
            patch("app.routers.analytics.cache.quote_key", return_value="test:quote"),
            patch("app.routers.analytics.cache.equity_info_key", return_value="test:info"),
            patch("app.routers.analytics.get_runner", side_effect=_side_effect_with_dcf_error),
        ):
            r = client.post("/api/v1/analytics/comprehensive/AAPL", json={})

        assert r.status_code == 200
        data = r.json()
        # Other sections must still be present
        assert "quote" in data
        assert "info" in data
        assert "technicals" in data
        assert "news" in data
        # DCF section must contain an error field
        assert "error" in data.get("dcf", {})
        # Response must be flagged as partial
        assert data.get("_partial") is True

    def test_response_has_metadata_fields(self, client):
        """Response must include symbol, generated_at, elapsed_ms, _cached fields."""
        with (
            patch("app.routers.analytics.cache.get", AsyncMock(return_value=None)),
            patch("app.routers.analytics.cache.set", AsyncMock(return_value=True)),
            patch("app.routers.analytics.cache.build_key", return_value="test:key"),
            patch("app.routers.analytics.cache.quote_key", return_value="test:quote"),
            patch("app.routers.analytics.cache.equity_info_key", return_value="test:info"),
            _patch_runners(),
        ):
            r = client.post("/api/v1/analytics/comprehensive/AAPL", json={})

        assert r.status_code == 200
        data = r.json()
        assert "symbol" in data
        assert "generated_at" in data
        assert "elapsed_ms" in data
        assert "_cached" in data
        assert data["_cached"] is False

    def test_empty_body_uses_defaults(self, client):
        """Sending an empty body {} must work with default parameters."""
        with (
            patch("app.routers.analytics.cache.get", AsyncMock(return_value=None)),
            patch("app.routers.analytics.cache.set", AsyncMock(return_value=True)),
            patch("app.routers.analytics.cache.build_key", return_value="test:key"),
            patch("app.routers.analytics.cache.quote_key", return_value="test:quote"),
            patch("app.routers.analytics.cache.equity_info_key", return_value="test:info"),
            _patch_runners(),
        ):
            r = client.post("/api/v1/analytics/comprehensive/AAPL", json={})

        assert r.status_code == 200

    def test_no_body_also_works(self, client):
        """Sending no body at all must work (body is optional)."""
        with (
            patch("app.routers.analytics.cache.get", AsyncMock(return_value=None)),
            patch("app.routers.analytics.cache.set", AsyncMock(return_value=True)),
            patch("app.routers.analytics.cache.build_key", return_value="test:key"),
            patch("app.routers.analytics.cache.quote_key", return_value="test:quote"),
            patch("app.routers.analytics.cache.equity_info_key", return_value="test:info"),
            _patch_runners(),
        ):
            r = client.post("/api/v1/analytics/comprehensive/AAPL")

        assert r.status_code == 200

    def test_all_sections_fail_still_returns_200(self, client):
        """Even if all sub-calls fail, the endpoint must return 200 with error sections."""
        from core.python_runner import PythonRunnerError

        def _always_fail(*args, **kwargs):
            m = MagicMock()
            m.run = AsyncMock(side_effect=PythonRunnerError("script failed"))
            return m

        with (
            patch("app.routers.analytics.cache.get", AsyncMock(return_value=None)),
            patch("app.routers.analytics.cache.set", AsyncMock(return_value=True)),
            patch("app.routers.analytics.cache.build_key", return_value="test:key"),
            patch("app.routers.analytics.cache.quote_key", return_value="test:quote"),
            patch("app.routers.analytics.cache.equity_info_key", return_value="test:info"),
            patch("app.routers.analytics.get_runner", side_effect=_always_fail),
        ):
            r = client.post("/api/v1/analytics/comprehensive/AAPL", json={})

        assert r.status_code == 200
        data = r.json()
        # All sections present but with errors
        for section in ("quote", "info", "dcf", "technicals", "news"):
            assert section in data
            assert "error" in data[section]
        assert data.get("_partial") is True

    def test_cache_not_set_when_quote_fails(self, client):
        """Aggregated result must NOT be cached when the quote section fails."""
        from core.python_runner import PythonRunnerError

        call_count = {"n": 0}

        def _quote_fails(*args, **kwargs):
            idx = call_count["n"]
            call_count["n"] += 1
            if idx == 0:  # quote is first
                m = MagicMock()
                # PythonRunnerError takes positional args only
                m.run = AsyncMock(side_effect=PythonRunnerError("quote failed"))
                return m
            responses = [INFO_RESP, DCF_RESP, TECH_RESP, NEWS_RESP]
            rv = responses[idx - 1] if (idx - 1) < len(responses) else {"success": True}
            return _mock_runner(rv)

        mock_set = AsyncMock(return_value=True)
        with (
            patch("app.routers.analytics.cache.get", AsyncMock(return_value=None)),
            patch("app.routers.analytics.cache.set", mock_set),
            patch("app.routers.analytics.cache.build_key", return_value="test:comprehensive:key"),
            patch("app.routers.analytics.cache.quote_key", return_value="test:quote"),
            patch("app.routers.analytics.cache.equity_info_key", return_value="test:info"),
            patch("app.routers.analytics.get_runner", side_effect=_quote_fails),
        ):
            r = client.post("/api/v1/analytics/comprehensive/AAPL", json={})

        assert r.status_code == 200
        data = r.json()
        # Quote section must have an error
        assert "error" in data.get("quote", {})
        # The aggregated response (identified by having "symbol" key) must NOT be cached.
        # We check that no cache.set call stored a dict with "symbol" == "AAPL" (the aggregated result).
        aggregated_cache_calls = [
            c for c in mock_set.call_args_list
            if c.args
            and isinstance(c.args[1], dict)
            and c.args[1].get("symbol") == "AAPL"
            and "quote" in c.args[1]
        ]
        assert len(aggregated_cache_calls) == 0, "Must not cache aggregated result when quote section fails"

"""Phase 2 — Multi-Asset Analytics API tests."""
from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.dependencies import get_api_key

HEADERS = {"X-API-Key": "test-key"}

@pytest.fixture
def client():
    async def _mock_key(x_api_key=None): return "test-key"
    app.dependency_overrides[get_api_key] = _mock_key
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

def _mock_runner(rv):
    m = MagicMock(); m.run = AsyncMock(return_value=rv); return m

QUOTE_RESP = {"success": True, "data": {"symbol": "AAPL", "price": 150.0}}
HISTORY_RESP = {"success": True, "data": {"bars": []}}
GREEKS_RESP = {"success": True, "data": {"delta": 0.5, "gamma": 0.02}}
PORTFOLIO_RESP = {"success": True, "data": {"weights": {"AAPL": 0.5, "MSFT": 0.5}}}

class TestMarketData:
    def test_get_quote_cache_miss(self, client):
        with (
            patch("app.routers.analytics.cache.get", AsyncMock(return_value=None)),
            patch("app.routers.analytics.cache.set", AsyncMock(return_value=True)),
            patch("app.routers.analytics.get_runner", return_value=_mock_runner(QUOTE_RESP)),
        ):
            r = client.get("/api/v1/market/quote/AAPL")
        assert r.status_code == 200

    def test_get_quote_cache_hit(self, client):
        with (
            patch("app.routers.analytics.cache.get", AsyncMock(return_value=QUOTE_RESP)),
            patch("app.routers.analytics.get_runner") as mock_runner,
        ):
            r = client.get("/api/v1/market/quote/AAPL")
        assert r.status_code == 200
        mock_runner.assert_not_called()

    def test_get_history(self, client):
        with (
            patch("app.routers.analytics.cache.get", AsyncMock(return_value=None)),
            patch("app.routers.analytics.cache.set", AsyncMock(return_value=True)),
            patch("app.routers.analytics.get_runner", return_value=_mock_runner(HISTORY_RESP)),
        ):
            r = client.get("/api/v1/market/history/AAPL?start=2024-01-01&interval=1d")
        assert r.status_code == 200

    def test_batch_quotes(self, client):
        with patch("app.routers.analytics.get_runner", return_value=_mock_runner({"success": True, "quotes": []})):
            r = client.post("/api/v1/market/quotes/batch", json={"symbols": ["AAPL", "MSFT"]})
        assert r.status_code == 200

    def test_search_symbols(self, client):
        with patch("app.routers.analytics.get_runner", return_value=_mock_runner({"results": []})):
            r = client.get("/api/v1/market/search?q=apple")
        assert r.status_code == 200

class TestEquityResearch:
    def test_equity_info(self, client):
        with (
            patch("app.routers.analytics.cache.get", AsyncMock(return_value=None)),
            patch("app.routers.analytics.cache.set", AsyncMock(return_value=True)),
            patch("app.routers.analytics.get_runner", return_value=_mock_runner({"success": True, "data": {}})),
        ):
            r = client.get("/api/v1/equity/AAPL/info")
        assert r.status_code == 200

    def test_dcf_requires_auth(self, client):
        app.dependency_overrides.clear()
        r = client.post("/api/v1/equity/AAPL/dcf", json={})
        assert r.status_code == 401
        async def _mock(x_api_key=None): return "test-key"
        app.dependency_overrides[get_api_key] = _mock

    def test_dcf_success(self, client):
        dcf_resp = {"success": True, "data": {"intrinsic_value": 180.0, "current_price": 150.0}}
        with (
            patch("app.routers.analytics.cache.get", AsyncMock(return_value=None)),
            patch("app.routers.analytics.cache.set", AsyncMock(return_value=True)),
            patch("app.routers.analytics.get_runner", return_value=_mock_runner(dcf_resp)),
        ):
            r = client.post("/api/v1/equity/AAPL/dcf", json={}, headers=HEADERS)
        assert r.status_code == 200

class TestPortfolioAnalytics:
    def test_optimize_portfolio(self, client):
        with patch("app.routers.analytics.get_runner", return_value=_mock_runner(PORTFOLIO_RESP)):
            r = client.post(
                "/api/v1/portfolio/optimize",
                json={"symbols": ["AAPL", "MSFT"], "method": "mean_variance"},
                headers=HEADERS,
            )
        assert r.status_code == 200

    def test_portfolio_metrics(self, client):
        with patch("app.routers.analytics.get_runner", return_value=_mock_runner({"success": True})):
            r = client.post(
                "/api/v1/portfolio/metrics",
                json={"holdings": [{"symbol": "AAPL", "weight": 1.0}], "start_date": "2024-01-01", "end_date": "2025-01-01"},
                headers=HEADERS,
            )
        assert r.status_code == 200

    def test_portfolio_var(self, client):
        with patch("app.routers.analytics.get_runner", return_value=_mock_runner({"success": True, "var": 0.05})):
            r = client.post(
                "/api/v1/portfolio/var",
                json={"holdings": [{"symbol": "AAPL", "weight": 1.0}]},
                headers=HEADERS,
            )
        assert r.status_code == 200

class TestDerivatives:
    def test_compute_greeks(self, client):
        with (
            patch("app.routers.analytics.cache.get", AsyncMock(return_value=None)),
            patch("app.routers.analytics.cache.set", AsyncMock(return_value=True)),
            patch("app.routers.analytics.get_runner", return_value=_mock_runner(GREEKS_RESP)),
        ):
            r = client.post(
                "/api/v1/derivatives/greeks",
                json={"S": 150.0, "K": 155.0, "T": 0.25, "r": 0.05, "sigma": 0.2, "option_type": "call"},
            )
        assert r.status_code == 200

    def test_implied_vol(self, client):
        with patch("app.routers.analytics.get_runner", return_value=_mock_runner({"success": True, "iv": 0.22})):
            r = client.post(
                "/api/v1/derivatives/implied-vol",
                json={"S": 150.0, "K": 155.0, "T": 0.25, "r": 0.05, "market_price": 5.0, "option_type": "call"},
            )
        assert r.status_code == 200

class TestTechnical:
    def test_compute_indicators(self, client):
        with (
            patch("app.routers.analytics.cache.get", AsyncMock(return_value=None)),
            patch("app.routers.analytics.cache.set", AsyncMock(return_value=True)),
            patch("app.routers.analytics.get_runner", return_value=_mock_runner({"success": True, "bars": []})),
        ):
            r = client.post(
                "/api/v1/technical/indicators",
                json={"symbol": "AAPL", "indicators": ["RSI", "MACD"]},
            )
        assert r.status_code == 200

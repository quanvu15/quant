"""Phase 3 — QuantLib Suite API tests."""
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

BSM_RESP = {"success": True, "price": 5.23, "delta": 0.45, "gamma": 0.02}
BOND_RESP = {"success": True, "price": 98.5, "ytm": 0.055, "duration": 4.2}

class TestOptionPricing:
    BASE = {"S": 150.0, "K": 155.0, "T": 0.25, "r": 0.05, "sigma": 0.2, "option_type": "call"}

    def test_option_price(self, client):
        with (
            patch("app.routers.quantlib.cache.get", AsyncMock(return_value=None)),
            patch("app.routers.quantlib.cache.set", AsyncMock(return_value=True)),
            patch("app.routers.quantlib.get_runner", return_value=_mock_runner(BSM_RESP)),
        ):
            r = client.post("/api/v1/quant/option/price", json=self.BASE)
        assert r.status_code == 200

    def test_option_greeks(self, client):
        with (
            patch("app.routers.quantlib.cache.get", AsyncMock(return_value=None)),
            patch("app.routers.quantlib.cache.set", AsyncMock(return_value=True)),
            patch("app.routers.quantlib.get_runner", return_value=_mock_runner(BSM_RESP)),
        ):
            r = client.post("/api/v1/quant/option/greeks", json=self.BASE)
        assert r.status_code == 200

    def test_batch_greeks_requires_auth(self, client):
        app.dependency_overrides.clear()
        r = client.post("/api/v1/quant/option/batch-greeks", json={"contracts": [self.BASE]})
        assert r.status_code == 401
        async def _mock(x_api_key=None): return "test-key"
        app.dependency_overrides[get_api_key] = _mock

    def test_batch_greeks(self, client):
        with patch("app.routers.quantlib.get_runner", return_value=_mock_runner({"results": [BSM_RESP]})):
            r = client.post(
                "/api/v1/quant/option/batch-greeks",
                json={"contracts": [self.BASE, self.BASE]},
                headers=HEADERS,
            )
        assert r.status_code == 200

    def test_fx_option(self, client):
        with patch("app.routers.quantlib.get_runner", return_value=_mock_runner(BSM_RESP)):
            r = client.post(
                "/api/v1/quant/option/fx",
                json={"S": 1.1, "K": 1.12, "T": 0.25, "r_d": 0.05, "r_f": 0.02, "sigma": 0.1, "option_type": "call"},
            )
        assert r.status_code == 200

class TestFixedIncome:
    BOND_BASE = {"face_value": 1000.0, "coupon_rate": 0.05, "maturity_years": 5.0, "ytm": 0.055}

    def test_bond_price(self, client):
        with (
            patch("app.routers.quantlib.cache.get", AsyncMock(return_value=None)),
            patch("app.routers.quantlib.cache.set", AsyncMock(return_value=True)),
            patch("app.routers.quantlib.get_runner", return_value=_mock_runner(BOND_RESP)),
        ):
            r = client.post("/api/v1/quant/bond/price", json=self.BOND_BASE)
        assert r.status_code == 200

    def test_bond_ytm(self, client):
        with patch("app.routers.quantlib.get_runner", return_value=_mock_runner(BOND_RESP)):
            r = client.post(
                "/api/v1/quant/bond/ytm",
                json={"face_value": 1000.0, "coupon_rate": 0.05, "maturity_years": 5.0, "clean_price": 98.5},
            )
        assert r.status_code == 200

class TestRiskModels:
    def test_var_historical(self, client):
        returns = [-0.01, 0.02, -0.03, 0.01, 0.005] * 20
        with patch("app.routers.quantlib.get_runner", return_value=_mock_runner({"var": 0.025, "cvar": 0.035})):
            r = client.post(
                "/api/v1/quant/risk/var",
                json={"returns": returns, "method": "historical"},
                headers=HEADERS,
            )
        assert r.status_code == 200

    def test_stress_test(self, client):
        with patch("app.routers.quantlib.get_runner", return_value=_mock_runner({"results": []})):
            r = client.post(
                "/api/v1/quant/risk/stress-test",
                json={
                    "portfolio": [{"symbol": "AAPL", "weight": 1.0}],
                    "scenarios": [{"name": "2008 Crisis", "shocks": {"equity": -0.4}}],
                },
                headers=HEADERS,
            )
        assert r.status_code == 200

class TestStochasticModels:
    def test_gbm_simulation(self, client):
        with patch("app.routers.quantlib.get_runner", return_value=_mock_runner({"paths": [], "statistics": {}})):
            r = client.post(
                "/api/v1/quant/stochastic/gbm",
                json={"S0": 100.0, "mu": 0.1, "sigma": 0.2, "T": 1.0, "n_paths": 100, "n_steps": 252},
                headers=HEADERS,
            )
        assert r.status_code == 200

    def test_heston_price(self, client):
        with patch("app.routers.quantlib.get_runner", return_value=_mock_runner({"price": 5.5, "implied_vol": 0.21})):
            r = client.post(
                "/api/v1/quant/stochastic/heston",
                json={"S0": 100.0, "v0": 0.04, "kappa": 2.0, "theta": 0.04, "sigma_v": 0.3, "rho": -0.7, "r": 0.05, "T": 1.0, "K": 100.0},
                headers=HEADERS,
            )
        assert r.status_code == 200

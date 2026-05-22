"""Phase 4 — Global Intelligence API tests."""
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

class TestGeopolitics:
    def test_get_events(self, client):
        with (
            patch("app.routers.intelligence.cache.get", AsyncMock(return_value=None)),
            patch("app.routers.intelligence.cache.set", AsyncMock(return_value=True)),
            patch("app.routers.intelligence.get_runner", return_value=_mock_runner({"events": [], "total": 0})),
        ):
            r = client.get("/api/v1/intelligence/geopolitics/events?country=Ukraine&days=30")
        assert r.status_code == 200

    def test_get_events_cache_hit(self, client):
        cached = {"events": [{"event_id": "1"}], "total": 1}
        with (
            patch("app.routers.intelligence.cache.get", AsyncMock(return_value=cached)),
            patch("app.routers.intelligence.get_runner") as mock_runner,
        ):
            r = client.get("/api/v1/intelligence/geopolitics/events")
        assert r.status_code == 200
        mock_runner.assert_not_called()

    def test_get_countries(self, client):
        with (
            patch("app.routers.intelligence.cache.get", AsyncMock(return_value=None)),
            patch("app.routers.intelligence.cache.set", AsyncMock(return_value=True)),
            patch("app.routers.intelligence.get_runner", return_value=_mock_runner({"countries": []})),
        ):
            r = client.get("/api/v1/intelligence/geopolitics/countries")
        assert r.status_code == 200

class TestMaritime:
    def test_get_vessel_requires_auth(self, client):
        app.dependency_overrides.clear()
        r = client.get("/api/v1/intelligence/maritime/vessel/1234567")
        assert r.status_code == 401
        async def _mock(x_api_key=None): return "test-key"
        app.dependency_overrides[get_api_key] = _mock

    def test_get_vessel(self, client):
        vessel = {"imo": "1234567", "name": "TEST VESSEL", "latitude": 1.0, "longitude": 103.0}
        with (
            patch("app.routers.intelligence.cache.get", AsyncMock(return_value=None)),
            patch("app.routers.intelligence.cache.set", AsyncMock(return_value=True)),
            patch("app.routers.intelligence.get_runner", return_value=_mock_runner(vessel)),
        ):
            r = client.get("/api/v1/intelligence/maritime/vessel/1234567", headers=HEADERS)
        assert r.status_code == 200

    def test_vessels_batch(self, client):
        with patch("app.routers.intelligence.get_runner", return_value=_mock_runner({"vessels": []})):
            r = client.post(
                "/api/v1/intelligence/maritime/vessels/batch",
                json={"imos": ["1234567", "7654321"]},
                headers=HEADERS,
            )
        assert r.status_code == 200

    def test_vessels_area(self, client):
        with patch("app.routers.intelligence.get_runner", return_value=_mock_runner({"vessels": [], "total_count": 0})):
            r = client.post(
                "/api/v1/intelligence/maritime/vessels/area",
                json={"lat_min": 1.0, "lat_max": 2.0, "lon_min": 103.0, "lon_max": 104.0},
                headers=HEADERS,
            )
        assert r.status_code == 200

class TestEconomics:
    def test_fred_series(self, client):
        fred_resp = {"series_id": "CPIAUCSL", "observations": []}
        with (
            patch("app.routers.intelligence.cache.get", AsyncMock(return_value=None)),
            patch("app.routers.intelligence.cache.set", AsyncMock(return_value=True)),
            patch("app.routers.intelligence.get_runner", return_value=_mock_runner(fred_resp)),
        ):
            r = client.get("/api/v1/intelligence/economics/fred/CPIAUCSL")
        assert r.status_code == 200

    def test_worldbank(self, client):
        with (
            patch("app.routers.intelligence.cache.get", AsyncMock(return_value=None)),
            patch("app.routers.intelligence.cache.set", AsyncMock(return_value=True)),
            patch("app.routers.intelligence.get_runner", return_value=_mock_runner({"data": []})),
        ):
            r = client.get("/api/v1/intelligence/economics/worldbank/NY.GDP.MKTP.CD/US")
        assert r.status_code == 200

    def test_economic_calendar(self, client):
        with (
            patch("app.routers.intelligence.cache.get", AsyncMock(return_value=None)),
            patch("app.routers.intelligence.cache.set", AsyncMock(return_value=True)),
            patch("app.routers.intelligence.get_runner", return_value=_mock_runner({"events": []})),
        ):
            r = client.get("/api/v1/intelligence/economics/calendar?limit=10")
        assert r.status_code == 200

    def test_central_bank(self, client):
        with (
            patch("app.routers.intelligence.cache.get", AsyncMock(return_value=None)),
            patch("app.routers.intelligence.cache.set", AsyncMock(return_value=True)),
            patch("app.routers.intelligence.get_runner", return_value=_mock_runner({"data": []})),
        ):
            r = client.get("/api/v1/intelligence/economics/central-banks/fed")
        assert r.status_code == 200

class TestGovData:
    def test_bls_series(self, client):
        with (
            patch("app.routers.intelligence.cache.get", AsyncMock(return_value=None)),
            patch("app.routers.intelligence.cache.set", AsyncMock(return_value=True)),
            patch("app.routers.intelligence.get_runner", return_value=_mock_runner({"data": []})),
        ):
            r = client.get("/api/v1/intelligence/govdata/us/bls/LNS14000000")
        assert r.status_code == 200

    def test_eia_energy(self, client):
        with (
            patch("app.routers.intelligence.cache.get", AsyncMock(return_value=None)),
            patch("app.routers.intelligence.cache.set", AsyncMock(return_value=True)),
            patch("app.routers.intelligence.get_runner", return_value=_mock_runner({"series": []})),
        ):
            r = client.get("/api/v1/intelligence/energy/eia/petroleum")
        assert r.status_code == 200

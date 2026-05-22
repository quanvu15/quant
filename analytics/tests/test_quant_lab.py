"""Phase 5 — AI Quant Lab API tests."""
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

class TestJobManagement:
    def test_list_jobs_empty(self, client):
        with patch("app.routers.quant_lab.list_jobs", AsyncMock(return_value=[])):
            r = client.get("/api/v1/quant-lab/jobs")
        assert r.status_code == 200
        assert r.json()["jobs"] == []

    def test_get_job_not_found(self, client):
        with patch("app.routers.quant_lab.get_job", AsyncMock(return_value=None)):
            r = client.get("/api/v1/quant-lab/jobs/nonexistent-id")
        assert r.status_code == 404

    def test_get_job_found(self, client):
        job = {
            "job_id": "abc-123", "type": "backtest", "status": "completed",
            "progress": 100, "created_at": 1000.0, "result": {"metrics": {}},
        }
        with patch("app.routers.quant_lab.get_job", AsyncMock(return_value=job)):
            r = client.get("/api/v1/quant-lab/jobs/abc-123")
        assert r.status_code == 200
        data = r.json()
        assert data["job_id"] == "abc-123"
        # result should NOT be in status response
        assert "result" not in data

    def test_get_job_result(self, client):
        job = {"job_id": "abc-123", "status": "completed", "result": {"equity_curve": []}}
        with patch("app.routers.quant_lab.get_job", AsyncMock(return_value=job)):
            r = client.get("/api/v1/quant-lab/jobs/abc-123/result")
        assert r.status_code == 200
        assert r.json()["result"] == {"equity_curve": []}

    def test_cancel_job(self, client):
        with patch("app.routers.quant_lab.cancel_job", AsyncMock(return_value=True)):
            r = client.delete("/api/v1/quant-lab/jobs/abc-123")
        assert r.status_code == 200
        assert r.json()["cancelled"] is True

class TestBacktest:
    def test_submit_backtest_returns_job_id(self, client):
        with (
            patch("app.routers.quant_lab.create_job", AsyncMock(return_value="job-xyz")),
            patch("app.routers.quant_lab.run_job_async", AsyncMock()),
            patch("asyncio.create_task"),
        ):
            r = client.post(
                "/api/v1/quant-lab/backtest",
                json={
                    "strategy": {"type": "momentum"},
                    "universe": {"market": "us"},
                    "start_date": "2020-01-01",
                    "end_date": "2024-12-31",
                },
                headers=HEADERS,
            )
        assert r.status_code == 202
        data = r.json()
        assert "job_id" in data
        assert data["status"] == "queued"

class TestModelTraining:
    def test_train_model_returns_job_id(self, client):
        with (
            patch("app.routers.quant_lab.create_job", AsyncMock(return_value="job-train-1")),
            patch("asyncio.create_task"),
        ):
            r = client.post(
                "/api/v1/quant-lab/models/train",
                json={"model_type": "lightgbm", "universe": {"market": "us"}, "start_date": "2020-01-01", "end_date": "2024-01-01"},
                headers=HEADERS,
            )
        assert r.status_code == 202
        assert r.json()["status"] == "queued"

    def test_predict_synchronous(self, client):
        with patch("app.routers.quant_lab.get_runner", return_value=_mock_runner({"predictions": []})):
            r = client.post(
                "/api/v1/quant-lab/models/model-123/predict",
                json={"symbols": ["AAPL", "MSFT"]},
                headers=HEADERS,
            )
        assert r.status_code == 200

class TestRLTrading:
    def test_train_rl_returns_job_id(self, client):
        with (
            patch("app.routers.quant_lab.create_job", AsyncMock(return_value="job-rl-1")),
            patch("asyncio.create_task"),
        ):
            r = client.post(
                "/api/v1/quant-lab/rl/train",
                json={"algorithm": "PPO", "environment": {"symbols": ["AAPL"], "start_date": "2020-01-01", "end_date": "2024-01-01"}},
                headers=HEADERS,
            )
        assert r.status_code == 202

class TestReporting:
    def test_tearsheet_returns_job_id(self, client):
        with (
            patch("app.routers.quant_lab.create_job", AsyncMock(return_value="job-report-1")),
            patch("asyncio.create_task"),
        ):
            r = client.post(
                "/api/v1/quant-lab/report/tearsheet",
                json={"returns": [{"date": "2024-01-01", "return": 0.01}]},
                headers=HEADERS,
            )
        assert r.status_code == 202

    def test_factor_attribution_synchronous(self, client):
        with patch("app.routers.quant_lab.get_runner", return_value=_mock_runner({"attribution": []})):
            r = client.post(
                "/api/v1/quant-lab/report/factor-attribution",
                json={"portfolio_returns": [], "factor_returns": {}},
                headers=HEADERS,
            )
        assert r.status_code == 200

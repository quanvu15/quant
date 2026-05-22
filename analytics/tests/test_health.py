"""
Phase 0 — Test Gate: health endpoint and basic infrastructure.
"""

import pytest


def test_health_returns_ok(client):
    """GET /health should return status ok."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "env" in data


def test_health_includes_redis_status(client):
    """GET /health should include redis field."""
    response = client.get("/health")
    data = response.json()
    assert "redis" in data
    assert data["redis"] in ("ok", "degraded")


def test_root_endpoint(client):
    """GET / should return API info."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data


def test_docs_available(client):
    """GET /docs should return 200."""
    response = client.get("/docs")
    assert response.status_code == 200


def test_openapi_schema(client):
    """GET /openapi.json should return valid schema."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "Fincept Terminal API"
    assert "paths" in schema


def test_request_id_header(client):
    """Responses should include X-Request-ID header."""
    response = client.get("/health")
    assert "x-request-id" in response.headers


def test_response_time_header(client):
    """Responses should include X-Response-Time header."""
    response = client.get("/health")
    assert "x-response-time" in response.headers


@pytest.mark.asyncio
async def test_health_async(async_client):
    """Async health check."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

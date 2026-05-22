"""
Pytest configuration and shared fixtures.
"""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app


# ── Override settings for tests ───────────────────────────────────────────────

@pytest.fixture(autouse=True)
def override_settings(monkeypatch):
    """Use test-safe settings."""
    monkeypatch.setattr(settings, "ENV", "test")
    monkeypatch.setattr(settings, "MASTER_API_KEY", "fincept_admin_test_key")
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "test-secret-key")
    monkeypatch.setattr(settings, "REDIS_URL", "redis://localhost:6379/15")  # DB 15 for tests


# ── Mock Redis ────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_cache():
    """Mock Redis cache to avoid requiring a real Redis instance."""
    with patch("core.cache.cache") as mock:
        mock.connect = AsyncMock()
        mock.disconnect = AsyncMock()
        mock.ping = AsyncMock(return_value=True)
        mock.get = AsyncMock(return_value=None)
        mock.set = AsyncMock(return_value=True)
        mock.delete = AsyncMock(return_value=True)
        mock.incr = AsyncMock(return_value=1)
        mock.expire = AsyncMock(return_value=True)
        mock.get_or_set = AsyncMock(side_effect=lambda key, factory, ttl=60: factory())
        yield mock


# ── HTTP clients ──────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    """Synchronous test client."""
    with TestClient(app) as c:
        yield c


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Async test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


# ── Auth headers ──────────────────────────────────────────────────────────────

@pytest.fixture
def auth_headers():
    """Headers with valid master API key."""
    return {"X-API-Key": "fincept_admin_test_key"}

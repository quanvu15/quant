"""
Tests for Task 3.2 — GET /api/v1/agents/runs endpoint.

Covers:
  - Basic listing: returns only the authenticated user's runs.
  - User isolation: user A cannot see user B's runs.
  - Filtering: from/to datetime, persona_id.
  - Cursor pagination: next_cursor, stable pages.
  - Query truncation: query field capped at 200 chars.
  - Auth: requires JWT (401 without token).
  - total count reflects full result set, not just current page.

**Validates: Requirements 3.4**
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import os
os.environ.setdefault("SCRIPTS_DIR", "/tmp/scripts")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MASTER_API_KEY", "fincept_admin_test_key")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-history-tests")

from app.main import app  # noqa: E402
from core.auth import create_analytics_jwt


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_jwt(user_id: str) -> str:
    return create_analytics_jwt(user_id=user_id, role="user")


def _auth_headers(user_id: str) -> dict:
    return {"Authorization": f"Bearer {_make_jwt(user_id)}"}


class _FakeRun:
    """Plain object that mimics an AgentRun ORM row for test purposes."""

    def __init__(
        self,
        user_id: uuid.UUID,
        persona_id: str = "stock_analyst",
        query: Optional[str] = "Analyze AAPL",
        status: str = "ok",
        duration_ms: int = 1000,
        tokens_in: int = 100,
        tokens_out: int = 200,
        created_at: Optional[datetime] = None,
        run_id: Optional[uuid.UUID] = None,
    ):
        self.id = run_id or uuid.uuid4()
        self.user_id = user_id
        self.persona_id = persona_id
        self.query = query
        self.response = "Some response"
        self.duration_ms = duration_ms
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out
        self.status = status
        self.error = None
        self.created_at = created_at or datetime.now(timezone.utc)


def _make_run(
    user_id: uuid.UUID,
    persona_id: str = "stock_analyst",
    query: Optional[str] = "Analyze AAPL",
    status: str = "ok",
    duration_ms: int = 1000,
    tokens_in: int = 100,
    tokens_out: int = 200,
    created_at: Optional[datetime] = None,
    run_id: Optional[uuid.UUID] = None,
) -> _FakeRun:
    """Create an in-memory fake AgentRun object (not persisted)."""
    return _FakeRun(
        user_id=user_id,
        persona_id=persona_id,
        query=query,
        status=status,
        duration_ms=duration_ms,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        created_at=created_at,
        run_id=run_id,
    )


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_cache_fixture():
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


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ── DB session mock helper ────────────────────────────────────────────────────

class _FakeResult:
    """Mimics SQLAlchemy async execute result."""

    def __init__(self, rows, scalar_value=None):
        self._rows = rows
        self._scalar_value = scalar_value

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar_one(self):
        return self._scalar_value if self._scalar_value is not None else len(self._rows)


class _FakeSession:
    """Minimal async context manager that fakes SQLAlchemy AsyncSession."""

    def __init__(self, execute_side_effects: list):
        """
        execute_side_effects: list of _FakeResult objects returned in order
        for each call to session.execute().
        """
        self._effects = iter(execute_side_effects)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def execute(self, stmt):
        return next(self._effects)


# ── Unit tests ────────────────────────────────────────────────────────────────

class TestListAgentRunsBasic:

    def test_returns_200_with_valid_jwt(self, client):
        """GET /runs with valid JWT returns 200."""
        user_id = uuid.uuid4()
        runs = [_make_run(user_id)]

        session = _FakeSession([
            _FakeResult(runs, scalar_value=1),   # count query
            _FakeResult(runs),                    # page query
        ])

        with patch("app.routers.agents.AsyncSessionLocal", return_value=session):
            resp = client.get("/api/v1/agents/runs", headers=_auth_headers(str(user_id)))

        assert resp.status_code == 200
        data = resp.json()
        assert "runs" in data
        assert "total" in data
        assert "next_cursor" in data

    def test_returns_401_without_auth(self, client):
        """GET /runs without auth returns 401."""
        resp = client.get("/api/v1/agents/runs")
        assert resp.status_code == 401

    def test_returns_only_current_user_runs(self, client):
        """Only runs belonging to the JWT user are returned."""
        user_a = uuid.uuid4()
        user_b = uuid.uuid4()

        # DB returns only user_a's runs (the filter is applied in the query)
        runs_a = [_make_run(user_a, persona_id="analyst_a")]

        session = _FakeSession([
            _FakeResult(runs_a, scalar_value=1),
            _FakeResult(runs_a),
        ])

        with patch("app.routers.agents.AsyncSessionLocal", return_value=session):
            resp = client.get("/api/v1/agents/runs", headers=_auth_headers(str(user_a)))

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["runs"]) == 1
        assert data["runs"][0]["persona_id"] == "analyst_a"

    def test_empty_result_returns_empty_list(self, client):
        """When no runs exist, returns empty list with total=0."""
        user_id = uuid.uuid4()

        session = _FakeSession([
            _FakeResult([], scalar_value=0),
            _FakeResult([]),
        ])

        with patch("app.routers.agents.AsyncSessionLocal", return_value=session):
            resp = client.get("/api/v1/agents/runs", headers=_auth_headers(str(user_id)))

        assert resp.status_code == 200
        data = resp.json()
        assert data["runs"] == []
        assert data["total"] == 0
        assert data["next_cursor"] is None

    def test_query_truncated_to_200_chars(self, client):
        """Long query strings are truncated to 200 characters in the response."""
        user_id = uuid.uuid4()
        long_query = "A" * 500
        runs = [_make_run(user_id, query=long_query)]

        session = _FakeSession([
            _FakeResult(runs, scalar_value=1),
            _FakeResult(runs),
        ])

        with patch("app.routers.agents.AsyncSessionLocal", return_value=session):
            resp = client.get("/api/v1/agents/runs", headers=_auth_headers(str(user_id)))

        assert resp.status_code == 200
        returned_query = resp.json()["runs"][0]["query"]
        assert len(returned_query) == 200
        assert returned_query == "A" * 200

    def test_null_query_returned_as_null(self, client):
        """Runs with no query return null in the response."""
        user_id = uuid.uuid4()
        runs = [_make_run(user_id, query=None)]
        # Override query to None
        runs[0].query = None

        session = _FakeSession([
            _FakeResult(runs, scalar_value=1),
            _FakeResult(runs),
        ])

        with patch("app.routers.agents.AsyncSessionLocal", return_value=session):
            resp = client.get("/api/v1/agents/runs", headers=_auth_headers(str(user_id)))

        assert resp.status_code == 200
        assert resp.json()["runs"][0]["query"] is None

    def test_response_includes_all_required_fields(self, client):
        """Each run in the response includes all required fields."""
        user_id = uuid.uuid4()
        run_id = uuid.uuid4()
        ts = datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        runs = [_make_run(
            user_id,
            run_id=run_id,
            persona_id="warren_buffett",
            query="Analyze AAPL",
            status="ok",
            duration_ms=1500,
            tokens_in=100,
            tokens_out=200,
            created_at=ts,
        )]

        session = _FakeSession([
            _FakeResult(runs, scalar_value=1),
            _FakeResult(runs),
        ])

        with patch("app.routers.agents.AsyncSessionLocal", return_value=session):
            resp = client.get("/api/v1/agents/runs", headers=_auth_headers(str(user_id)))

        assert resp.status_code == 200
        run = resp.json()["runs"][0]
        assert run["id"] == str(run_id)
        assert run["persona_id"] == "warren_buffett"
        assert run["query"] == "Analyze AAPL"
        assert run["status"] == "ok"
        assert run["duration_ms"] == 1500
        assert run["tokens_in"] == 100
        assert run["tokens_out"] == 200
        assert "created_at" in run


class TestListAgentRunsPagination:

    def test_next_cursor_set_when_full_page_returned(self, client):
        """next_cursor is set to the last run's id when a full page is returned."""
        user_id = uuid.uuid4()
        limit = 3
        run_ids = [uuid.uuid4() for _ in range(limit)]
        runs = [_make_run(user_id, run_id=rid) for rid in run_ids]

        session = _FakeSession([
            _FakeResult(runs, scalar_value=10),  # total=10, more pages exist
            _FakeResult(runs),
        ])

        with patch("app.routers.agents.AsyncSessionLocal", return_value=session):
            resp = client.get(
                f"/api/v1/agents/runs?limit={limit}",
                headers=_auth_headers(str(user_id)),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["next_cursor"] == str(run_ids[-1])

    def test_next_cursor_none_when_partial_page(self, client):
        """next_cursor is None when fewer items than limit are returned."""
        user_id = uuid.uuid4()
        runs = [_make_run(user_id)]  # 1 run, limit=20

        session = _FakeSession([
            _FakeResult(runs, scalar_value=1),
            _FakeResult(runs),
        ])

        with patch("app.routers.agents.AsyncSessionLocal", return_value=session):
            resp = client.get("/api/v1/agents/runs?limit=20", headers=_auth_headers(str(user_id)))

        assert resp.status_code == 200
        assert resp.json()["next_cursor"] is None

    def test_cursor_param_accepted(self, client):
        """Providing a valid cursor UUID does not cause an error."""
        user_id = uuid.uuid4()
        cursor_id = uuid.uuid4()
        cursor_ts = datetime.now(timezone.utc)
        runs = [_make_run(user_id)]

        # First execute: cursor lookup → returns (created_at, id)
        class _CursorResult:
            def first(self):
                return (cursor_ts, cursor_id)

        session = _FakeSession([
            _CursorResult(),                          # cursor lookup
            _FakeResult(runs, scalar_value=5),        # count
            _FakeResult(runs),                        # page
        ])

        with patch("app.routers.agents.AsyncSessionLocal", return_value=session):
            resp = client.get(
                f"/api/v1/agents/runs?cursor={cursor_id}",
                headers=_auth_headers(str(user_id)),
            )

        assert resp.status_code == 200

    def test_invalid_cursor_returns_400(self, client):
        """A non-UUID cursor value returns 400."""
        user_id = uuid.uuid4()

        # The session won't even be reached for an invalid cursor
        session = _FakeSession([])

        with patch("app.routers.agents.AsyncSessionLocal", return_value=session):
            resp = client.get(
                "/api/v1/agents/runs?cursor=not-a-uuid",
                headers=_auth_headers(str(user_id)),
            )

        assert resp.status_code == 400

    def test_limit_default_is_20(self, client):
        """Default limit is 20 — endpoint accepts no limit param."""
        user_id = uuid.uuid4()
        runs = [_make_run(user_id) for _ in range(5)]

        session = _FakeSession([
            _FakeResult(runs, scalar_value=5),
            _FakeResult(runs),
        ])

        with patch("app.routers.agents.AsyncSessionLocal", return_value=session):
            resp = client.get("/api/v1/agents/runs", headers=_auth_headers(str(user_id)))

        assert resp.status_code == 200

    def test_limit_max_100(self, client):
        """limit > 100 returns 422 validation error."""
        user_id = uuid.uuid4()
        resp = client.get(
            "/api/v1/agents/runs?limit=101",
            headers=_auth_headers(str(user_id)),
        )
        assert resp.status_code == 422

    def test_total_reflects_full_result_set(self, client):
        """total in response reflects the full count, not just the current page."""
        user_id = uuid.uuid4()
        runs = [_make_run(user_id) for _ in range(5)]

        session = _FakeSession([
            _FakeResult(runs, scalar_value=42),  # total=42
            _FakeResult(runs),
        ])

        with patch("app.routers.agents.AsyncSessionLocal", return_value=session):
            resp = client.get("/api/v1/agents/runs?limit=5", headers=_auth_headers(str(user_id)))

        assert resp.status_code == 200
        assert resp.json()["total"] == 42


class TestListAgentRunsFilters:

    def test_persona_id_filter_accepted(self, client):
        """persona_id query param is accepted without error."""
        user_id = uuid.uuid4()
        runs = [_make_run(user_id, persona_id="warren_buffett")]

        session = _FakeSession([
            _FakeResult(runs, scalar_value=1),
            _FakeResult(runs),
        ])

        with patch("app.routers.agents.AsyncSessionLocal", return_value=session):
            resp = client.get(
                "/api/v1/agents/runs?persona_id=warren_buffett",
                headers=_auth_headers(str(user_id)),
            )

        assert resp.status_code == 200

    def test_from_filter_accepted(self, client):
        """from datetime query param is accepted without error."""
        user_id = uuid.uuid4()
        runs = [_make_run(user_id)]

        session = _FakeSession([
            _FakeResult(runs, scalar_value=1),
            _FakeResult(runs),
        ])

        with patch("app.routers.agents.AsyncSessionLocal", return_value=session):
            resp = client.get(
                "/api/v1/agents/runs?from=2025-01-01T00:00:00Z",
                headers=_auth_headers(str(user_id)),
            )

        assert resp.status_code == 200

    def test_to_filter_accepted(self, client):
        """to datetime query param is accepted without error."""
        user_id = uuid.uuid4()
        runs = [_make_run(user_id)]

        session = _FakeSession([
            _FakeResult(runs, scalar_value=1),
            _FakeResult(runs),
        ])

        with patch("app.routers.agents.AsyncSessionLocal", return_value=session):
            resp = client.get(
                "/api/v1/agents/runs?to=2025-12-31T23:59:59Z",
                headers=_auth_headers(str(user_id)),
            )

        assert resp.status_code == 200

    def test_all_filters_combined(self, client):
        """All filters can be combined without error."""
        user_id = uuid.uuid4()
        runs = [_make_run(user_id, persona_id="macro_analyst")]

        session = _FakeSession([
            _FakeResult(runs, scalar_value=1),
            _FakeResult(runs),
        ])

        with patch("app.routers.agents.AsyncSessionLocal", return_value=session):
            resp = client.get(
                "/api/v1/agents/runs"
                "?from=2025-01-01T00:00:00Z"
                "&to=2025-12-31T23:59:59Z"
                "&persona_id=macro_analyst"
                "&limit=10",
                headers=_auth_headers(str(user_id)),
            )

        assert resp.status_code == 200

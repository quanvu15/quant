"""
Tests for Task 3.1 — Audit log for agent runs.

Covers:
  - PBT Property 9: every successful agent run has an entry in
    analytics.agent_runs with user_id matching the JWT claim.
  - Cancelled runs recorded with status='cancelled'.
  - Error runs recorded with status='error'.

**Validates: Requirements 3.4**

Testing strategy:
  - All DB writes are intercepted by mocking AsyncSessionLocal so no real
    Postgres is required.
  - JWT tokens are created with create_analytics_jwt() (real function) so the
    auth path is exercised end-to-end.
  - PBT uses hypothesis to generate many (user_id, agent_id, query) combos
    and verifies the audit record always carries the correct user_id.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st

# ── App bootstrap ─────────────────────────────────────────────────────────────

import os
os.environ.setdefault("SCRIPTS_DIR", "/tmp/scripts")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MASTER_API_KEY", "fincept_admin_test_key")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-audit-tests")

from app.main import app  # noqa: E402
from app.config import settings
from core.auth import create_analytics_jwt

# ── Helpers ───────────────────────────────────────────────────────────────────

LLM_CONFIG = {
    "model": "gpt-4o",
    "api_key": "sk-test-1234567890abcdef",  # Must be ≥10 chars to pass validation
    "base_url": "https://api.openai.com/v1",
    "temperature": 0.7,
    "max_tokens": 4096,
}

AGENT_SUCCESS_RESPONSE = {
    "success": True,
    "response": "Analysis complete.",
    "tokens_in": 100,
    "tokens_out": 200,
}


def _make_jwt(user_id: str) -> str:
    """Create a valid Analytics-native JWT for the given user_id."""
    return create_analytics_jwt(user_id=user_id, role="user")


def _auth_headers(user_id: str) -> dict:
    """Return headers with both API key and JWT Bearer token."""
    token = _make_jwt(user_id)
    return {
        "X-API-Key": "fincept_admin_test_key",
        "Authorization": f"Bearer {token}",
    }


def _mock_runner(return_value: dict):
    """Return a patched PythonRunner whose run() returns return_value."""
    mock = MagicMock()
    mock.run = AsyncMock(return_value=return_value)
    return mock


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    """Sync test client with API key dependency overridden."""
    from app.dependencies import get_api_key

    async def _mock_api_key(x_api_key=None):
        return "fincept_admin_test_key"

    app.dependency_overrides[get_api_key] = _mock_api_key
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def mock_cache_fixture():
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


# ── Unit tests ────────────────────────────────────────────────────────────────

class TestAgentRunAuditUnit:
    """Unit tests for _record_agent_run helper."""

    def test_record_agent_run_writes_correct_fields(self):
        """_record_agent_run creates AgentRun with correct user_id and status."""
        from app.routers.agents import _record_agent_run

        captured_runs = []

        class FakeSession:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            def add(self, obj):
                captured_runs.append(obj)
            async def commit(self):
                pass

        with patch("app.routers.agents.AsyncSessionLocal", return_value=FakeSession()):
            user_id = str(uuid.uuid4())
            asyncio.get_event_loop().run_until_complete(
                _record_agent_run(
                    user_id=user_id,
                    persona_id="warren_buffett",
                    query="Analyze AAPL",
                    response="Bullish outlook",
                    duration_ms=1500,
                    status="ok",
                    tokens_in=100,
                    tokens_out=200,
                )
            )

        assert len(captured_runs) == 1
        run = captured_runs[0]
        assert str(run.user_id) == user_id
        assert run.persona_id == "warren_buffett"
        assert run.query == "Analyze AAPL"
        assert run.response == "Bullish outlook"
        assert run.duration_ms == 1500
        assert run.status == "ok"
        assert run.tokens_in == 100
        assert run.tokens_out == 200

    def test_record_agent_run_error_status(self):
        """_record_agent_run stores error details in error JSONB field."""
        from app.routers.agents import _record_agent_run

        captured_runs = []

        class FakeSession:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            def add(self, obj):
                captured_runs.append(obj)
            async def commit(self):
                pass

        with patch("app.routers.agents.AsyncSessionLocal", return_value=FakeSession()):
            asyncio.get_event_loop().run_until_complete(
                _record_agent_run(
                    user_id=str(uuid.uuid4()),
                    persona_id="macro_analyst",
                    query="Macro scan",
                    response=None,
                    duration_ms=500,
                    status="error",
                    error={"message": "Script timed out"},
                )
            )

        run = captured_runs[0]
        assert run.status == "error"
        assert run.error == {"message": "Script timed out"}
        assert run.response is None

    def test_record_agent_run_cancelled_status(self):
        """_record_agent_run stores cancelled status correctly."""
        from app.routers.agents import _record_agent_run

        captured_runs = []

        class FakeSession:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            def add(self, obj):
                captured_runs.append(obj)
            async def commit(self):
                pass

        with patch("app.routers.agents.AsyncSessionLocal", return_value=FakeSession()):
            asyncio.get_event_loop().run_until_complete(
                _record_agent_run(
                    user_id=str(uuid.uuid4()),
                    persona_id="stock_analyst",
                    query="Analyze TSLA",
                    response=None,
                    duration_ms=200,
                    status="cancelled",
                )
            )

        run = captured_runs[0]
        assert run.status == "cancelled"

    def test_record_agent_run_db_failure_does_not_raise(self):
        """DB write failure in _record_agent_run must not propagate."""
        from app.routers.agents import _record_agent_run

        class BrokenSession:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            def add(self, obj):
                raise RuntimeError("DB connection lost")
            async def commit(self):
                pass

        with patch("app.routers.agents.AsyncSessionLocal", return_value=BrokenSession()):
            # Should not raise
            asyncio.get_event_loop().run_until_complete(
                _record_agent_run(
                    user_id=str(uuid.uuid4()),
                    persona_id="test",
                    query="test",
                    response=None,
                    duration_ms=100,
                    status="ok",
                )
            )


class TestAgentRunAuditEndpoint:
    """Integration-style tests for POST /run audit behaviour."""

    def test_successful_run_triggers_audit_with_correct_user_id(self, client):
        """POST /run → audit entry created with user_id from JWT sub claim."""
        user_id = str(uuid.uuid4())
        recorded = []

        async def _fake_record(**kwargs):
            recorded.append(kwargs)

        with (
            patch("app.routers.agents.get_runner", return_value=_mock_runner(AGENT_SUCCESS_RESPONSE)),
            patch("app.routers.agents._record_agent_run", new=_fake_record),
        ):
            resp = client.post(
                "/api/v1/agents/run",
                json={"query": "Analyze AAPL", "agent_id": "stock_analyst", "llm_config": LLM_CONFIG},
                headers=_auth_headers(user_id),
            )

        assert resp.status_code == 200
        assert len(recorded) == 1
        assert recorded[0]["user_id"] == user_id
        assert recorded[0]["status"] == "ok"
        assert recorded[0]["persona_id"] == "stock_analyst"

    def test_error_run_triggers_audit_with_error_status(self, client):
        """POST /run that raises → audit entry with status='error'."""
        from core.python_runner import PythonRunnerError

        user_id = str(uuid.uuid4())
        recorded = []

        async def _fake_record(**kwargs):
            recorded.append(kwargs)

        mock = MagicMock()
        mock.run = AsyncMock(side_effect=PythonRunnerError("Script failed", stderr="err", exit_code=1))

        with (
            patch("app.routers.agents.get_runner", return_value=mock),
            patch("app.routers.agents._record_agent_run", new=_fake_record),
        ):
            resp = client.post(
                "/api/v1/agents/run",
                json={"query": "Analyze AAPL", "agent_id": "stock_analyst", "llm_config": LLM_CONFIG},
                headers=_auth_headers(user_id),
            )

        # Error response (502 or 500)
        assert resp.status_code in (500, 502, 504)
        assert len(recorded) == 1
        assert recorded[0]["status"] == "error"
        assert recorded[0]["user_id"] == user_id

    def test_audit_user_id_matches_jwt_not_api_key(self, client):
        """user_id in audit entry comes from JWT sub, not API key identity."""
        user_id = str(uuid.uuid4())
        recorded = []

        async def _fake_record(**kwargs):
            recorded.append(kwargs)

        with (
            patch("app.routers.agents.get_runner", return_value=_mock_runner(AGENT_SUCCESS_RESPONSE)),
            patch("app.routers.agents._record_agent_run", new=_fake_record),
        ):
            resp = client.post(
                "/api/v1/agents/run",
                json={"query": "test", "llm_config": LLM_CONFIG},
                headers=_auth_headers(user_id),
            )

        assert resp.status_code == 200
        # user_id must be the JWT sub, not "anonymous" or an API key hash
        assert recorded[0]["user_id"] == user_id
        assert recorded[0]["user_id"] != "anonymous"

    def test_stream_successful_run_triggers_audit(self, client):
        """POST /run/stream → audit entry created after stream completes."""
        user_id = str(uuid.uuid4())
        recorded = []

        async def _fake_record(**kwargs):
            recorded.append(kwargs)

        async def _fake_stream(script, payload):
            yield "TOKEN: Analysis result"
            yield "DONE: Complete"

        mock = MagicMock()
        mock.stream = _fake_stream

        with (
            patch("app.routers.agents.get_runner", return_value=mock),
            patch("app.routers.agents._record_agent_run", new=_fake_record),
        ):
            resp = client.post(
                "/api/v1/agents/run/stream",
                json={"query": "Analyze AAPL", "agent_id": "warren_buffett", "llm_config": LLM_CONFIG},
                headers=_auth_headers(user_id),
            )

        assert resp.status_code == 200
        assert len(recorded) == 1
        assert recorded[0]["user_id"] == user_id
        assert recorded[0]["status"] == "ok"
        assert recorded[0]["persona_id"] == "warren_buffett"

    def test_stream_error_event_triggers_error_audit(self, client):
        """POST /run/stream with error SSE event → audit with status='error'."""
        user_id = str(uuid.uuid4())
        recorded = []

        async def _fake_record(**kwargs):
            recorded.append(kwargs)

        # _stream_agent emits error events when the subprocess outputs "ERROR: ..."
        # The _audited_stream checks for '"type": "error"' in the SSE chunk
        async def _fake_stream(script, payload):
            yield "ERROR: LLM provider error"

        mock = MagicMock()
        mock.stream = _fake_stream

        with (
            patch("app.routers.agents.get_runner", return_value=mock),
            patch("app.routers.agents._record_agent_run", new=_fake_record),
        ):
            resp = client.post(
                "/api/v1/agents/run/stream",
                json={"query": "test", "agent_id": "macro_analyst", "llm_config": LLM_CONFIG},
                headers=_auth_headers(user_id),
            )

        assert resp.status_code == 200  # SSE always 200, error is in stream
        assert len(recorded) == 1
        assert recorded[0]["status"] == "error"
        assert recorded[0]["user_id"] == user_id


# ── PBT Property 9 ────────────────────────────────────────────────────────────

# Strategies for generating valid UUIDs and non-empty strings
_uuid_strategy = st.uuids().map(str)
_agent_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="_"),
    min_size=1,
    max_size=50,
)
_query_strategy = st.text(min_size=1, max_size=200)


@given(
    user_id=_uuid_strategy,
    agent_id=_agent_id_strategy,
    query=_query_strategy,
)
@h_settings(
    max_examples=30,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
    deadline=None,
)
def test_property_9_agent_run_audit_user_id_matches_jwt(user_id, agent_id, query):
    """
    **Validates: Requirements 3.4**

    Property 9: Every successful agent run has an entry in analytics.agent_runs
    with user_id matching the JWT claim.

    For any valid (user_id, agent_id, query) combination:
      - POST /api/v1/agents/run with JWT containing user_id as sub
      - The audit record written to analytics.agent_runs must have
        user_id == jwt.sub
    """
    from app.dependencies import get_api_key

    async def _mock_api_key(x_api_key=None):
        return "fincept_admin_test_key"

    app.dependency_overrides[get_api_key] = _mock_api_key

    recorded = []

    async def _fake_record(**kwargs):
        recorded.append(kwargs)

    with (
        patch("core.cache.cache") as mock_cache,
        patch("app.routers.agents.get_runner", return_value=_mock_runner(AGENT_SUCCESS_RESPONSE)),
        patch("app.routers.agents._record_agent_run", new=_fake_record),
    ):
        mock_cache.connect = AsyncMock()
        mock_cache.disconnect = AsyncMock()
        mock_cache.ping = AsyncMock(return_value=True)
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock(return_value=True)
        mock_cache.delete = AsyncMock(return_value=True)
        mock_cache.incr = AsyncMock(return_value=1)
        mock_cache.expire = AsyncMock(return_value=True)
        mock_cache.get_or_set = AsyncMock(side_effect=lambda key, factory, ttl=60: factory())

        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.post(
                "/api/v1/agents/run",
                json={
                    "query": query,
                    "agent_id": agent_id,
                    "llm_config": {
                        "model": "gpt-4o",
                        "api_key": "sk-test-1234567890abcdef",
                        "base_url": "https://api.openai.com/v1",
                        "temperature": 0.7,
                        "max_tokens": 4096,
                    },
                },
                headers=_auth_headers(user_id),
            )

    app.dependency_overrides.clear()

    # The run must succeed
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    # Property 9: audit entry must exist with correct user_id
    assert len(recorded) >= 1, "No audit entry was created for the agent run"
    audit_entry = recorded[0]
    assert audit_entry["user_id"] == user_id, (
        f"Audit user_id {audit_entry['user_id']!r} does not match JWT sub {user_id!r}"
    )
    assert audit_entry["status"] == "ok", (
        f"Expected status='ok', got {audit_entry['status']!r}"
    )

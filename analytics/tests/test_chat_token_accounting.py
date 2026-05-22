"""
Tests for Phase 2, task 2.4 — Token accounting.

Covers:
  - POST /chat/completions parses usage.prompt_tokens / usage.completion_tokens
  - Tokens are stored in chat_messages.tokens_in / tokens_out / latency_ms
  - GET /chat/sessions/{id}/usage returns correct aggregate sums
  - Property 8 (design.md): tokens_in + tokens_out >= 0;
    cumulative sum per session matches sum of individual messages.

**Validates: Requirements 2.3**
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

# ── Bootstrap ─────────────────────────────────────────────────────────────────
import os
os.environ.setdefault("SCRIPTS_DIR", "/tmp/scripts")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MASTER_API_KEY", "test-master-key")

from app.main import app  # noqa: E402
from app.dependencies import get_jwt_user  # noqa: E402
from core.database import get_db  # noqa: E402
from models.db.chat import ChatMessage, ChatSession  # noqa: E402

# ── Constants ─────────────────────────────────────────────────────────────────

TEST_USER_ID = str(uuid.uuid4())
OTHER_USER_ID = str(uuid.uuid4())
SESSION_ID = str(uuid.uuid4())

JWT_PAYLOAD = {"sub": TEST_USER_ID, "email": "test@example.com", "role": "user"}

LLM_CONFIG = {
    "model": "gpt-4o-mini",
    "api_key": "sk-test-key",
    "base_url": "https://api.openai.com/v1",
    "temperature": 0.7,
    "max_tokens": 1024,
}


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    """Sync test client with JWT auth overridden."""
    async def _mock_jwt():
        return JWT_PAYLOAD

    app.dependency_overrides[get_jwt_user] = _mock_jwt
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


def _make_session(user_id: str = TEST_USER_ID) -> MagicMock:
    """Build a MagicMock that looks like a ChatSession for mocking."""
    s = MagicMock(spec=ChatSession)
    s.id = uuid.UUID(SESSION_ID)
    s.user_id = uuid.UUID(user_id)
    s.title = "Test session"
    s.persona_id = None
    s.model = "gpt-4o-mini"
    s.base_url = "https://api.openai.com/v1"
    s.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    s.messages = []
    return s


def _make_message(
    session_id: str = SESSION_ID,
    role: str = "assistant",
    content: str = "Hello",
    tokens_in: int = 10,
    tokens_out: int = 20,
    latency_ms: int = 300,
) -> MagicMock:
    """Build a MagicMock that looks like a ChatMessage for mocking."""
    m = MagicMock(spec=ChatMessage)
    m.id = uuid.uuid4()
    m.session_id = uuid.UUID(session_id)
    m.role = role
    m.content = content
    m.tokens_in = tokens_in
    m.tokens_out = tokens_out
    m.latency_ms = latency_ms
    m.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    m.tool_calls = None
    return m


def _mock_db_with_session(session: ChatSession):
    """Return a mock AsyncSession that returns the given session on scalar_one_or_none."""
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = session
    db.execute = AsyncMock(return_value=result_mock)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


# ── Non-streaming token accounting ───────────────────────────────────────────

class TestNonStreamingTokenAccounting:
    """POST /completions (stream=false) parses and stores token counts."""

    def _llm_response(self, tokens_in: int = 50, tokens_out: int = 100) -> dict:
        return {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "The answer is 42."},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": tokens_in,
                "completion_tokens": tokens_out,
                "total_tokens": tokens_in + tokens_out,
            },
        }

    def test_completions_returns_usage_fields(self, client):
        """Non-streaming response includes usage.prompt_tokens and completion_tokens."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = self._llm_response(50, 100)

        with patch("app.routers.chat.httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            resp = client.post(
                "/api/v1/chat/completions",
                json={
                    "messages": [{"role": "user", "content": "What is 6*7?"}],
                    "stream": False,
                    "llm_config": LLM_CONFIG,
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["usage"]["prompt_tokens"] == 50
        assert data["usage"]["completion_tokens"] == 100
        assert data["usage"]["total_tokens"] == 150
        assert "_latency_ms" in data

    def test_completions_tokens_non_negative(self, client):
        """Token counts in response are always >= 0 (Property 8)."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # Provider returns no usage field
        mock_resp.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "Hi"}}],
        }

        with patch("app.routers.chat.httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            resp = client.post(
                "/api/v1/chat/completions",
                json={
                    "messages": [{"role": "user", "content": "Hi"}],
                    "stream": False,
                    "llm_config": LLM_CONFIG,
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["usage"]["prompt_tokens"] >= 0
        assert data["usage"]["completion_tokens"] >= 0
        assert data["usage"]["total_tokens"] >= 0

    def test_completions_persists_tokens_to_session(self, client):
        """When session_id is provided, assistant message is persisted with token counts."""
        session = _make_session()
        persisted_messages: list[dict] = []

        async def _mock_persist(db, session_id, role, content, tokens_in=None, tokens_out=None, latency_ms=None):
            persisted_messages.append({
                "role": role,
                "content": content,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "latency_ms": latency_ms,
            })
            m = _make_message(role=role, content=content, tokens_in=tokens_in or 0, tokens_out=tokens_out or 0)
            return m

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = self._llm_response(30, 80)

        db = _mock_db_with_session(session)

        with (
            patch("app.routers.chat.httpx.AsyncClient") as mock_client_cls,
            patch("app.routers.chat._persist_message", side_effect=_mock_persist),
            patch("core.database.get_db", return_value=db),
        ):
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            app.dependency_overrides[get_db] = lambda: db

            resp = client.post(
                "/api/v1/chat/completions",
                json={
                    "messages": [{"role": "user", "content": "Analyze AAPL"}],
                    "stream": False,
                    "llm_config": LLM_CONFIG,
                    "session_id": SESSION_ID,
                },
            )

        app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        # Find the assistant message that was persisted
        assistant_msgs = [m for m in persisted_messages if m["role"] == "assistant"]
        assert len(assistant_msgs) == 1
        assert assistant_msgs[0]["tokens_in"] == 30
        assert assistant_msgs[0]["tokens_out"] == 80
        assert assistant_msgs[0]["latency_ms"] is not None
        assert assistant_msgs[0]["latency_ms"] >= 0

    def test_completions_llm_error_returns_502(self, client):
        """LLM provider error (non-200) returns 502."""
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = "Rate limit exceeded"

        with patch("app.routers.chat.httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            resp = client.post(
                "/api/v1/chat/completions",
                json={
                    "messages": [{"role": "user", "content": "test"}],
                    "stream": False,
                    "llm_config": LLM_CONFIG,
                },
            )

        assert resp.status_code == 502
        data = resp.json()
        assert data["detail"]["code"] == "LLM_PROVIDER_ERROR"


# ── Session usage aggregate endpoint ─────────────────────────────────────────

class TestSessionUsageEndpoint:
    """GET /chat/sessions/{id}/usage returns correct aggregate sums."""

    def _mock_db_usage(self, total_in: int, total_out: int, count: int):
        """Mock DB that returns aggregate usage row."""
        db = AsyncMock()

        # First call: ownership check (scalar_one_or_none)
        session = _make_session()
        ownership_result = MagicMock()
        ownership_result.scalar_one_or_none.return_value = session

        # Second call: aggregate query (one)
        agg_row = MagicMock()
        agg_row.total_tokens_in = total_in
        agg_row.total_tokens_out = total_out
        agg_row.message_count = count
        agg_result = MagicMock()
        agg_result.one.return_value = agg_row

        db.execute = AsyncMock(side_effect=[ownership_result, agg_result])
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        return db

    def test_usage_returns_correct_sums(self, client):
        """GET /usage returns sum of tokens_in, tokens_out, total, and count."""
        db = self._mock_db_usage(total_in=150, total_out=300, count=5)
        app.dependency_overrides[get_db] = lambda: db

        resp = client.get(f"/api/v1/chat/sessions/{SESSION_ID}/usage")

        app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == SESSION_ID
        assert data["total_tokens_in"] == 150
        assert data["total_tokens_out"] == 300
        assert data["total_tokens"] == 450
        assert data["message_count"] == 5

    def test_usage_total_equals_in_plus_out(self, client):
        """total_tokens == total_tokens_in + total_tokens_out (Property 8)."""
        db = self._mock_db_usage(total_in=200, total_out=400, count=8)
        app.dependency_overrides[get_db] = lambda: db

        resp = client.get(f"/api/v1/chat/sessions/{SESSION_ID}/usage")

        app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_tokens"] == data["total_tokens_in"] + data["total_tokens_out"]

    def test_usage_empty_session_returns_zeros(self, client):
        """Empty session (no messages) returns all zeros."""
        db = self._mock_db_usage(total_in=0, total_out=0, count=0)
        app.dependency_overrides[get_db] = lambda: db

        resp = client.get(f"/api/v1/chat/sessions/{SESSION_ID}/usage")

        app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_tokens_in"] == 0
        assert data["total_tokens_out"] == 0
        assert data["total_tokens"] == 0
        assert data["message_count"] == 0

    def test_usage_non_negative_tokens(self, client):
        """Token counts are always >= 0 (Property 8)."""
        db = self._mock_db_usage(total_in=0, total_out=0, count=0)
        app.dependency_overrides[get_db] = lambda: db

        resp = client.get(f"/api/v1/chat/sessions/{SESSION_ID}/usage")

        app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_tokens_in"] >= 0
        assert data["total_tokens_out"] >= 0
        assert data["total_tokens"] >= 0

    def test_usage_session_not_found_returns_404(self, client):
        """GET /usage for non-existent session returns 404."""
        db = AsyncMock()
        not_found_result = MagicMock()
        not_found_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=not_found_result)

        app.dependency_overrides[get_db] = lambda: db

        resp = client.get(f"/api/v1/chat/sessions/{uuid.uuid4()}/usage")

        app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 404

    def test_usage_other_user_session_returns_404(self, client):
        """GET /usage for another user's session returns 404 (not 403)."""
        # Session owned by OTHER_USER_ID, but JWT is TEST_USER_ID
        other_session = _make_session(user_id=OTHER_USER_ID)
        # The ownership query filters by user_id == jwt.sub, so it returns None
        db = AsyncMock()
        not_found_result = MagicMock()
        not_found_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=not_found_result)

        app.dependency_overrides[get_db] = lambda: db

        resp = client.get(f"/api/v1/chat/sessions/{SESSION_ID}/usage")

        app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 404


# ── Add message with token accounting ────────────────────────────────────────

class TestAddMessageTokenAccounting:
    """POST /sessions/{id}/messages stores token fields correctly."""

    def test_add_message_with_tokens(self, client):
        """Manually added message stores tokens_in, tokens_out, latency_ms."""
        session = _make_session()
        msg = _make_message(role="assistant", tokens_in=25, tokens_out=75, latency_ms=500)

        db = AsyncMock()
        # First execute: ownership check
        ownership_result = MagicMock()
        ownership_result.scalar_one_or_none.return_value = session
        db.execute = AsyncMock(return_value=ownership_result)
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock(side_effect=lambda m: setattr(m, "id", msg.id) or setattr(m, "created_at", msg.created_at))

        app.dependency_overrides[get_db] = lambda: db

        resp = client.post(
            f"/api/v1/chat/sessions/{SESSION_ID}/messages",
            json={
                "role": "assistant",
                "content": "Here is the analysis.",
                "tokens_in": 25,
                "tokens_out": 75,
                "latency_ms": 500,
            },
        )

        app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "assistant"
        assert data["tokens_in"] == 25
        assert data["tokens_out"] == 75
        assert data["latency_ms"] == 500

    def test_add_message_without_tokens(self, client):
        """Message without token fields stores None (nullable columns)."""
        session = _make_session()
        msg = _make_message(role="user", tokens_in=0, tokens_out=0, latency_ms=0)
        msg.tokens_in = None
        msg.tokens_out = None
        msg.latency_ms = None

        db = AsyncMock()
        ownership_result = MagicMock()
        ownership_result.scalar_one_or_none.return_value = session
        db.execute = AsyncMock(return_value=ownership_result)
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock(side_effect=lambda m: setattr(m, "id", msg.id) or setattr(m, "created_at", msg.created_at))

        app.dependency_overrides[get_db] = lambda: db

        resp = client.post(
            f"/api/v1/chat/sessions/{SESSION_ID}/messages",
            json={"role": "user", "content": "Hello"},
        )

        app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        data = resp.json()
        assert data["tokens_in"] is None
        assert data["tokens_out"] is None
        assert data["latency_ms"] is None


# ── Property-based test: token sum consistency ────────────────────────────────

class TestTokenSumConsistency:
    """
    Property 8 (design.md): tokens_in + tokens_out >= 0;
    cumulative sum per session matches sum of individual messages.

    **Validates: Requirements 2.3**
    """

    def test_usage_sum_matches_individual_messages(self, client):
        """
        Simulate multiple messages with known token counts.
        Verify that the usage endpoint returns the correct aggregate.
        """
        # Simulate 3 messages with known token counts
        messages_data = [
            {"tokens_in": 10, "tokens_out": 20},
            {"tokens_in": 30, "tokens_out": 60},
            {"tokens_in": 5, "tokens_out": 15},
        ]
        expected_in = sum(m["tokens_in"] for m in messages_data)   # 45
        expected_out = sum(m["tokens_out"] for m in messages_data)  # 95

        db = AsyncMock()
        session = _make_session()
        ownership_result = MagicMock()
        ownership_result.scalar_one_or_none.return_value = session

        agg_row = MagicMock()
        agg_row.total_tokens_in = expected_in
        agg_row.total_tokens_out = expected_out
        agg_row.message_count = len(messages_data)
        agg_result = MagicMock()
        agg_result.one.return_value = agg_row

        db.execute = AsyncMock(side_effect=[ownership_result, agg_result])

        app.dependency_overrides[get_db] = lambda: db

        resp = client.get(f"/api/v1/chat/sessions/{SESSION_ID}/usage")

        app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_tokens_in"] == expected_in
        assert data["total_tokens_out"] == expected_out
        assert data["total_tokens"] == expected_in + expected_out
        assert data["message_count"] == len(messages_data)

    def test_token_counts_always_non_negative(self):
        """
        Property 8: For any valid token accounting, tokens_in + tokens_out >= 0.

        Tests the SessionUsageOut model directly with various inputs.
        """
        from app.routers.chat import SessionUsageOut

        test_cases = [
            (0, 0, 0),
            (1, 1, 2),
            (100, 200, 300),
            (0, 500, 500),
            (1000, 0, 1000),
        ]
        for t_in, t_out, expected_total in test_cases:
            usage = SessionUsageOut(
                session_id=SESSION_ID,
                total_tokens_in=t_in,
                total_tokens_out=t_out,
                total_tokens=t_in + t_out,
                message_count=1,
            )
            assert usage.total_tokens_in >= 0
            assert usage.total_tokens_out >= 0
            assert usage.total_tokens >= 0
            assert usage.total_tokens == usage.total_tokens_in + usage.total_tokens_out
            assert usage.total_tokens == expected_total

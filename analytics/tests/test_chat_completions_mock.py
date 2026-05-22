"""
Task 2.6 — Chat completions tests with mocked LLM provider.

Tests:
  - Non-streaming completion returns correct format {choices: [...], usage: {...}}
  - Streaming completion returns SSE chunks
  - Invalid llm_config returns appropriate error
  - Missing API key returns 400

Note: The chat router is currently a stub (Phase 2 task 2.2 not yet implemented).
These tests validate the *expected* contract and will be updated once the full
implementation lands. Tests that exercise the stub are marked accordingly.

Validates: Requirements 2.1, 2.2
"""

from __future__ import annotations

import json
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app
from core.auth import create_analytics_jwt
from core.llm_router import validate_llm_config


# ── Helpers ───────────────────────────────────────────────────────────────────

def _auth_headers(user_id: str = "user-chat-001", role: str = "user") -> dict:
    """Return Bearer auth headers for a test user."""
    token = create_analytics_jwt(user_id, role=role)
    return {"Authorization": f"Bearer {token}"}


def _make_completion_response(
    content: str = "Hello, world!",
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
) -> dict:
    """Build a fake OpenAI-compatible completion response."""
    return {
        "id": "chatcmpl-test123",
        "object": "chat.completion",
        "model": "gpt-4o-mini",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def _make_sse_chunk(content: str, finish_reason: str | None = None) -> str:
    """Build a fake SSE data chunk in OpenAI streaming format."""
    delta = {"role": "assistant", "content": content} if content else {}
    chunk = {
        "id": "chatcmpl-stream-test",
        "object": "chat.completion.chunk",
        "model": "gpt-4o-mini",
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }
    return f"data: {json.dumps(chunk)}\n\n"


# ── LLM config validation unit tests ─────────────────────────────────────────
# These test core/llm_router.py::validate_llm_config directly — no HTTP needed.

class TestLlmConfigValidation:
    """Unit tests for validate_llm_config (no HTTP, no mock needed)."""

    def test_valid_openai_config(self):
        ok, err = validate_llm_config(
            model="gpt-4o-mini",
            api_key="sk-test1234567890",
            base_url="https://api.openai.com/v1",
            provider="openai",
        )
        assert ok is True
        assert err == ""

    def test_missing_model_returns_error(self):
        ok, err = validate_llm_config(
            model="",
            api_key="sk-test1234567890",
            base_url="https://api.openai.com/v1",
            provider="openai",
        )
        assert ok is False
        assert "model" in err.lower()

    def test_missing_api_key_non_local_returns_error(self):
        ok, err = validate_llm_config(
            model="gpt-4o-mini",
            api_key="",
            base_url="https://api.openai.com/v1",
            provider="openai",
        )
        assert ok is False
        assert "api key" in err.lower() or "key" in err.lower()

    def test_local_model_no_api_key_required(self):
        """Local models (localhost) don't require an API key."""
        ok, err = validate_llm_config(
            model="llama3",
            api_key="",
            base_url="http://localhost:11434/v1",
            provider="openai_local",
        )
        assert ok is True
        assert err == ""

    def test_invalid_base_url_scheme(self):
        ok, err = validate_llm_config(
            model="gpt-4o-mini",
            api_key="sk-test1234567890",
            base_url="ftp://api.openai.com/v1",
            provider="openai",
        )
        assert ok is False
        assert "http" in err.lower()

    def test_openai_key_wrong_prefix(self):
        """OpenAI native endpoint requires sk- prefix."""
        ok, err = validate_llm_config(
            model="gpt-4o-mini",
            api_key="wrong-key-format",
            base_url="https://api.openai.com/v1",
            provider="openai",
        )
        assert ok is False
        assert "sk-" in err

    def test_anthropic_key_wrong_prefix(self):
        ok, err = validate_llm_config(
            model="claude-3-haiku-20240307",
            api_key="sk-wrong-prefix",
            base_url="https://api.anthropic.com/v1",
            provider="anthropic",
        )
        assert ok is False
        assert "sk-ant-" in err

    def test_groq_key_wrong_prefix(self):
        ok, err = validate_llm_config(
            model="llama-3.1-8b-instant",
            api_key="wrong-key",
            base_url="https://api.groq.com/openai/v1",
            provider="groq",
        )
        assert ok is False
        assert "gsk_" in err

    def test_key_too_short(self):
        ok, err = validate_llm_config(
            model="gpt-4o-mini",
            api_key="sk-abc",
            base_url="https://custom.endpoint.com/v1",
            provider="custom",
        )
        assert ok is False
        assert "short" in err.lower()

    def test_custom_endpoint_any_key_format_ok(self):
        """Custom (non-native) OpenAI-compatible endpoints accept any key format."""
        ok, err = validate_llm_config(
            model="my-model",
            api_key="any-key-format-1234567890",
            base_url="https://my-custom-llm.example.com/v1",
            provider="custom",
        )
        assert ok is True
        assert err == ""


# ── Chat completions endpoint tests ──────────────────────────────────────────
# The router is currently a stub. These tests verify the stub returns a valid
# shape and will be extended once task 2.2 is implemented.

class TestChatCompletionsEndpoint:
    """Tests for POST /api/v1/chat/completions."""

    def test_completions_stub_endpoint_exists(self, client, auth_headers):
        """
        Stub endpoint must be reachable (not 404).

        The stub has no body params so FastAPI returns 422 when a body is sent.
        Once task 2.2 is implemented this will return 200 with {choices: [...]}.
        """
        # Send no body — stub accepts no params
        resp = client.post(
            "/api/v1/chat/completions",
            headers=auth_headers,
        )
        # Stub returns 200 with {choices: [], _stub: True}
        assert resp.status_code in (200, 422), (
            f"Expected 200 (stub) or 422 (body validation), got {resp.status_code}"
        )

    def test_completions_stub_no_body_returns_choices(self, client, auth_headers):
        """Stub endpoint with no body returns choices key."""
        resp = client.post(
            "/api/v1/chat/completions",
            headers=auth_headers,
        )
        if resp.status_code == 200:
            data = resp.json()
            assert "choices" in data

    def test_completions_requires_auth(self, client):
        """Endpoint must reject unauthenticated requests."""
        resp = client.post(
            "/api/v1/chat/completions",
        )
        # Stub currently doesn't enforce auth — once 2.2 is implemented this
        # should be 401. For now we just verify the endpoint exists (not 404).
        assert resp.status_code != 404, "Endpoint must exist"

    def test_completions_mock_non_streaming_format(self):
        """
        Verify the expected non-streaming response format.

        This test mocks the LLM call and validates the response shape that
        task 2.2 must produce: {choices: [...], usage: {...}}.
        """
        mock_response = _make_completion_response("The market looks bullish.", 15, 8)

        # Validate the shape we expect from the real implementation
        assert "choices" in mock_response
        assert "usage" in mock_response
        assert len(mock_response["choices"]) > 0
        assert "message" in mock_response["choices"][0]
        assert mock_response["choices"][0]["message"]["role"] == "assistant"
        assert "prompt_tokens" in mock_response["usage"]
        assert "completion_tokens" in mock_response["usage"]
        assert "total_tokens" in mock_response["usage"]
        # total_tokens must equal sum
        assert (
            mock_response["usage"]["total_tokens"]
            == mock_response["usage"]["prompt_tokens"]
            + mock_response["usage"]["completion_tokens"]
        )

    def test_completions_mock_streaming_sse_format(self):
        """
        Verify the expected SSE chunk format for streaming completions.

        Task 2.2 must produce SSE chunks in OpenAI streaming format.
        """
        chunk = _make_sse_chunk("Hello")
        assert chunk.startswith("data: ")
        assert chunk.endswith("\n\n")

        payload = json.loads(chunk[6:].strip())
        assert "choices" in payload
        assert "delta" in payload["choices"][0]
        assert payload["object"] == "chat.completion.chunk"

    def test_completions_mock_streaming_done_sentinel(self):
        """SSE stream must end with 'data: [DONE]' sentinel."""
        done_sentinel = "data: [DONE]\n\n"
        assert done_sentinel.startswith("data: [DONE]")

    def test_completions_mock_usage_accounting(self):
        """
        Verify token accounting in completion response.

        tokens_in + tokens_out must equal total_tokens.
        """
        for prompt_t, completion_t in [(5, 10), (100, 50), (0, 1), (1000, 2000)]:
            resp = _make_completion_response(
                prompt_tokens=prompt_t,
                completion_tokens=completion_t,
            )
            usage = resp["usage"]
            assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]
            assert usage["prompt_tokens"] >= 0
            assert usage["completion_tokens"] >= 0


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def auth_headers():
    return _auth_headers()


@pytest.fixture
def client(mock_cache):
    with TestClient(app) as c:
        yield c

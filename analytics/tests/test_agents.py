"""
Unit tests for Phase 1 — AI Agents API router.

All subprocess calls are mocked via unittest.mock so no real scripts are needed.
Run with: pytest tests/test_agents.py -v
"""

from __future__ import annotations

import json
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

# ── App bootstrap ─────────────────────────────────────────────────────────────

# Patch settings before importing app to avoid missing env vars
import os
os.environ.setdefault("SCRIPTS_DIR", "/tmp/scripts")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MASTER_API_KEY", "test-master-key")

from app.main import app  # noqa: E402  (must come after env setup)

# ── Fixtures ──────────────────────────────────────────────────────────────────

VALID_API_KEY = "test-api-key-valid"
HEADERS = {"X-API-Key": VALID_API_KEY}

LLM_CONFIG = {
    "model": "gpt-4o",
    "api_key": "sk-test",
    "base_url": "https://api.openai.com/v1",
    "temperature": 0.7,
    "max_tokens": 4096,
}


@pytest.fixture
def client():
    """Sync test client with auth dependency overridden."""
    from app.dependencies import get_api_key

    async def _mock_api_key(x_api_key=None):
        return VALID_API_KEY

    app.dependency_overrides[get_api_key] = _mock_api_key
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


def _mock_runner(return_value: dict):
    """Return a patched PythonRunner whose run() returns return_value."""
    mock = MagicMock()
    mock.run = AsyncMock(return_value=return_value)
    return mock


def _mock_cache_miss():
    """Patch cache.get to always miss, cache.set to succeed."""
    get_mock = AsyncMock(return_value=None)
    set_mock = AsyncMock(return_value=True)
    return get_mock, set_mock


# ── Discovery / Listing ───────────────────────────────────────────────────────

class TestDiscoverAgents:
    AGENT_RESPONSE = {
        "agents": [
            {
                "id": "stock-analyst",
                "name": "Stock Analyst",
                "description": "Analyzes stocks",
                "category": "analysis",
                "version": "1.0.0",
                "provider": "local",
                "capabilities": ["stock_analysis"],
                "config": {},
            }
        ],
        "categories": ["analysis"],
        "count": 1,
    }

    def test_discover_agents_cache_miss(self, client):
        """discover_agents fetches from subprocess on cache miss."""
        with (
            patch("app.routers.agents.cache.get", AsyncMock(return_value=None)),
            patch("app.routers.agents.cache.set", AsyncMock(return_value=True)),
            patch("app.routers.agents.get_runner", return_value=_mock_runner(self.AGENT_RESPONSE)),
        ):
            resp = client.get("/api/v1/agents/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["agents"][0]["id"] == "stock-analyst"

    def test_discover_agents_cache_hit(self, client):
        """discover_agents returns cached value without calling subprocess."""
        with (
            patch("app.routers.agents.cache.get", AsyncMock(return_value=self.AGENT_RESPONSE)),
            patch("app.routers.agents.get_runner") as mock_runner,
        ):
            resp = client.get("/api/v1/agents/")
        assert resp.status_code == 200
        mock_runner.assert_not_called()

    def test_list_agents_with_category(self, client):
        """list_agents passes category param to subprocess."""
        captured = {}

        async def _run(script, payload, **kwargs):
            captured["payload"] = payload
            return self.AGENT_RESPONSE

        mock = MagicMock()
        mock.run = _run
        with (
            patch("app.routers.agents.cache.get", AsyncMock(return_value=None)),
            patch("app.routers.agents.cache.set", AsyncMock(return_value=True)),
            patch("app.routers.agents.get_runner", return_value=mock),
        ):
            resp = client.get("/api/v1/agents/list?category=analysis")
        assert resp.status_code == 200
        assert captured["payload"]["params"]["category"] == "analysis"
        assert captured["payload"]["action"] == "list_agents"


# ── Agent Run ─────────────────────────────────────────────────────────────────

class TestAgentRun:
    RUN_RESPONSE = {
        "success": True,
        "response": "AAPL looks bullish based on technicals.",
    }

    def test_run_agent_success(self, client):
        """POST /run returns AgentRunResponse on success."""
        with patch("app.routers.agents.get_runner", return_value=_mock_runner(self.RUN_RESPONSE)):
            resp = client.post(
                "/api/v1/agents/run",
                json={
                    "query": "Analyze AAPL",
                    "llm_config": LLM_CONFIG,
                },
                headers=HEADERS,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "AAPL" in data["response"]
        assert data["execution_time_ms"] is not None

    def test_run_agent_payload_structure(self, client):
        """run action payload has correct structure sent to subprocess."""
        captured = {}

        async def _run(script, payload, **kwargs):
            captured["payload"] = payload
            return self.RUN_RESPONSE

        mock = MagicMock()
        mock.run = _run
        with patch("app.routers.agents.get_runner", return_value=mock):
            client.post(
                "/api/v1/agents/run",
                json={
                    "query": "Test query",
                    "agent_id": "stock-analyst",
                    "llm_config": LLM_CONFIG,
                },
                headers=HEADERS,
            )
        p = captured["payload"]
        assert p["action"] == "run"
        assert p["params"]["query"] == "Test query"
        assert p["params"]["agent_id"] == "stock-analyst"
        assert p["active_llm"]["provider"] == "openai"
        assert p["active_llm"]["model_id"] == "gpt-4o"
        # api_keys must be empty (LLM key goes via active_llm, not api_keys)
        assert p["api_keys"] == {}

    def test_run_agent_requires_auth(self, client):
        """POST /run without API key returns 401."""
        # Remove dependency override for this test
        app.dependency_overrides.clear()
        resp = client.post(
            "/api/v1/agents/run",
            json={"query": "test", "llm_config": LLM_CONFIG},
        )
        assert resp.status_code == 401
        # Restore override
        from app.dependencies import get_api_key
        async def _mock(x_api_key=None): return VALID_API_KEY
        app.dependency_overrides[get_api_key] = _mock

    def test_run_agent_subprocess_error(self, client):
        """PythonRunnerError is converted to FinceptAPIError."""
        from core.python_runner import PythonRunnerError

        mock = MagicMock()
        mock.run = AsyncMock(side_effect=PythonRunnerError("Script failed", stderr="traceback", exit_code=1))
        with patch("app.routers.agents.get_runner", return_value=mock):
            resp = client.post(
                "/api/v1/agents/run",
                json={"query": "test", "llm_config": LLM_CONFIG},
                headers=HEADERS,
            )
        # FinceptAPIError → 502 ScriptError
        assert resp.status_code in (502, 500)

    def test_run_agent_timeout_error(self, client):
        """Timeout PythonRunnerError maps to 504."""
        from core.python_runner import PythonRunnerError

        mock = MagicMock()
        mock.run = AsyncMock(
            side_effect=PythonRunnerError("Script 'x' timed out after 120s", exit_code=-1)
        )
        with patch("app.routers.agents.get_runner", return_value=mock):
            resp = client.post(
                "/api/v1/agents/run",
                json={"query": "test", "llm_config": LLM_CONFIG},
                headers=HEADERS,
            )
        assert resp.status_code in (504, 500)


# ── SSE Streaming ─────────────────────────────────────────────────────────────

class TestAgentStream:
    def test_stream_returns_event_stream_content_type(self, client):
        """POST /run/stream returns text/event-stream content type."""
        async def _fake_stream(script, payload):
            yield "THINKING: Analyzing AAPL..."
            yield "TOKEN: Based on technicals"
            yield "DONE: Analysis complete"

        mock = MagicMock()
        mock.stream = _fake_stream
        with patch("app.routers.agents.get_runner", return_value=mock):
            resp = client.post(
                "/api/v1/agents/run/stream",
                json={"query": "Analyze AAPL", "llm_config": LLM_CONFIG},
                headers=HEADERS,
            )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

    def test_stream_sse_format(self, client):
        """SSE lines are correctly formatted as data: {...}\\n\\n."""
        async def _fake_stream(script, payload):
            yield "THINKING: step 1"
            yield "TOKEN: hello"
            yield "DONE: finished"

        mock = MagicMock()
        mock.stream = _fake_stream
        with patch("app.routers.agents.get_runner", return_value=mock):
            resp = client.post(
                "/api/v1/agents/run/stream",
                json={"query": "test", "llm_config": LLM_CONFIG},
                headers=HEADERS,
            )
        body = resp.text
        events = [line for line in body.splitlines() if line.startswith("data:")]
        assert len(events) == 3

        first = json.loads(events[0][len("data: "):])
        assert first["type"] == "thinking"
        assert first["content"] == "step 1"

        second = json.loads(events[1][len("data: "):])
        assert second["type"] == "token"
        assert second["content"] == "hello"

        third = json.loads(events[2][len("data: "):])
        assert third["type"] == "done"
        assert third["content"] == "finished"

    def test_stream_unknown_prefix_defaults_to_token(self, client):
        """Lines without a known prefix are emitted as type=token."""
        async def _fake_stream(script, payload):
            yield "Some raw output line"

        mock = MagicMock()
        mock.stream = _fake_stream
        with patch("app.routers.agents.get_runner", return_value=mock):
            resp = client.post(
                "/api/v1/agents/run/stream",
                json={"query": "test", "llm_config": LLM_CONFIG},
                headers=HEADERS,
            )
        events = [l for l in resp.text.splitlines() if l.startswith("data:")]
        assert len(events) == 1
        parsed = json.loads(events[0][len("data: "):])
        assert parsed["type"] == "token"
        assert parsed["content"] == "Some raw output line"


# ── Team / Multi-Agent ────────────────────────────────────────────────────────

class TestTeamAndMulti:
    def test_run_team_action(self, client):
        """POST /team/run sends run_team action."""
        captured = {}

        async def _run(script, payload, **kwargs):
            captured["payload"] = payload
            return {"success": True, "response": "Team result"}

        mock = MagicMock()
        mock.run = _run
        with patch("app.routers.agents.get_runner", return_value=mock):
            resp = client.post(
                "/api/v1/agents/team/run",
                json={
                    "team_config": {
                        "name": "Alpha Team",
                        "mode": "coordinate",
                        "members": [{"agent_id": "stock-analyst"}],
                    },
                    "query": "Analyze portfolio",
                    "llm_config": LLM_CONFIG,
                },
                headers=HEADERS,
            )
        assert resp.status_code == 200
        assert captured["payload"]["action"] == "run_team"
        assert captured["payload"]["params"]["query"] == "Analyze portfolio"

    def test_multi_agent_run_action(self, client):
        """POST /multi/run sends execute_multi_query action."""
        captured = {}

        async def _run(script, payload, **kwargs):
            captured["payload"] = payload
            return {"success": True, "responses": [], "aggregated": "summary"}

        mock = MagicMock()
        mock.run = _run
        with patch("app.routers.agents.get_runner", return_value=mock):
            resp = client.post(
                "/api/v1/agents/multi/run",
                json={
                    "query": "What is the market outlook?",
                    "agent_ids": ["macro-analyst", "stock-analyst"],
                    "llm_config": LLM_CONFIG,
                },
                headers=HEADERS,
            )
        assert resp.status_code == 200
        assert captured["payload"]["action"] == "execute_multi_query"
        assert captured["payload"]["params"]["agent_ids"] == ["macro-analyst", "stock-analyst"]


# ── Execution Planner ─────────────────────────────────────────────────────────

class TestPlanner:
    def test_create_stock_plan(self, client):
        """POST /plan/stock sends create_stock_plan action with symbol."""
        captured = {}

        async def _run(script, payload, **kwargs):
            captured["payload"] = payload
            return {"success": True, "plan": {"steps": []}}

        mock = MagicMock()
        mock.run = _run
        with patch("app.routers.agents.get_runner", return_value=mock):
            resp = client.post(
                "/api/v1/agents/plan/stock",
                json={"symbol": "TSLA", "llm_config": LLM_CONFIG},
                headers=HEADERS,
            )
        assert resp.status_code == 200
        assert captured["payload"]["action"] == "create_stock_plan"
        assert captured["payload"]["params"]["symbol"] == "TSLA"

    def test_execute_plan_uses_plan_timeout(self, client):
        """POST /plan/execute uses AGENT_PLAN_TIMEOUT (300s)."""
        captured = {}

        async def _run(script, payload, timeout=None, **kwargs):
            captured["timeout"] = timeout
            return {"success": True, "results": ["done"]}

        mock = MagicMock()
        mock.run = _run
        with patch("app.routers.agents.get_runner", return_value=mock):
            resp = client.post(
                "/api/v1/agents/plan/execute",
                json={"plan": {"steps": []}, "llm_config": LLM_CONFIG},
                headers=HEADERS,
            )
        assert resp.status_code == 200
        from app.config import settings
        assert captured["timeout"] == settings.AGENT_PLAN_TIMEOUT


# ── Financial Analysis ────────────────────────────────────────────────────────

class TestFinancialAnalysis:
    @pytest.mark.parametrize("endpoint,action,body_extra", [
        ("/api/v1/agents/analyze/stock",   "stock_analysis",   {"symbol": "AAPL"}),
        ("/api/v1/agents/analyze/portfolio","portfolio_rebal",  {"portfolio_data": {"holdings": []}}),
        ("/api/v1/agents/analyze/risk",    "risk_assessment",  {"portfolio_data": {"holdings": []}}),
        ("/api/v1/agents/analyze/macro",   "macro_scan",       {}),
        ("/api/v1/agents/analyze/earnings","earnings_brief",   {"symbol": "MSFT"}),
        ("/api/v1/agents/analyze/sector-rotation","sector_rotation",{}),
    ])
    def test_analysis_action_mapping(self, client, endpoint, action, body_extra):
        """Each analysis endpoint sends the correct action to subprocess."""
        captured = {}

        async def _run(script, payload, **kwargs):
            captured["payload"] = payload
            return {"success": True, "response": "analysis result"}

        mock = MagicMock()
        mock.run = _run
        body = {"llm_config": LLM_CONFIG, **body_extra}
        with patch("app.routers.agents.get_runner", return_value=mock):
            resp = client.post(endpoint, json=body, headers=HEADERS)
        assert resp.status_code == 200, f"{endpoint} failed: {resp.text}"
        assert captured["payload"]["action"] == action


# ── Paper Trading ─────────────────────────────────────────────────────────────

class TestPaperTrading:
    def test_paper_trade_action(self, client):
        """POST /paper/trade sends paper_execute_trade action."""
        captured = {}

        async def _run(script, payload, **kwargs):
            captured["payload"] = payload
            return {"success": True, "trade_id": "trade-123"}

        mock = MagicMock()
        mock.run = _run
        with patch("app.routers.agents.get_runner", return_value=mock):
            resp = client.post(
                "/api/v1/agents/paper/trade",
                json={
                    "portfolio_id": "port-1",
                    "symbol": "AAPL",
                    "action": "buy",
                    "quantity": 10.0,
                    "price": 150.0,
                },
                headers=HEADERS,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["trade_id"] == "trade-123"
        assert captured["payload"]["action"] == "paper_execute_trade"

    def test_paper_trade_invalid_action(self, client):
        """action must be buy or sell — other values fail validation."""
        resp = client.post(
            "/api/v1/agents/paper/trade",
            json={
                "portfolio_id": "port-1",
                "symbol": "AAPL",
                "action": "short",  # invalid
                "quantity": 10.0,
                "price": 150.0,
            },
            headers=HEADERS,
        )
        assert resp.status_code == 422

    def test_get_portfolio(self, client):
        """GET /paper/portfolio/{id} sends paper_get_portfolio action."""
        captured = {}

        async def _run(script, payload, **kwargs):
            captured["payload"] = payload
            return {"success": True, "portfolio_value": 10000.0, "cash": 5000.0, "positions": []}

        mock = MagicMock()
        mock.run = _run
        with patch("app.routers.agents.get_runner", return_value=mock):
            resp = client.get("/api/v1/agents/paper/portfolio/port-1", headers=HEADERS)
        assert resp.status_code == 200
        assert captured["payload"]["action"] == "paper_get_portfolio"
        assert captured["payload"]["params"]["portfolio_id"] == "port-1"


# ── Session Management ────────────────────────────────────────────────────────

class TestSessions:
    def test_create_session_returns_session_id(self, client):
        """POST /sessions returns a new session_id."""
        with patch("app.routers.agents.get_runner", return_value=_mock_runner({"success": True})):
            resp = client.post(
                "/api/v1/agents/sessions",
                json={"agent_id": "stock-analyst"},
                headers=HEADERS,
            )
        assert resp.status_code == 201
        data = resp.json()
        assert "session_id" in data
        assert len(data["session_id"]) == 36  # UUID format

    def test_create_session_action(self, client):
        """POST /sessions sends save_session action with generated session_id."""
        captured = {}

        async def _run(script, payload, **kwargs):
            captured["payload"] = payload
            return {"success": True}

        mock = MagicMock()
        mock.run = _run
        with patch("app.routers.agents.get_runner", return_value=mock):
            resp = client.post(
                "/api/v1/agents/sessions",
                json={"agent_id": "stock-analyst", "user_id": "user-42"},
                headers=HEADERS,
            )
        assert resp.status_code == 201
        assert captured["payload"]["action"] == "save_session"
        assert captured["payload"]["params"]["agent_id"] == "stock-analyst"
        assert captured["payload"]["params"]["user_id"] == "user-42"

    def test_get_session(self, client):
        """GET /sessions/{id} sends get_session action."""
        captured = {}

        async def _run(script, payload, **kwargs):
            captured["payload"] = payload
            return {"agent_id": "stock-analyst", "messages": [], "status": "active"}

        mock = MagicMock()
        mock.run = _run
        with patch("app.routers.agents.get_runner", return_value=mock):
            resp = client.get("/api/v1/agents/sessions/sess-abc", headers=HEADERS)
        assert resp.status_code == 200
        assert captured["payload"]["action"] == "get_session"
        assert captured["payload"]["params"]["session_id"] == "sess-abc"

    def test_add_message(self, client):
        """POST /sessions/{id}/messages sends add_message action."""
        captured = {}

        async def _run(script, payload, **kwargs):
            captured["payload"] = payload
            return {"messages": [{"role": "user", "content": "hello"}], "status": "active"}

        mock = MagicMock()
        mock.run = _run
        with patch("app.routers.agents.get_runner", return_value=mock):
            resp = client.post(
                "/api/v1/agents/sessions/sess-abc/messages",
                json={"role": "user", "content": "hello"},
                headers=HEADERS,
            )
        assert resp.status_code == 200
        assert captured["payload"]["action"] == "add_message"
        assert captured["payload"]["params"]["role"] == "user"
        assert captured["payload"]["params"]["content"] == "hello"

    def test_add_message_invalid_role(self, client):
        """role must be user|assistant|system."""
        resp = client.post(
            "/api/v1/agents/sessions/sess-abc/messages",
            json={"role": "bot", "content": "hello"},
            headers=HEADERS,
        )
        assert resp.status_code == 422

    def test_delete_session(self, client):
        """DELETE /sessions/{id} returns 204."""
        with patch("app.routers.agents.get_runner", return_value=_mock_runner({"success": True})):
            resp = client.delete("/api/v1/agents/sessions/sess-abc", headers=HEADERS)
        assert resp.status_code == 204


# ── Payload builder ───────────────────────────────────────────────────────────

class TestBuildPayload:
    def test_build_payload_structure(self):
        """_build_payload produces correct structure with OpenAI-compatible LLMConfig."""
        from app.routers.agents import _build_payload

        class FakeLLM:
            model = "gpt-4o"
            provider = "openai"
            api_key = "sk-test-123"
            base_url = "https://api.openai.com/v1"
            temperature = 0.5
            max_tokens = 2048

        payload = _build_payload("run", {"query": "test"}, {"opt": 1}, FakeLLM())
        assert payload["action"] == "run"
        assert payload["api_keys"] == {}
        assert payload["params"] == {"query": "test"}
        assert payload["config"] == {"opt": 1}
        assert payload["active_llm"]["provider"] == "openai"
        assert payload["active_llm"]["model_id"] == "gpt-4o"
        assert payload["active_llm"]["api_key"] == "sk-test-123"
        assert payload["active_llm"]["base_url"] == "https://api.openai.com/v1"
        assert payload["active_llm"]["temperature"] == 0.5
        assert payload["active_llm"]["max_tokens"] == 2048

    def test_build_payload_groq(self):
        """_build_payload works with Groq OpenAI-compatible endpoint."""
        from app.routers.agents import _build_payload

        class GroqLLM:
            model = "llama-3.1-70b-versatile"
            provider = "groq"
            api_key = "gsk_test"
            base_url = "https://api.groq.com/openai/v1"
            temperature = 0.3
            max_tokens = 8192

        payload = _build_payload("run", {"query": "test"}, {}, GroqLLM())
        assert payload["active_llm"]["provider"] == "groq"
        assert payload["active_llm"]["model_id"] == "llama-3.1-70b-versatile"
        assert payload["active_llm"]["base_url"] == "https://api.groq.com/openai/v1"

    def test_build_payload_ollama(self):
        """_build_payload works with local Ollama endpoint."""
        from app.routers.agents import _build_payload

        class OllamaLLM:
            model = "llama3.2"
            provider = "openai"   # Ollama uses openai-compat
            api_key = "ollama"
            base_url = "http://localhost:11434/v1"
            temperature = 0.7
            max_tokens = 4096

        payload = _build_payload("run", {"query": "test"}, {}, OllamaLLM())
        assert payload["active_llm"]["model_id"] == "llama3.2"
        assert "localhost" in payload["active_llm"]["base_url"]

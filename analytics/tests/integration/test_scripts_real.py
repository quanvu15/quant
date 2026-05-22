"""
Integration tests — chạy với scripts thực (không mock).

Yêu cầu:
- SCRIPTS_DIR và VENV_NUMPY2_PYTHON đã cấu hình trong .env
- Redis đang chạy
- Một số tests cần API keys (FRED_API_KEY, LLM key)

Chạy: pytest tests/integration/ -v -s
Skip nếu môi trường chưa sẵn sàng: pytest tests/integration/ -v -s --ignore-glob="*real*"
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

# ── Skip nếu môi trường chưa sẵn sàng ───────────────────────────────────────

def _env_ready() -> bool:
    """Check nếu SCRIPTS_DIR và VENV_NUMPY2_PYTHON đã cấu hình."""
    from app.config import settings
    scripts_ok = bool(settings.SCRIPTS_DIR) and Path(settings.SCRIPTS_DIR).exists()
    venv_ok = bool(settings.VENV_NUMPY2_PYTHON) and Path(settings.VENV_NUMPY2_PYTHON).exists()
    return scripts_ok and venv_ok


def _check_redis() -> bool:
    try:
        import redis
        r = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        r.ping()
        return True
    except Exception:
        return False


skip_if_not_ready = pytest.mark.skipif(
    not _env_ready(),
    reason="SCRIPTS_DIR hoặc VENV_NUMPY2_PYTHON chưa cấu hình. Xem tests/integration/README.md"
)

skip_if_no_redis = pytest.mark.skipif(
    os.getenv("REDIS_URL", "") == "" and not _check_redis(),
    reason="Redis chưa chạy"
)


# ── Test helpers ──────────────────────────────────────────────────────────────

async def _run_script(script_key: str, payload: dict) -> dict:
    """Run a real script via PythonRunner."""
    from core.python_runner import get_runner
    from core.script_catalog import catalog
    runner = get_runner()
    script = catalog.path(script_key)
    return await runner.run(script, payload, timeout=30)


# ── Phase 2: Market Data ──────────────────────────────────────────────────────

@skip_if_not_ready
@pytest.mark.asyncio
async def test_yfinance_quote_real():
    """yfinance_data.py — get_quote action."""
    result = await _run_script("market.yfinance", {
        "action": "get_quote",
        "params": {"symbol": "AAPL", "source": "yfinance"}
    })
    assert isinstance(result, dict), f"Expected dict, got: {type(result)}"
    # Script có thể trả về success=True hoặc data trực tiếp
    print(f"\n✅ yfinance quote result keys: {list(result.keys())}")


@skip_if_not_ready
@pytest.mark.asyncio
async def test_yfinance_history_real():
    """yfinance_data.py — get_history action."""
    result = await _run_script("market.yfinance", {
        "action": "get_history",
        "params": {"symbol": "AAPL", "start": "2024-01-01", "interval": "1d"}
    })
    assert isinstance(result, dict)
    print(f"\n✅ yfinance history result keys: {list(result.keys())}")


# ── Phase 3: QuantLib ─────────────────────────────────────────────────────────

@skip_if_not_ready
@pytest.mark.asyncio
async def test_derivatives_bsm_real():
    """derivatives_pricing.py — BSM option pricing."""
    result = await _run_script("quant.derivatives", {
        "action": "option_price",
        "params": {
            "S": 150.0, "K": 155.0, "T": 0.25,
            "r": 0.05, "sigma": 0.2,
            "option_type": "call", "model": "bsm"
        }
    })
    assert isinstance(result, dict)
    print(f"\n✅ BSM result: {result}")


@skip_if_not_ready
@pytest.mark.asyncio
async def test_derivatives_greeks_real():
    """derivatives_pricing.py — compute_greeks action."""
    result = await _run_script("quant.derivatives", {
        "action": "compute_greeks",
        "params": {
            "S": 150.0, "K": 155.0, "T": 0.25,
            "r": 0.05, "sigma": 0.2,
            "option_type": "call"
        }
    })
    assert isinstance(result, dict)
    print(f"\n✅ Greeks result: {result}")


# ── Phase 4: Economics ────────────────────────────────────────────────────────

@skip_if_not_ready
@pytest.mark.skipif(not os.getenv("FRED_API_KEY"), reason="FRED_API_KEY not set")
@pytest.mark.asyncio
async def test_fred_series_real():
    """fred_data.py — get_series action."""
    result = await _run_script("intel.fred", {
        "action": "get_series",
        "params": {"series_id": "CPIAUCSL", "start": "2024-01-01"}
    })
    assert isinstance(result, dict)
    print(f"\n✅ FRED result keys: {list(result.keys())}")


# ── Phase 1: Agent Discovery ──────────────────────────────────────────────────

@skip_if_not_ready
@pytest.mark.asyncio
async def test_agent_discover_real():
    """finagent_core/main.py — discover_agents action (no LLM needed)."""
    result = await _run_script("agents.main", {
        "action": "discover_agents",
        "api_keys": {},
        "params": {},
        "config": {},
        "active_llm": {}
    })
    assert isinstance(result, dict)
    # Có thể trả về agents list hoặc empty nếu không có configs
    print(f"\n✅ discover_agents result: count={result.get('count', 0)}")


@skip_if_not_ready
@pytest.mark.asyncio
async def test_agent_list_real():
    """finagent_core/main.py — list_agents action."""
    result = await _run_script("agents.main", {
        "action": "list_agents",
        "api_keys": {},
        "params": {"category": ""},
        "config": {},
        "active_llm": {}
    })
    assert isinstance(result, dict)
    print(f"\n✅ list_agents result: count={result.get('count', 0)}")


@skip_if_not_ready
@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY") and not os.getenv("LLM_API_KEY"),
    reason="LLM API key not set (OPENAI_API_KEY or LLM_API_KEY)"
)
@pytest.mark.asyncio
async def test_agent_run_real():
    """finagent_core/main.py — run action với LLM thực."""
    llm_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY", "")
    result = await _run_script("agents.main", {
        "action": "run",
        "api_keys": {},
        "params": {"query": "What is 2+2? Answer in one word."},
        "config": {},
        "active_llm": {
            "provider": "openai",
            "model_id": "gpt-4o-mini",
            "api_key": llm_key,
            "base_url": "https://api.openai.com/v1",
            "temperature": 0.0,
            "max_tokens": 10
        }
    })
    assert isinstance(result, dict)
    assert result.get("success") is True, f"Agent run failed: {result.get('error')}"
    print(f"\n✅ agent run response: {result.get('response', '')[:100]}")

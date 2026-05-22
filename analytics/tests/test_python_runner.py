"""
Phase 0 — Test Gate: Python subprocess bridge.
"""

from __future__ import annotations

import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.python_runner import PythonRunner, PythonRunnerError, _extract_json


# ── Unit tests for _extract_json ─────────────────────────────────────────────

def test_extract_json_simple_object():
    output = '{"success": true, "data": {"value": 42}}'
    assert json.loads(_extract_json(output)) == {"success": True, "data": {"value": 42}}


def test_extract_json_with_preamble():
    output = "Loading...\nDone.\n{\"success\": true}"
    result = _extract_json(output)
    assert json.loads(result) == {"success": True}


def test_extract_json_empty():
    result = _extract_json("")
    assert result == "{}"


def test_extract_json_array():
    output = "[1, 2, 3]"
    result = _extract_json(output)
    assert json.loads(result) == [1, 2, 3]


# ── Unit tests for PythonRunner ───────────────────────────────────────────────

@pytest.fixture
def runner():
    return PythonRunner(timeout=10)


@pytest.mark.asyncio
async def test_runner_run_success(runner):
    """run() should parse JSON from stdout."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(
        return_value=(
            b'{"success": true, "data": {"value": 42}}',
            b"",
        )
    )

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        with patch("asyncio.wait_for", new_callable=AsyncMock) as mock_wait:
            mock_wait.return_value = (
                b'{"success": true, "data": {"value": 42}}',
                b"",
            )
            mock_proc.communicate = AsyncMock(
                return_value=(b'{"success": true, "data": {"value": 42}}', b"")
            )
            result = await runner.run("test_script.py", {"action": "test"})

    assert result["success"] is True


@pytest.mark.asyncio
async def test_runner_run_timeout(runner):
    """run() should raise PythonRunnerError on timeout."""
    import asyncio

    mock_proc = MagicMock()
    mock_proc.kill = MagicMock()

    async def slow_communicate(data):
        await asyncio.sleep(100)

    mock_proc.communicate = slow_communicate

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            with pytest.raises(PythonRunnerError) as exc_info:
                await runner.run("slow_script.py", {})

    assert "timed out" in str(exc_info.value)


@pytest.mark.asyncio
async def test_runner_run_nonzero_exit(runner):
    """run() should raise PythonRunnerError on non-zero exit code."""
    mock_proc = MagicMock()
    mock_proc.returncode = 1

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        with patch("asyncio.wait_for", new_callable=AsyncMock) as mock_wait:
            mock_wait.return_value = (b"", b"Error: something went wrong")
            with pytest.raises(PythonRunnerError) as exc_info:
                await runner.run("failing_script.py", {})

    assert exc_info.value.exit_code == 1


def test_runner_resolve_python_fallback(runner):
    """_resolve_python should fall back to sys.executable."""
    python = runner._resolve_python("venv-numpy2")
    assert python == sys.executable  # No venv configured in test env


def test_runner_build_env_sets_pythonpath(runner):
    """_build_env should set PYTHONPATH to include scripts dir."""
    env = runner._build_env({})
    assert "PYTHONPATH" in env
    assert "PYTHONIOENCODING" in env
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert env["PYTHONUNBUFFERED"] == "1"


def test_runner_build_env_injects_api_keys(runner):
    """_build_env should inject per-request API keys."""
    env = runner._build_env({"OPENAI_API_KEY": "sk-test-123"})
    assert env["OPENAI_API_KEY"] == "sk-test-123"

"""
Async Python subprocess bridge.

Mirrors the logic of fincept-qt/src/python/PythonRunner.cpp but in async Python.
Supports:
  - run()    — one-shot JSON in/out
  - stream() — async generator yielding stdout lines (for SSE/WebSocket)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, Optional

import structlog

from app.config import settings

logger = structlog.get_logger(__name__)


class PythonRunnerError(Exception):
    """Raised when a subprocess exits with non-zero code or times out."""

    def __init__(self, message: str, stderr: str = "", exit_code: int = -1):
        super().__init__(message)
        self.stderr = stderr
        self.exit_code = exit_code


class PythonRunner:
    """
    Async subprocess bridge for Fincept Python scripts.

    Usage::

        runner = PythonRunner()

        # One-shot
        result = await runner.run("yfinance_data.py", {"action": "quote", "symbol": "AAPL"})

        # Streaming
        async for line in runner.stream("agents/finagent_core/main.py", payload, api_keys):
            print(line)
    """

    def __init__(
        self,
        venv: str = "",
        timeout: int = 0,
        max_concurrent: int = 0,
    ):
        self._venv = venv or settings.DEFAULT_VENV
        self._timeout = timeout or settings.DEFAULT_TIMEOUT
        self._max_concurrent = max_concurrent or settings.MAX_CONCURRENT_PROCESSES
        self._semaphore: Optional[asyncio.Semaphore] = None  # lazy — tạo trong event loop hiện tại

    def _get_semaphore(self) -> asyncio.Semaphore:
        """Lazy semaphore — tránh lỗi 'attached to different event loop'."""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max_concurrent)
        return self._semaphore

    # ── Public API ────────────────────────────────────────────────────────────

    async def run(
        self,
        script: str,
        payload: Dict[str, Any],
        api_keys: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        venv: Optional[str] = None,
    ) -> Dict[str, Any]:
        effective_timeout = timeout or self._timeout
        effective_venv = venv or self._venv

        async with self._get_semaphore():
            python_bin = self._resolve_python(effective_venv)
            script_path = self._resolve_script(script)
            env = self._build_env(api_keys or {})
            stdin_data = json.dumps(payload).encode("utf-8")

            logger.debug(
                "python_runner.run",
                script=script,
                timeout=effective_timeout,
                venv=effective_venv,
            )

            # Windows: SelectorEventLoop không hỗ trợ subprocess.
            # Dùng ThreadPoolExecutor để chạy subprocess trong thread riêng.
            if sys.platform == "win32":
                return await self._run_via_thread(
                    python_bin, script_path, stdin_data, env,
                    effective_timeout, script
                )

            try:
                proc = await asyncio.create_subprocess_exec(
                    python_bin, str(script_path), "--stdin",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(stdin_data),
                    timeout=effective_timeout,
                )
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except Exception:
                    pass
                raise PythonRunnerError(
                    f"Script '{script}' timed out after {effective_timeout}s",
                    exit_code=-1,
                )
            except Exception as exc:
                logger.error(
                    "python_runner.spawn_failed",
                    script=script,
                    python_bin=python_bin,
                    script_path=str(script_path),
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                raise PythonRunnerError(
                    f"Failed to spawn subprocess: {type(exc).__name__}: {exc}",
                    stderr=str(exc),
                ) from exc

            return self._parse_output(stdout, stderr, script)

    async def _run_via_thread(
        self,
        python_bin: str,
        script_path: Path,
        stdin_data: bytes,
        env: Dict[str, str],
        timeout: int,
        script: str,
    ) -> Dict[str, Any]:
        """
        Windows fallback: chạy subprocess trong ThreadPoolExecutor.
        SelectorEventLoop không hỗ trợ create_subprocess_exec trên Windows.
        """
        import concurrent.futures
        import subprocess

        def _run_sync():
            try:
                result = subprocess.run(
                    [python_bin, str(script_path), "--stdin"],
                    input=stdin_data,
                    capture_output=True,
                    timeout=timeout,
                    env=env,
                )
                return result.returncode, result.stdout, result.stderr
            except subprocess.TimeoutExpired:
                return -1, b"", b"timeout"
            except Exception as exc:
                return -1, b"", str(exc).encode()

        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            try:
                returncode, stdout, stderr = await asyncio.wait_for(
                    loop.run_in_executor(pool, _run_sync),
                    timeout=timeout + 5,
                )
            except asyncio.TimeoutError:
                raise PythonRunnerError(
                    f"Script '{script}' timed out after {timeout}s",
                    exit_code=-1,
                )

        if returncode == -1 and stderr == b"timeout":
            raise PythonRunnerError(
                f"Script '{script}' timed out after {timeout}s",
                exit_code=-1,
            )

        return self._parse_output(stdout, stderr, script)

    def _parse_output(self, stdout: bytes, stderr: bytes, script: str) -> Dict[str, Any]:
        """Parse stdout/stderr from subprocess into dict."""
        stdout_str = stdout.decode("utf-8", errors="replace").strip()
        stderr_str = stderr.decode("utf-8", errors="replace").strip()

        # Script có output lỗi nhưng không có stdout
        if not stdout_str and stderr_str:
            raise PythonRunnerError(
                f"Script '{script}' produced no output",
                stderr=stderr_str,
                exit_code=1,
            )

        if not stdout_str:
            raise PythonRunnerError(
                f"Script '{script}' produced no output",
                stderr=stderr_str,
                exit_code=1,
            )

        json_str = _extract_json(stdout_str)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as exc:
            raise PythonRunnerError(
                f"Script '{script}' produced invalid JSON: {exc}. Output: {stdout_str[:200]}",
                stderr=stderr_str,
            ) from exc

    async def stream(
        self,
        script: str,
        payload: Dict[str, Any],
        api_keys: Optional[Dict[str, str]] = None,
        venv: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Run a script in streaming mode, yielding stdout lines as they arrive.
        Windows: dùng thread-based approach vì SelectorEventLoop không hỗ trợ subprocess.
        """
        effective_venv = venv or self._venv
        python_bin = self._resolve_python(effective_venv)
        script_path = self._resolve_script(script)
        env = self._build_env(api_keys or {})
        stdin_data = json.dumps(payload).encode("utf-8")

        logger.debug("python_runner.stream", script=script, venv=effective_venv)

        if sys.platform == "win32":
            # Windows: chạy subprocess sync trong thread, collect all output
            import concurrent.futures
            import subprocess

            def _run_sync():
                try:
                    result = subprocess.run(
                        [python_bin, str(script_path), "--stream", "--stdin"],
                        input=stdin_data,
                        capture_output=True,
                        timeout=300,
                        env=env,
                    )
                    return result.stdout
                except Exception as exc:
                    return f"ERROR: {exc}".encode()

            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                stdout_bytes = await loop.run_in_executor(pool, _run_sync)

            for line in stdout_bytes.decode("utf-8", errors="replace").splitlines():
                line = line.strip()
                if line:
                    yield line
            return

        # Non-Windows: true async streaming
        proc = await asyncio.create_subprocess_exec(
            python_bin, str(script_path), "--stream", "--stdin",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        proc.stdin.write(stdin_data)
        await proc.stdin.drain()
        proc.stdin.close()

        try:
            async for raw_line in proc.stdout:
                line = raw_line.decode("utf-8", errors="replace").rstrip("\n\r")
                if line:
                    yield line
        finally:
            if proc.returncode is None:
                try:
                    proc.kill()
                except Exception:
                    pass
            await proc.wait()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _resolve_python(self, venv: str) -> str:
        """Return path to python executable for the given venv name."""
        if venv == "venv-numpy1" and settings.VENV_NUMPY1_PYTHON:
            return settings.VENV_NUMPY1_PYTHON
        if venv == "venv-numpy2" and settings.VENV_NUMPY2_PYTHON:
            return settings.VENV_NUMPY2_PYTHON
        # Fallback: use current interpreter
        return sys.executable

    def _resolve_script(self, script: str) -> Path:
        """Resolve script path relative to SCRIPTS_DIR."""
        p = Path(script)
        if p.is_absolute():
            return p
        scripts_dir = Path(settings.SCRIPTS_DIR)
        return scripts_dir / script

    def _build_env(self, api_keys: Dict[str, str]) -> Dict[str, str]:
        """Build subprocess environment, injecting API keys."""
        env = os.environ.copy()

        # Standard Python env vars (mirrors C++ build_python_env)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONUNBUFFERED"] = "1"

        # PYTHONPATH: include scripts dir so sub-packages can import each other
        scripts_dir = settings.SCRIPTS_DIR
        existing_path = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{scripts_dir}{os.pathsep}{existing_path}" if existing_path else scripts_dir

        # Inject configured external API keys
        # OPENAI_API_KEY: dùng key riêng nếu có, fallback về LLM_API_KEY
        # (LLM_API_KEY là key của bất kỳ OpenAI-compatible provider nào)
        openai_key = settings.OPENAI_API_KEY or settings.LLM_API_KEY
        _inject_if_set(env, "OPENAI_API_KEY", openai_key)
        _inject_if_set(env, "ANTHROPIC_API_KEY", settings.ANTHROPIC_API_KEY)
        _inject_if_set(env, "GOOGLE_API_KEY", settings.GOOGLE_API_KEY)
        _inject_if_set(env, "POLYGON_API_KEY", settings.POLYGON_API_KEY)
        _inject_if_set(env, "FINNHUB_API_KEY", settings.FINNHUB_API_KEY)
        _inject_if_set(env, "ALPHA_VANTAGE_API_KEY", settings.ALPHA_VANTAGE_API_KEY)
        _inject_if_set(env, "FRED_API_KEY", settings.FRED_API_KEY)
        _inject_if_set(env, "MARINETRAFFIC_API_KEY", settings.MARINETRAFFIC_API_KEY)
        _inject_if_set(env, "ACLED_API_KEY", settings.ACLED_API_KEY)

        # Per-request API keys override (from request body — NOT logged)
        for k, v in api_keys.items():
            if v:
                env[k] = v

        return env


# ── Module-level singleton ────────────────────────────────────────────────────

_runner: Optional[PythonRunner] = None


def get_runner(venv: str = "", timeout: int = 0) -> PythonRunner:
    """
    Return a PythonRunner instance.
    - Không có args: trả singleton (semaphore shared, giới hạn concurrency đúng)
    - Có args: tạo instance mới (cho custom timeout/venv)
    """
    global _runner
    if venv or timeout:
        # Custom params — tạo mới, không share semaphore
        return PythonRunner(venv=venv, timeout=timeout)
    if _runner is None:
        _runner = PythonRunner()
    return _runner


# ── Utilities ─────────────────────────────────────────────────────────────────

def _extract_json(output: str) -> str:
    """
    Extract the last JSON object/array from script stdout.
    Mirrors the C++ extract_json() logic in PythonRunner.cpp.
    """
    if not output:
        return "{}"

    # Try the whole output first
    stripped = output.strip()
    if stripped.startswith(("{", "[")):
        return stripped

    # Walk backwards line by line to find last JSON line
    lines = output.splitlines()
    for line in reversed(lines):
        line = line.strip()
        if line.startswith(("{", "[")):
            return line

    return output.strip()


def _inject_if_set(env: Dict[str, str], key: str, value: str) -> None:
    if value:
        env[key] = value

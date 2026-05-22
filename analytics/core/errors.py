"""
Standardized error handling for Fincept API.

Error codes mirror the PLAN.md specification.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from fastapi.responses import JSONResponse


# ── Error codes ───────────────────────────────────────────────────────────────

class ErrorCode:
    AUTH_REQUIRED = "AUTH_REQUIRED"
    RATE_LIMITED = "RATE_LIMITED"
    SCRIPT_TIMEOUT = "SCRIPT_TIMEOUT"
    SCRIPT_ERROR = "SCRIPT_ERROR"
    INVALID_PARAMS = "INVALID_PARAMS"
    EXTERNAL_API_ERROR = "EXTERNAL_API_ERROR"
    MISSING_API_KEY = "MISSING_API_KEY"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    JOB_FAILED = "JOB_FAILED"
    NOT_FOUND = "NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# ── Exception class ───────────────────────────────────────────────────────────

class FinceptAPIError(Exception):
    """Base exception for all Fincept API errors."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        self.request_id = str(uuid.uuid4())


class ScriptTimeoutError(FinceptAPIError):
    def __init__(self, script: str, timeout: int):
        super().__init__(
            code=ErrorCode.SCRIPT_TIMEOUT,
            message=f"Script '{script}' timed out after {timeout}s.",
            status_code=504,
            details={"script": script, "timeout_seconds": timeout},
        )


class ScriptError(FinceptAPIError):
    def __init__(self, script: str, stderr: str = "", exit_code: int = -1):
        super().__init__(
            code=ErrorCode.SCRIPT_ERROR,
            message=f"Script '{script}' returned an error.",
            status_code=502,
            details={"script": script, "exit_code": exit_code, "stderr": stderr[:500]},
        )


class InvalidParamsError(FinceptAPIError):
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(
            code=ErrorCode.INVALID_PARAMS,
            message=message,
            status_code=422,
            details=details or {},
        )


class MissingApiKeyError(FinceptAPIError):
    def __init__(self, service: str):
        super().__init__(
            code=ErrorCode.MISSING_API_KEY,
            message=f"API key for '{service}' is not configured.",
            status_code=400,
            details={"service": service},
        )


class ExternalApiError(FinceptAPIError):
    def __init__(self, service: str, message: str):
        super().__init__(
            code=ErrorCode.EXTERNAL_API_ERROR,
            message=f"External API error from '{service}': {message}",
            status_code=502,
            details={"service": service},
        )


class JobNotFoundError(FinceptAPIError):
    def __init__(self, job_id: str):
        super().__init__(
            code=ErrorCode.JOB_NOT_FOUND,
            message=f"Job '{job_id}' not found.",
            status_code=404,
            details={"job_id": job_id},
        )


# ── Error handler ─────────────────────────────────────────────────────────────

def error_handler(exc: FinceptAPIError) -> JSONResponse:
    """Convert a FinceptAPIError to a standardized JSON response."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
                "request_id": exc.request_id,
            }
        },
    )


def script_error_to_api_error(exc: Exception, script: str) -> FinceptAPIError:
    """Convert a PythonRunnerError to the appropriate FinceptAPIError."""
    from core.python_runner import PythonRunnerError

    if isinstance(exc, PythonRunnerError):
        msg = str(exc)
        if "timed out" in msg:
            return ScriptTimeoutError(script=script, timeout=60)
        # Expose the actual error message (spawn failures, etc.)
        detail_msg = exc.stderr or msg
        return ScriptError(script=script, stderr=detail_msg, exit_code=exc.exit_code)
    return FinceptAPIError(
        code=ErrorCode.INTERNAL_ERROR,
        message=str(exc),
        status_code=500,
    )

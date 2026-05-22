"""
Standard response models — wraps fincept_output_standard.py format into Pydantic.
"""

from __future__ import annotations

from typing import Any, Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)
    request_id: Optional[str] = None


class ScriptMetadata(BaseModel):
    script: str
    timestamp: str
    output_type: str
    version: str = "1.0.0"
    execution_time_ms: float


class StandardResponse(BaseModel, Generic[T]):
    """
    Mirrors fincept_output_standard.py format.

    {
        "success": true,
        "data": {...},
        "metadata": {...},
        "error": null
    }
    """

    success: bool
    data: Optional[T] = None
    metadata: Optional[ScriptMetadata] = None
    error: Optional[Dict[str, Any]] = None

    @classmethod
    def ok(cls, data: Any, metadata: Optional[Dict] = None) -> "StandardResponse":
        return cls(success=True, data=data, metadata=metadata)

    @classmethod
    def fail(cls, code: str, message: str, details: Optional[Dict] = None) -> "StandardResponse":
        return cls(
            success=False,
            data=None,
            error={"code": code, "message": message, "details": details or {}},
        )


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated list response."""

    items: List[T]
    total: int
    page: int = 1
    page_size: int = 50
    has_more: bool = False


class HealthResponse(BaseModel):
    status: str
    version: str
    env: str
    redis: str

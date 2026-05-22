"""
Audit log helpers for the Analytics microservice.

Provides:
  record_audit()       — fire-and-forget async write to analytics.audit_log
  cleanup_audit_log()  — delete entries older than AUDIT_LOG_RETENTION_DAYS
                         (called by a scheduled job or startup hook)

Requirement 0.8:
  - Every POST/DELETE request writes an entry with user_id, action,
    resource, request_id, ip, ts.
  - Retention: 90 days (configurable via AUDIT_LOG_RETENTION_DAYS).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import structlog
from sqlalchemy import delete, text

from app.config import settings
from core.database import AsyncSessionLocal
from models.db.audit import AuditLog

logger = structlog.get_logger(__name__)


async def record_audit(
    *,
    action: str,
    resource: Optional[str] = None,
    user_id: Optional[str] = None,
    request_id: Optional[str] = None,
    ip: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    """
    Write a single audit log entry to analytics.audit_log.

    This function is designed to be called as a fire-and-forget coroutine
    (via asyncio.create_task) so it never blocks the HTTP response path.

    Args:
        action:     Method + path string, e.g. "POST /api/v1/agents/run".
        resource:   The request path, e.g. "/api/v1/agents/run".
        user_id:    UUID string from the JWT ``sub`` claim (may be None for
                    unauthenticated requests that still reach the middleware).
        request_id: UUID string from request.state.request_id.
        ip:         Client IP address string.
        metadata:   Optional extra JSONB payload (headers, query params, etc.).
    """
    try:
        # Convert string UUIDs to uuid.UUID objects (or None)
        uid: Optional[uuid.UUID] = None
        if user_id:
            try:
                uid = uuid.UUID(user_id)
            except (ValueError, AttributeError):
                uid = None

        rid: Optional[uuid.UUID] = None
        if request_id:
            try:
                rid = uuid.UUID(request_id)
            except (ValueError, AttributeError):
                rid = None

        entry = AuditLog(
            user_id=uid,
            action=action,
            resource=resource,
            request_id=rid,
            ip=ip,
            metadata_=metadata,
        )

        async with AsyncSessionLocal() as session:
            session.add(entry)
            await session.commit()

        logger.debug(
            "audit.recorded",
            action=action,
            resource=resource,
            user_id=str(uid) if uid else None,
            request_id=str(rid) if rid else None,
        )

    except Exception as exc:
        # Audit failures must never crash the application.
        logger.error("audit.write_failed", error=str(exc), action=action)


async def cleanup_audit_log(retention_days: Optional[int] = None) -> int:
    """
    Delete audit log entries older than the retention period.

    Args:
        retention_days: Override for AUDIT_LOG_RETENTION_DAYS setting.
                        Defaults to settings.AUDIT_LOG_RETENTION_DAYS (90).

    Returns:
        Number of rows deleted.

    This function is safe to call from a scheduled job (e.g. APScheduler,
    a startup background task, or a cron-triggered endpoint).
    """
    days = retention_days if retention_days is not None else settings.AUDIT_LOG_RETENTION_DAYS
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                delete(AuditLog).where(AuditLog.ts < cutoff)
            )
            deleted = result.rowcount
            await session.commit()

        logger.info(
            "audit.cleanup_done",
            deleted=deleted,
            retention_days=days,
            cutoff=cutoff.isoformat(),
        )
        return deleted

    except Exception as exc:
        logger.error("audit.cleanup_failed", error=str(exc), retention_days=days)
        return 0

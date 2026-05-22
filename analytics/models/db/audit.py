"""
SQLAlchemy ORM model for the general audit log.

Table:
  analytics.audit_log — append-only log of every POST/DELETE action
                        performed by any user through the Analytics API.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Index,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.db.base import ANALYTICS_SCHEMA, Base


class AuditLog(Base):
    """Append-only audit trail for compliance.

    Requirement 0.8 — every POST/DELETE writes an entry with user_id,
                       action, resource, request_id, ip, ts.
    Retention        — 90 days (enforced by a scheduled cleanup job,
                       configurable via AUDIT_LOG_RETENTION_DAYS).
    """

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("idx_audit_ts", "ts"),
        Index("idx_audit_user_ts", "user_id", "ts"),
        {"schema": ANALYTICS_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    resource: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    ip: Mapped[Any | None] = mapped_column(INET, nullable=True)
    metadata_: Mapped[Any | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog id={self.id} action={self.action!r} "
            f"user_id={self.user_id} ts={self.ts}>"
        )

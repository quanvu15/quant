"""
SQLAlchemy ORM model for the agent execution audit log.

Table:
  analytics.agent_runs — records every agent execution with user, persona,
                         query, response, duration, token counts, and status.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.db.base import ANALYTICS_SCHEMA, Base


class AgentRun(Base):
    """Audit record for a single agent execution.

    Requirement 3.4 — every run stored with user_id, persona_id, query,
                       response, duration, tokens, status.
    Property 9      — user_id must match JWT claim.
    """

    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ok', 'error', 'cancelled')",
            name="ck_agent_runs_status",
        ),
        Index("idx_agent_runs_user", "user_id", "created_at"),
        {"schema": ANALYTICS_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    persona_id: Mapped[str] = mapped_column(Text, nullable=False)
    query: Mapped[str | None] = mapped_column(Text, nullable=True)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str | None] = mapped_column(Text, nullable=True)  # ok|error|cancelled
    error: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<AgentRun id={self.id} user_id={self.user_id} "
            f"persona_id={self.persona_id!r} status={self.status!r}>"
        )

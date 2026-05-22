"""
SQLAlchemy ORM models for the chatbot sub-module.

Tables:
  analytics.chat_sessions  — chatbot sessions (per user)
  analytics.chat_messages  — individual messages within a session
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.db.base import ANALYTICS_SCHEMA, Base


class ChatSession(Base):
    """A chatbot conversation session owned by a single user.

    Requirement 2.2 — session persist & ownership.
    Requirement 0.4 — user isolation (user_id == jwt.sub).
    """

    __tablename__ = "chat_sessions"
    __table_args__ = (
        Index("idx_chat_sessions_user", "user_id", "created_at"),
        {"schema": ANALYTICS_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    persona_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[Any] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default="'{}'::jsonb",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationship — cascade delete messages when session is deleted
    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<ChatSession id={self.id} user_id={self.user_id}>"


class ChatMessage(Base):
    """A single message within a chat session.

    Requirement 2.3 — token accounting (tokens_in, tokens_out, latency_ms).
    Requirement 2.5 — tool_calls JSONB for LLM tool call support.
    """

    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint(
            "role IN ('system', 'user', 'assistant', 'tool')",
            name="ck_chat_messages_role",
        ),
        Index("idx_chat_messages_session", "session_id", "created_at"),
        {"schema": ANALYTICS_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{ANALYTICS_SCHEMA}.chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)  # system|user|assistant|tool
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationship
    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="messages")

    def __repr__(self) -> str:
        return f"<ChatMessage id={self.id} role={self.role!r} session_id={self.session_id}>"

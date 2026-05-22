"""
SQLAlchemy ORM models for the news sub-module.

Tables:
  analytics.news_sources   — registry of RSS / scraper sources
  analytics.news_articles  — fetched articles with NLP enrichment fields
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.db.base import ANALYTICS_SCHEMA, Base


class NewsSource(Base):
    """Registry of RSS / scraper news sources.

    Requirement 0.5 — all tables in schema `analytics.*`.
    Requirement 1.1 — source registry with enabled flag and error counter.
    """

    __tablename__ = "news_sources"
    __table_args__ = (
        CheckConstraint("type IN ('rss', 'scraper')", name="ck_news_sources_type"),
        {"schema": ANALYTICS_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)  # 'rss' | 'scraper'
    language: Mapped[str | None] = mapped_column(Text, default="en", server_default="en")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    last_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationship
    articles: Mapped[list["NewsArticle"]] = relationship(
        "NewsArticle", back_populates="source", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"<NewsSource id={self.id} name={self.name!r} enabled={self.enabled}>"


class NewsArticle(Base):
    """Fetched news articles with NLP enrichment.

    Requirement 1.2 — URL uniqueness (dedupe).
    Requirement 1.3 — sentiment ∈ [-1, 1], tickers, entities.
    """

    __tablename__ = "news_articles"
    __table_args__ = (
        # Full-text search index on title + summary
        Index(
            "idx_news_fts",
            func.to_tsvector(
                "simple",
                func.coalesce(Column("title"), "")
                + " "
                + func.coalesce(Column("summary"), ""),
            ),
            postgresql_using="gin",
        ),
        # GIN index on tickers array for fast containment queries
        Index("idx_news_tickers", "tickers", postgresql_using="gin"),
        # B-tree index on published_at DESC for ordering
        Index("idx_news_published", "published_at"),
        CheckConstraint(
            "sentiment IS NULL OR (sentiment >= -1 AND sentiment <= 1)",
            name="ck_news_articles_sentiment_range",
        ),
        {"schema": ANALYTICS_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{ANALYTICS_SCHEMA}.news_sources.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    # url_hash is a computed column in Postgres (md5(url)); we expose it as a
    # server-side computed column — not mapped as a Python attribute to avoid
    # confusion. Alembic migration creates it as GENERATED ALWAYS AS STORED.
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    language: Mapped[str | None] = mapped_column(Text, nullable=True)
    tickers: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    entities: Mapped[Any] = mapped_column(
        JSONB, nullable=False, server_default="'[]'::jsonb"
    )
    sentiment: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    importance: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    raw: Mapped[Any | None] = mapped_column(JSONB, nullable=True)

    # Relationship
    source: Mapped["NewsSource | None"] = relationship(
        "NewsSource", back_populates="articles"
    )

    def __repr__(self) -> str:
        return f"<NewsArticle id={self.id} title={self.title[:40]!r}>"

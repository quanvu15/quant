"""Init analytics schema and all Phase 0-4 tables.

Creates the `analytics` PostgreSQL schema and the following tables:
  - analytics.news_sources
  - analytics.news_articles
  - analytics.chat_sessions
  - analytics.chat_messages
  - analytics.agent_runs
  - analytics.audit_log

Revision ID: 001
Revises: (none — initial migration)
Create Date: 2026-05-20 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "analytics"


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Create the analytics schema
    # ------------------------------------------------------------------
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    # ------------------------------------------------------------------
    # 2. analytics.news_sources
    # ------------------------------------------------------------------
    op.create_table(
        "news_sources",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), server_default="en", nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "last_fetched_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("error_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "type IN ('rss', 'scraper')",
            name="ck_news_sources_type",
        ),
        schema=SCHEMA,
    )

    # ------------------------------------------------------------------
    # 3. analytics.news_articles
    # ------------------------------------------------------------------
    op.create_table(
        "news_articles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.news_sources.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), unique=True, nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("author", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("language", sa.Text(), nullable=True),
        sa.Column("tickers", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column(
            "entities",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("sentiment", sa.Numeric(4, 3), nullable=True),
        sa.Column("importance", sa.Numeric(3, 2), nullable=True),
        sa.Column(
            "raw",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.CheckConstraint(
            "sentiment IS NULL OR (sentiment >= -1 AND sentiment <= 1)",
            name="ck_news_articles_sentiment_range",
        ),
        schema=SCHEMA,
    )

    # url_hash computed column (md5 of url) — Postgres-specific DDL
    op.execute(
        f"""
        ALTER TABLE {SCHEMA}.news_articles
        ADD COLUMN url_hash TEXT GENERATED ALWAYS AS (md5(url)) STORED
        """
    )

    # Indexes for news_articles
    op.create_index(
        "idx_news_published",
        "news_articles",
        [sa.text("published_at DESC")],
        schema=SCHEMA,
    )
    op.create_index(
        "idx_news_tickers",
        "news_articles",
        ["tickers"],
        schema=SCHEMA,
        postgresql_using="gin",
    )
    # Full-text search index on title + summary
    op.execute(
        f"""
        CREATE INDEX idx_news_fts ON {SCHEMA}.news_articles
        USING gin(to_tsvector('simple', title || ' ' || coalesce(summary, '')))
        """
    )

    # ------------------------------------------------------------------
    # 4. analytics.chat_sessions
    # ------------------------------------------------------------------
    op.create_table(
        "chat_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("persona_id", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "idx_chat_sessions_user",
        "chat_sessions",
        ["user_id", sa.text("created_at DESC")],
        schema=SCHEMA,
    )

    # ------------------------------------------------------------------
    # 5. analytics.chat_messages
    # ------------------------------------------------------------------
    op.create_table(
        "chat_messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "tool_calls",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('system', 'user', 'assistant', 'tool')",
            name="ck_chat_messages_role",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "idx_chat_messages_session",
        "chat_messages",
        ["session_id", sa.text("created_at")],
        schema=SCHEMA,
    )

    # ------------------------------------------------------------------
    # 6. analytics.agent_runs
    # ------------------------------------------------------------------
    op.create_table(
        "agent_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("persona_id", sa.Text(), nullable=False),
        sa.Column("query", sa.Text(), nullable=True),
        sa.Column("response", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column(
            "error",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('ok', 'error', 'cancelled')",
            name="ck_agent_runs_status",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "idx_agent_runs_user",
        "agent_runs",
        ["user_id", sa.text("created_at DESC")],
        schema=SCHEMA,
    )

    # ------------------------------------------------------------------
    # 7. analytics.audit_log
    # ------------------------------------------------------------------
    op.create_table(
        "audit_log",
        sa.Column(
            "id",
            sa.BigInteger(),
            primary_key=True,
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("resource", sa.Text(), nullable=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        schema=SCHEMA,
    )
    op.create_index("idx_audit_ts", "audit_log", ["ts"], schema=SCHEMA)
    op.create_index(
        "idx_audit_user_ts", "audit_log", ["user_id", "ts"], schema=SCHEMA
    )

    # ------------------------------------------------------------------
    # 8. Postgres role grant (idempotent helper comment)
    # ------------------------------------------------------------------
    # The following GRANT statements should be run once by a superuser
    # after the schema is created.  They are included here as a comment
    # so the DBA knows what permissions the analytics_app role needs.
    #
    #   CREATE ROLE analytics_app LOGIN PASSWORD '...';
    #   GRANT USAGE ON SCHEMA analytics TO analytics_app;
    #   GRANT ALL ON ALL TABLES IN SCHEMA analytics TO analytics_app;
    #   GRANT ALL ON ALL SEQUENCES IN SCHEMA analytics TO analytics_app;
    #   ALTER DEFAULT PRIVILEGES IN SCHEMA analytics
    #       GRANT ALL ON TABLES TO analytics_app;
    #   ALTER DEFAULT PRIVILEGES IN SCHEMA analytics
    #       GRANT ALL ON SEQUENCES TO analytics_app;


def downgrade() -> None:
    # Drop tables in reverse dependency order
    op.drop_table("audit_log", schema=SCHEMA)
    op.drop_table("agent_runs", schema=SCHEMA)
    op.drop_table("chat_messages", schema=SCHEMA)
    op.drop_table("chat_sessions", schema=SCHEMA)
    op.drop_table("news_articles", schema=SCHEMA)
    op.drop_table("news_sources", schema=SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")

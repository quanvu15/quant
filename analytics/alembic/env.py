"""
Alembic environment configuration for the Analytics microservice.

Key design decisions:
- DATABASE_URL is read from `app.config.settings` (which reads from .env),
  so no credentials are hard-coded here.
- The URL is converted to a *synchronous* psycopg2 URL for Alembic's
  offline/online migration runner (asyncpg is not supported by Alembic
  directly; use the sync driver for migrations only).
- `version_table_schema` is set to `analytics` so the alembic_version table
  lives inside the analytics schema, not in `public`.
- `include_schemas=True` ensures autogenerate inspects the analytics schema.
- `search_path` is set on the connection so unqualified table references
  resolve to the analytics schema.
"""

from __future__ import annotations

import re
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

# ---------------------------------------------------------------------------
# Load Alembic config object (gives access to alembic.ini values)
# ---------------------------------------------------------------------------
config = context.config

# Interpret the config file's logging section.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Import all ORM models so Alembic autogenerate can detect them.
# ---------------------------------------------------------------------------
# This import must happen BEFORE `target_metadata` is set.
from models.db.base import Base, ANALYTICS_SCHEMA  # noqa: E402
import models.db.news   # noqa: F401 — registers NewsSource, NewsArticle
import models.db.chat   # noqa: F401 — registers ChatSession, ChatMessage
import models.db.agent  # noqa: F401 — registers AgentRun
import models.db.audit  # noqa: F401 — registers AuditLog

target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# Resolve DATABASE_URL from settings and convert to sync psycopg2 URL
# ---------------------------------------------------------------------------

def _get_sync_url() -> str:
    """Return a synchronous psycopg2 URL for Alembic migrations.

    The runtime app uses asyncpg (postgresql+asyncpg://...).
    Alembic needs a sync driver, so we swap the driver component.
    """
    try:
        from app.config import settings
        url: str = settings.DATABASE_URL
    except Exception:
        # Fallback: read directly from environment variable
        import os
        url = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/quantdinger")

    # Replace async driver with sync psycopg2
    url = re.sub(r"^postgresql\+asyncpg://", "postgresql+psycopg2://", url)
    url = re.sub(r"^postgres://", "postgresql+psycopg2://", url)
    url = re.sub(r"^postgresql://", "postgresql+psycopg2://", url)
    return url


# Override the placeholder URL in alembic.ini with the real one from settings.
config.set_main_option("sqlalchemy.url", _get_sync_url())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _include_object(obj, name, type_, reflected, compare_to):
    """Only autogenerate for objects in the analytics schema."""
    if type_ == "table":
        return obj.schema == ANALYTICS_SCHEMA
    return True


def _run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to stdout/file).

    Useful for generating SQL scripts to review before applying.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Keep alembic_version table in the analytics schema
        version_table_schema=ANALYTICS_SCHEMA,
        include_schemas=True,
        include_object=_include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def _run_migrations_online() -> None:
    """Run migrations in 'online' mode (apply directly to the database)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    # Pre-create the analytics schema outside the migration transaction
    # so Alembic can place its version table there.
    with connectable.connect() as bootstrap_conn:
        bootstrap_conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {ANALYTICS_SCHEMA}"))
        bootstrap_conn.commit()

    with connectable.connect() as connection:
        # Set search_path so unqualified names resolve to analytics schema.
        connection.execute(text(f"SET search_path TO {ANALYTICS_SCHEMA}, public"))
        connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=ANALYTICS_SCHEMA,
            include_schemas=True,
            include_object=_include_object,
            # Compare server defaults so Alembic detects DEFAULT changes.
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    _run_migrations_offline()
else:
    _run_migrations_online()

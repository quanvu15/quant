"""
SQLAlchemy declarative base and shared metadata for the `analytics` schema.

All ORM models must inherit from `Base`. The MetaData object is configured
with `schema="analytics"` so every table is created in the correct schema
without needing to repeat it in each model's __table_args__.

The `schema` is also read from `settings.DB_SCHEMA` at import time so it
can be overridden via the `DB_SCHEMA` environment variable if needed.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Naming convention for constraints — keeps Alembic autogenerate clean.
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Import settings lazily to avoid circular imports at module load time.
def _get_schema() -> str:
    try:
        from app.config import settings
        return settings.DB_SCHEMA
    except Exception:
        return "analytics"


ANALYTICS_SCHEMA: str = _get_schema()

metadata = MetaData(
    schema=ANALYTICS_SCHEMA,
    naming_convention=NAMING_CONVENTION,
)


class Base(DeclarativeBase):
    """Shared declarative base for all analytics ORM models."""

    metadata = metadata

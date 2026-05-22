"""
Async SQLAlchemy engine and session factory for the Analytics microservice.

Uses asyncpg driver (postgresql+asyncpg://...) for all runtime queries.
Alembic migrations use a separate sync engine (psycopg2) configured in
alembic/env.py.

Usage (FastAPI dependency):
    from core.database import get_db
    async def my_endpoint(db: AsyncSession = Depends(get_db)):
        ...
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
# The DATABASE_URL in settings uses the asyncpg driver
# (postgresql+asyncpg://...).  If the URL uses the plain `postgresql://`
# scheme we swap the driver automatically so callers don't have to worry.
def _async_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


engine: AsyncEngine = create_async_engine(
    _async_url(settings.DATABASE_URL),
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    # Set search_path so every query defaults to the analytics schema.
    connect_args={
        "server_settings": {
            "search_path": settings.DB_SCHEMA,
        }
    },
)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------
AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session; roll back on error, close on exit."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

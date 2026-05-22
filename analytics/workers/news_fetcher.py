"""
News Fetcher Worker — Task 1.2

Runs as a standalone process:
    python -m workers.news_fetcher

Responsibilities:
  - Load active RSS sources from analytics.news_sources every cycle
  - Fetch each source with feedparser + httpx (async, 10s timeout)
  - Push new articles into Redis Stream "analytics:news:queue"
  - Track consecutive errors per source; disable source after 5 failures
  - Update last_fetched_at on success

Requirement 1.1:
  - Runs every NEWS_FETCH_INTERVAL seconds (default 30s)
  - Source error 5 times → set enabled=false + log alert
  - Articles pushed to Redis Stream within < 5s of fetch

Run via docker-compose service "analytics-news-fetcher".
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from typing import Any

import feedparser
import httpx
import structlog
from sqlalchemy import select, update

# Bootstrap path so we can import from project root when run as __main__
if __name__ == "__main__":
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from core.cache import cache
from core.database import AsyncSessionLocal
from core.logging_setup import configure_logging
from domains.news.canonicalize import canonicalize_url
from models.db.news import NewsSource

configure_logging()
logger = structlog.get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

STREAM_KEY = settings.NEWS_QUEUE_STREAM  # "analytics:news:queue"
FETCH_INTERVAL = settings.NEWS_FETCH_INTERVAL  # 30s
FETCH_TIMEOUT = settings.NEWS_FETCH_TIMEOUT  # 10s
ERROR_THRESHOLD = settings.NEWS_SOURCE_ERROR_THRESHOLD  # 5


# ── Helpers ───────────────────────────────────────────────────────────────────

def _entry_to_dict(entry: Any, source: NewsSource) -> dict[str, Any]:
    """Convert a feedparser entry to a dict suitable for Redis Stream."""
    # published_at: try multiple feedparser fields
    published_at: str = ""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            published_at = dt.isoformat()
        except Exception:
            pass
    if not published_at and hasattr(entry, "updated_parsed") and entry.updated_parsed:
        try:
            dt = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
            published_at = dt.isoformat()
        except Exception:
            pass
    if not published_at:
        published_at = datetime.now(timezone.utc).isoformat()

    # URL canonicalization
    raw_url = getattr(entry, "link", "") or ""
    url = canonicalize_url(raw_url) if raw_url else ""

    # Summary / content
    summary = ""
    if hasattr(entry, "summary"):
        summary = entry.summary or ""
    elif hasattr(entry, "description"):
        summary = entry.description or ""

    # Strip basic HTML tags from summary
    import re
    summary = re.sub(r"<[^>]+>", " ", summary).strip()
    summary = re.sub(r"\s+", " ", summary)[:2000]

    return {
        "source_id": str(source.id),
        "source_name": source.name,
        "url": url,
        "raw_url": raw_url,
        "title": (getattr(entry, "title", "") or "").strip()[:500],
        "summary": summary,
        "author": (getattr(entry, "author", "") or "").strip()[:200],
        "published_at": published_at,
        "language": source.language or "en",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


async def _fetch_source(
    client: httpx.AsyncClient,
    source: NewsSource,
) -> list[dict[str, Any]]:
    """
    Fetch RSS feed for a single source.

    Returns list of article dicts (may be empty on error).
    Raises httpx.HTTPError or feedparser-related exceptions on failure.
    """
    response = await client.get(source.url, timeout=FETCH_TIMEOUT)
    response.raise_for_status()

    feed = feedparser.parse(response.text)
    articles = []
    for entry in feed.entries:
        try:
            article = _entry_to_dict(entry, source)
            if article["url"] and article["title"]:
                articles.append(article)
        except Exception as exc:
            logger.warning(
                "news_fetcher.entry_parse_error",
                source=source.name,
                error=str(exc),
            )
    return articles


async def _push_to_stream(redis_client: Any, articles: list[dict[str, Any]]) -> int:
    """Push articles to Redis Stream. Returns count pushed."""
    pushed = 0
    for article in articles:
        try:
            # Redis Stream XADD — each field must be a string
            fields = {k: str(v) for k, v in article.items() if v is not None}
            await redis_client.xadd(STREAM_KEY, fields, maxlen=50000, approximate=True)
            pushed += 1
        except Exception as exc:
            logger.warning(
                "news_fetcher.stream_push_error",
                url=article.get("url", ""),
                error=str(exc),
            )
    return pushed


async def _update_source_success(source_id: str) -> None:
    """Update last_fetched_at and reset error_count on success."""
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(NewsSource)
            .where(NewsSource.id == source_id)
            .values(
                last_fetched_at=datetime.now(timezone.utc),
                error_count=0,
            )
        )
        await session.commit()


async def _update_source_error(source: NewsSource) -> None:
    """Increment error_count; disable source if threshold reached."""
    new_count = (source.error_count or 0) + 1
    should_disable = new_count >= ERROR_THRESHOLD

    async with AsyncSessionLocal() as session:
        await session.execute(
            update(NewsSource)
            .where(NewsSource.id == source.id)
            .values(
                error_count=new_count,
                enabled=not should_disable,
            )
        )
        await session.commit()

    if should_disable:
        logger.warning(
            "news_fetcher.source_disabled",
            source=source.name,
            url=source.url,
            error_count=new_count,
        )


async def _load_active_sources() -> list[NewsSource]:
    """Load all enabled sources from DB."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(NewsSource).where(NewsSource.enabled.is_(True))
        )
        return list(result.scalars().all())


# ── Main fetch cycle ──────────────────────────────────────────────────────────

async def run_fetch_cycle(redis_client: Any) -> None:
    """Run one complete fetch cycle across all active sources."""
    sources = await _load_active_sources()
    if not sources:
        logger.info("news_fetcher.no_active_sources")
        return

    logger.info("news_fetcher.cycle_start", source_count=len(sources))
    total_pushed = 0
    cycle_start = time.monotonic()

    async with httpx.AsyncClient(
        headers={"User-Agent": "AnalyticsBot/1.0 (+https://github.com/FinceptTerminal)"},
        follow_redirects=True,
    ) as client:
        # Fetch all sources concurrently with a semaphore to limit parallelism
        sem = asyncio.Semaphore(10)

        async def fetch_one(source: NewsSource) -> None:
            nonlocal total_pushed
            async with sem:
                try:
                    articles = await _fetch_source(client, source)
                    if articles:
                        pushed = await _push_to_stream(redis_client, articles)
                        total_pushed += pushed
                        logger.debug(
                            "news_fetcher.source_ok",
                            source=source.name,
                            articles=len(articles),
                            pushed=pushed,
                        )
                    await _update_source_success(str(source.id))
                except Exception as exc:
                    logger.warning(
                        "news_fetcher.source_error",
                        source=source.name,
                        url=source.url,
                        error=str(exc),
                    )
                    await _update_source_error(source)

        await asyncio.gather(*[fetch_one(s) for s in sources])

    elapsed = time.monotonic() - cycle_start
    logger.info(
        "news_fetcher.cycle_done",
        sources=len(sources),
        pushed=total_pushed,
        elapsed_s=round(elapsed, 2),
    )


# ── Entry point ───────────────────────────────────────────────────────────────

async def main() -> None:
    """Main loop — runs indefinitely, one cycle every FETCH_INTERVAL seconds."""
    logger.info(
        "news_fetcher.start",
        interval=FETCH_INTERVAL,
        stream=STREAM_KEY,
    )

    # Connect Redis
    await cache.connect()
    redis_client = cache._redis
    if redis_client is None:
        logger.error("news_fetcher.redis_unavailable")
        sys.exit(1)

    while True:
        try:
            await run_fetch_cycle(redis_client)
        except Exception as exc:
            logger.error("news_fetcher.cycle_exception", error=str(exc), exc_info=True)

        await asyncio.sleep(FETCH_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())

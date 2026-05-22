"""
Phase 1 — News API router (full implementation).

Tasks 1.5 (REST) and 1.6 (WebSocket).

REST Endpoints:
  GET  /api/v1/news              — list articles with filters + cursor pagination
  GET  /api/v1/news/search       — Postgres FTS search
  GET  /api/v1/news/{id}         — single article by UUID

WebSocket Endpoint (mounted at /ws/news via ws_router):
  WS   /ws/news                  — realtime article feed (Redis pubsub fanout)

Requirement 1.4: REST API with filter, pagination, FTS.
Requirement 1.5: WebSocket realtime with ticker filter + reconnect backfill.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel
from sqlalchemy import and_, cast, func, select, text
from sqlalchemy.dialects.postgresql import ARRAY, TEXT
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from core.auth import CurrentUser
from core.cache import cache
from core.database import get_db, AsyncSessionLocal
from models.db.news import NewsArticle

logger = structlog.get_logger(__name__)

router = APIRouter()
ws_router = APIRouter()


# ── Response models ───────────────────────────────────────────────────────────

class ArticleResponse(BaseModel):
    id: str
    source_id: Optional[str] = None
    source_name: str
    url: str
    title: str
    summary: Optional[str] = None
    author: Optional[str] = None
    published_at: datetime
    fetched_at: datetime
    language: Optional[str] = None
    tickers: Optional[list[str]] = None
    entities: Optional[list[dict]] = None
    sentiment: Optional[float] = None
    importance: Optional[float] = None

    model_config = {"from_attributes": True}


class NewsListResponse(BaseModel):
    articles: list[ArticleResponse]
    total: int
    cursor: Optional[str] = None


class NewsSearchResponse(BaseModel):
    articles: list[ArticleResponse]
    total: int
    query: str


# ── Helper ────────────────────────────────────────────────────────────────────

def _to_response(article: NewsArticle) -> ArticleResponse:
    return ArticleResponse(
        id=str(article.id),
        source_id=str(article.source_id) if article.source_id else None,
        source_name=article.source_name,
        url=article.url,
        title=article.title,
        summary=article.summary,
        author=article.author,
        published_at=article.published_at,
        fetched_at=article.fetched_at,
        language=article.language,
        tickers=article.tickers,
        entities=article.entities if isinstance(article.entities, list) else [],
        sentiment=float(article.sentiment) if article.sentiment is not None else None,
        importance=float(article.importance) if article.importance is not None else None,
    )


# ── REST: GET /  ──────────────────────────────────────────────────────────────

@router.get("/", response_model=NewsListResponse, summary="List news articles")
async def list_news(
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    ticker: Optional[str] = Query(None, description="Filter by ticker (e.g. AAPL)"),
    source: Optional[str] = Query(None, description="Source name partial match"),
    sentiment_min: Optional[float] = Query(None, ge=-1.0, le=1.0),
    sentiment_max: Optional[float] = Query(None, ge=-1.0, le=1.0),
    from_date: Optional[datetime] = Query(None, alias="from"),
    to_date: Optional[datetime] = Query(None, alias="to"),
    language: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = Query(None, description="published_at ISO timestamp of last item"),
) -> NewsListResponse:
    """List news articles with optional filters and cursor pagination."""
    conditions: list = []

    if ticker:
        conditions.append(
            NewsArticle.tickers.contains(cast([ticker.upper()], ARRAY(TEXT)))
        )
    if source:
        conditions.append(NewsArticle.source_name.ilike(f"%{source}%"))
    if sentiment_min is not None:
        conditions.append(NewsArticle.sentiment >= sentiment_min)
    if sentiment_max is not None:
        conditions.append(NewsArticle.sentiment <= sentiment_max)
    if from_date:
        conditions.append(NewsArticle.published_at >= from_date)
    if to_date:
        conditions.append(NewsArticle.published_at <= to_date)
    if language:
        conditions.append(NewsArticle.language == language.lower())

    # Cursor: next page starts before this timestamp
    cursor_condition = None
    if cursor:
        try:
            cursor_dt = datetime.fromisoformat(cursor)
            cursor_condition = NewsArticle.published_at < cursor_dt
        except ValueError:
            pass

    base_where = and_(*conditions) if conditions else text("1=1")
    page_where = and_(base_where, cursor_condition) if cursor_condition else base_where

    # Total count (no cursor)
    count_result = await db.execute(
        select(func.count()).select_from(NewsArticle).where(base_where)
    )
    total = count_result.scalar() or 0

    # Fetch page
    result = await db.execute(
        select(NewsArticle)
        .where(page_where)
        .order_by(NewsArticle.published_at.desc())
        .limit(limit)
    )
    articles = list(result.scalars().all())

    next_cursor = articles[-1].published_at.isoformat() if len(articles) == limit else None

    return NewsListResponse(
        articles=[_to_response(a) for a in articles],
        total=total,
        cursor=next_cursor,
    )


# ── REST: GET /search  ────────────────────────────────────────────────────────

@router.get("/search", response_model=NewsSearchResponse, summary="Full-text search news")
async def search_news(
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    q: str = Query(..., min_length=1, max_length=500),
    limit: int = Query(20, ge=1, le=100),
) -> NewsSearchResponse:
    """Postgres FTS search over title + summary."""
    safe_q = re.sub(r"[^\w\s]", " ", q).strip()
    if not safe_q:
        return NewsSearchResponse(articles=[], total=0, query=q)

    tsquery = " & ".join(safe_q.split())
    fts = text(
        "to_tsvector('simple', title || ' ' || coalesce(summary, '')) "
        "@@ to_tsquery('simple', :q)"
    ).bindparams(q=tsquery)

    total = (await db.execute(select(func.count()).select_from(NewsArticle).where(fts))).scalar() or 0
    rows = list((await db.execute(
        select(NewsArticle).where(fts).order_by(NewsArticle.published_at.desc()).limit(limit)
    )).scalars().all())

    return NewsSearchResponse(articles=[_to_response(a) for a in rows], total=total, query=q)


# ── REST: GET /{id}  ──────────────────────────────────────────────────────────

@router.get("/{article_id}", response_model=ArticleResponse, summary="Get article by ID")
async def get_news_article(
    article_id: str,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> ArticleResponse:
    """Get a single article by UUID."""
    try:
        aid = uuid.UUID(article_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_PARAMS", "message": "Invalid article ID format."},
        )

    row = (await db.execute(select(NewsArticle).where(NewsArticle.id == aid))).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Article not found."},
        )
    return _to_response(row)


# ── WebSocket: /ws/news  ──────────────────────────────────────────────────────

@ws_router.websocket("/news")
async def news_websocket(
    websocket: WebSocket,
    ticker: Optional[str] = Query(None),
    since: Optional[str] = Query(None, description="ISO timestamp for backfill"),
) -> None:
    """
    Realtime news WebSocket — Task 1.6 / Requirement 1.5.

    Events sent by server:
      {"type": "article_new",      "data": {...}}   — new article from NLP pipeline
      {"type": "article_backfill", "data": {...}}   — backfill on reconnect
      {"type": "ping",             "ts":  "..."}    — heartbeat every 30s

    Client may send {"type": "pong"} to acknowledge heartbeat.
    Pass ?ticker=AAPL to filter; omit for all articles.
    Pass ?since=<ISO> to backfill articles missed since that timestamp.
    """
    await websocket.accept()
    logger.info("ws.news.connected", ticker=ticker, client=str(websocket.client))

    redis_client = cache._redis
    if redis_client is None:
        await websocket.send_json({"type": "error", "message": "Redis unavailable"})
        await websocket.close()
        return

    # ── Backfill ──────────────────────────────────────────────────────────────
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
            async with AsyncSessionLocal() as db:
                conds: list = [NewsArticle.published_at > since_dt]
                if ticker:
                    conds.append(
                        NewsArticle.tickers.contains(cast([ticker.upper()], ARRAY(TEXT)))
                    )
                rows = list((await db.execute(
                    select(NewsArticle)
                    .where(and_(*conds))
                    .order_by(NewsArticle.published_at.asc())
                    .limit(100)
                )).scalars().all())
                for a in rows:
                    await websocket.send_json({
                        "type": "article_backfill",
                        "data": {
                            "id": str(a.id),
                            "title": a.title,
                            "summary": a.summary,
                            "url": a.url,
                            "source_name": a.source_name,
                            "published_at": a.published_at.isoformat(),
                            "tickers": a.tickers or [],
                            "sentiment": float(a.sentiment) if a.sentiment is not None else None,
                        },
                    })
        except Exception as exc:
            logger.warning("ws.news.backfill_error", error=str(exc))

    # ── Subscribe Redis pubsub ────────────────────────────────────────────────
    pubsub = redis_client.pubsub()
    try:
        await pubsub.psubscribe(f"{settings.NEWS_PUBSUB_PREFIX}*")

        heartbeat_interval = 30.0
        last_hb = asyncio.get_event_loop().time()

        while True:
            now = asyncio.get_event_loop().time()

            # Heartbeat
            if now - last_hb >= heartbeat_interval:
                try:
                    await websocket.send_json({"type": "ping", "ts": datetime.now(timezone.utc).isoformat()})
                    last_hb = now
                except Exception:
                    break

            # Read pubsub (non-blocking, 1s timeout)
            try:
                msg = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True),
                    timeout=1.0,
                )
            except asyncio.TimeoutError:
                msg = None
            except Exception as exc:
                logger.warning("ws.news.pubsub_error", error=str(exc))
                break

            if msg and msg.get("type") in ("message", "pmessage"):
                try:
                    raw = msg.get("data", b"")
                    payload = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                    # Ticker filter
                    if ticker:
                        art_tickers = payload.get("data", {}).get("tickers", [])
                        if ticker.upper() not in [t.upper() for t in art_tickers]:
                            continue
                    await websocket.send_json(payload)
                except Exception as exc:
                    logger.debug("ws.news.send_error", error=str(exc))

            # Read client messages (non-blocking)
            try:
                client_msg = await asyncio.wait_for(websocket.receive_text(), timeout=0.01)
                try:
                    parsed = json.loads(client_msg)
                    if parsed.get("type") == "pong":
                        pass
                except Exception:
                    pass
            except asyncio.TimeoutError:
                pass
            except (WebSocketDisconnect, Exception):
                break

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("ws.news.error", error=str(exc))
    finally:
        try:
            await pubsub.punsubscribe()
            await pubsub.aclose()
        except Exception:
            pass
        logger.info("ws.news.closed", ticker=ticker)

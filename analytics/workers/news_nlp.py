"""
News NLP Worker — Task 1.4

Runs as a standalone process:
    python -m workers.news_nlp

Responsibilities:
  - Consumer group on Redis Stream "analytics:news:queue"
  - Deduplicate articles by canonical URL (UNIQUE constraint in DB)
  - Run FinBERT sentiment analysis (ProsusAI/finbert, Apache 2.0)
  - Run spaCy NER (en_core_web_sm) for ORG, GPE, PERSON entities
  - Match tickers against S&P500 + NASDAQ100 list
  - Insert enriched articles into analytics.news_articles
  - Publish to Redis pubsub "analytics:news:pubsub:{ticker1},{ticker2},..."
  - XACK message after successful processing

Requirement 1.3:
  - Sentiment ∈ [-1, 1]
  - Tickers matched against known list
  - End-to-end latency (RSS → DB enriched) < 60s

Run via docker-compose service "analytics-news-nlp".
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Optional

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

# Bootstrap path so we can import from project root when run as __main__
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from core.cache import cache
from core.database import AsyncSessionLocal
from core.logging_setup import configure_logging
from core.metrics import record_news_pipeline_lag
from domains.news.canonicalize import canonicalize_url
from models.db.news import NewsArticle

configure_logging()
logger = structlog.get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

STREAM_KEY = settings.NEWS_QUEUE_STREAM          # "analytics:news:queue"
CONSUMER_GROUP = "analytics-nlp-group"
CONSUMER_NAME = f"nlp-worker-{os.getpid()}"
PUBSUB_PREFIX = settings.NEWS_PUBSUB_PREFIX      # "analytics:news:pubsub:"
BATCH_SIZE = 10                                   # messages per XREADGROUP call
BLOCK_MS = 5000                                   # block 5s waiting for messages

# ── NLP model loading (lazy) ──────────────────────────────────────────────────

_sentiment_pipeline: Any = None
_nlp_model: Any = None
_known_tickers: set[str] = set()


def _load_tickers() -> set[str]:
    """Load known tickers from tickers.json."""
    global _known_tickers
    if _known_tickers:
        return _known_tickers
    try:
        tickers_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "domains", "news", "tickers.json",
        )
        with open(tickers_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        _known_tickers = {t.upper() for t in data.get("tickers", [])}
        logger.info("nlp.tickers_loaded", count=len(_known_tickers))
    except Exception as exc:
        logger.warning("nlp.tickers_load_failed", error=str(exc))
        _known_tickers = set()
    return _known_tickers


def _get_sentiment_pipeline():
    """Lazy-load FinBERT sentiment pipeline."""
    global _sentiment_pipeline
    if _sentiment_pipeline is not None:
        return _sentiment_pipeline
    try:
        from transformers import pipeline as hf_pipeline
        logger.info("nlp.loading_finbert", model=settings.NEWS_SENTIMENT_MODEL)
        _sentiment_pipeline = hf_pipeline(
            "text-classification",
            model=settings.NEWS_SENTIMENT_MODEL,
            top_k=None,
            truncation=True,
            max_length=512,
        )
        logger.info("nlp.finbert_loaded")
    except Exception as exc:
        logger.warning("nlp.finbert_unavailable", error=str(exc))
        _sentiment_pipeline = None
    return _sentiment_pipeline


def _get_spacy_model():
    """Lazy-load spaCy NER model."""
    global _nlp_model
    if _nlp_model is not None:
        return _nlp_model
    try:
        import spacy
        logger.info("nlp.loading_spacy", model=settings.NEWS_NER_MODEL)
        _nlp_model = spacy.load(settings.NEWS_NER_MODEL)
        logger.info("nlp.spacy_loaded")
    except Exception as exc:
        logger.warning("nlp.spacy_unavailable", error=str(exc))
        _nlp_model = None
    return _nlp_model


# ── NLP helpers ───────────────────────────────────────────────────────────────

def _compute_sentiment(text: str) -> Optional[float]:
    """
    Run FinBERT sentiment on text.

    Returns a float in [-1, 1]:
      positive → +score
      negative → -score
      neutral  → 0.0

    Returns None if model unavailable or text is empty.
    """
    if not text or not text.strip():
        return None
    pipe = _get_sentiment_pipeline()
    if pipe is None:
        return None
    try:
        # FinBERT returns list of [{label, score}]
        results = pipe(text[:512])
        if not results:
            return None
        # results is list of list when top_k=None
        scores = results[0] if isinstance(results[0], list) else results
        label_scores = {r["label"].lower(): r["score"] for r in scores}
        pos = label_scores.get("positive", 0.0)
        neg = label_scores.get("negative", 0.0)
        # Map to [-1, 1]: positive - negative
        sentiment = round(float(pos - neg), 3)
        # Clamp to [-1, 1]
        return max(-1.0, min(1.0, sentiment))
    except Exception as exc:
        logger.debug("nlp.sentiment_error", error=str(exc))
        return None


def _extract_entities(text: str) -> list[dict[str, str]]:
    """
    Run spaCy NER on text.

    Returns list of {text, label} dicts for ORG, GPE, PERSON entities.
    Returns [] if model unavailable.
    """
    if not text or not text.strip():
        return []
    nlp = _get_spacy_model()
    if nlp is None:
        return []
    try:
        doc = nlp(text[:1000])
        seen: set[str] = set()
        entities = []
        for ent in doc.ents:
            if ent.label_ in ("ORG", "GPE", "PERSON"):
                key = f"{ent.text}:{ent.label_}"
                if key not in seen:
                    seen.add(key)
                    entities.append({"text": ent.text, "label": ent.label_})
        return entities
    except Exception as exc:
        logger.debug("nlp.ner_error", error=str(exc))
        return []


def _match_tickers(text: str, entities: list[dict[str, str]]) -> list[str]:
    """
    Match known tickers in text and entity names.

    Strategy:
      1. Tokenize text on whitespace + punctuation
      2. Check each token (uppercased) against known_tickers set
      3. Also check entity texts for ORG entities

    Returns sorted, deduplicated list of matched tickers.
    """
    import re
    known = _load_tickers()
    if not known:
        return []

    found: set[str] = set()

    # Tokenize text
    tokens = re.findall(r"[A-Z]{1,5}(?:\.[A-Z]{1,2})?", text.upper())
    for token in tokens:
        if token in known:
            found.add(token)

    # Check entity texts (ORG entities often contain ticker-like strings)
    for ent in entities:
        if ent.get("label") == "ORG":
            org_tokens = re.findall(r"[A-Z]{1,5}(?:\.[A-Z]{1,2})?", ent["text"].upper())
            for token in org_tokens:
                if token in known:
                    found.add(token)

    return sorted(found)


# ── Article processing ────────────────────────────────────────────────────────

def _process_article(msg_data: dict[str, str]) -> dict[str, Any]:
    """
    Run NLP enrichment on a raw article dict from the Redis Stream.

    Returns enriched article dict ready for DB insert.
    """
    title = msg_data.get("title", "")
    summary = msg_data.get("summary", "")
    text_for_nlp = f"{title}. {summary}"

    # Sentiment
    sentiment = _compute_sentiment(text_for_nlp)

    # NER
    entities = _extract_entities(text_for_nlp)

    # Ticker matching
    tickers = _match_tickers(text_for_nlp, entities)

    # Parse published_at
    published_at_str = msg_data.get("published_at", "")
    try:
        published_at = datetime.fromisoformat(published_at_str)
    except Exception:
        published_at = datetime.now(timezone.utc)

    # Canonical URL (already canonicalized by fetcher, but re-apply for safety)
    url = canonicalize_url(msg_data.get("url", ""))

    return {
        "source_id": msg_data.get("source_id") or None,
        "source_name": msg_data.get("source_name", ""),
        "url": url,
        "title": title,
        "summary": summary,
        "author": msg_data.get("author") or None,
        "published_at": published_at,
        "language": msg_data.get("language", "en"),
        "tickers": tickers or None,
        "entities": entities,
        "sentiment": sentiment,
        "raw": {k: v for k, v in msg_data.items() if k not in ("source_id", "source_name")},
    }


async def _insert_article(article_data: dict[str, Any]) -> Optional[NewsArticle]:
    """
    Insert article into DB. Returns the inserted article or None on dedupe.

    Deduplication: URL UNIQUE constraint — IntegrityError on duplicate.
    """
    import uuid as _uuid
    try:
        # Convert source_id string to UUID if present
        source_id = article_data.get("source_id")
        if source_id:
            try:
                source_id = _uuid.UUID(source_id)
            except (ValueError, AttributeError):
                source_id = None

        article = NewsArticle(
            source_id=source_id,
            source_name=article_data["source_name"],
            url=article_data["url"],
            title=article_data["title"],
            summary=article_data.get("summary"),
            author=article_data.get("author"),
            published_at=article_data["published_at"],
            language=article_data.get("language", "en"),
            tickers=article_data.get("tickers"),
            entities=article_data.get("entities", []),
            sentiment=article_data.get("sentiment"),
            raw=article_data.get("raw"),
        )
        async with AsyncSessionLocal() as session:
            session.add(article)
            await session.commit()
            await session.refresh(article)
            return article
    except IntegrityError:
        # Duplicate URL — expected, not an error
        logger.debug("nlp.dedupe_skip", url=article_data.get("url", ""))
        return None
    except Exception as exc:
        logger.error("nlp.insert_error", error=str(exc), url=article_data.get("url", ""))
        return None


async def _publish_article(redis_client: Any, article: NewsArticle) -> None:
    """Publish article to Redis pubsub channels for WebSocket fanout."""
    try:
        payload = json.dumps({
            "type": "article_new",
            "data": {
                "id": str(article.id),
                "title": article.title,
                "summary": article.summary,
                "url": article.url,
                "source_name": article.source_name,
                "published_at": article.published_at.isoformat() if article.published_at else None,
                "tickers": article.tickers or [],
                "sentiment": float(article.sentiment) if article.sentiment is not None else None,
                "entities": article.entities or [],
            },
        })

        # Publish to ticker-specific channels
        tickers = article.tickers or []
        if tickers:
            channel = f"{PUBSUB_PREFIX}{','.join(tickers)}"
            await redis_client.publish(channel, payload)

        # Always publish to the global channel
        await redis_client.publish(f"{PUBSUB_PREFIX}*", payload)

    except Exception as exc:
        logger.warning("nlp.publish_error", error=str(exc))


# ── Consumer group setup ──────────────────────────────────────────────────────

async def _ensure_consumer_group(redis_client: Any) -> None:
    """Create consumer group if it doesn't exist."""
    try:
        await redis_client.xgroup_create(
            STREAM_KEY, CONSUMER_GROUP, id="0", mkstream=True
        )
        logger.info("nlp.consumer_group_created", group=CONSUMER_GROUP)
    except Exception as exc:
        # BUSYGROUP error means group already exists — that's fine
        if "BUSYGROUP" not in str(exc):
            logger.warning("nlp.consumer_group_error", error=str(exc))


# ── Main processing loop ──────────────────────────────────────────────────────

async def process_messages(redis_client: Any) -> None:
    """Read and process messages from the Redis Stream consumer group."""
    try:
        messages = await redis_client.xreadgroup(
            CONSUMER_GROUP,
            CONSUMER_NAME,
            {STREAM_KEY: ">"},
            count=BATCH_SIZE,
            block=BLOCK_MS,
        )
    except Exception as exc:
        logger.warning("nlp.xreadgroup_error", error=str(exc))
        await asyncio.sleep(1)
        return

    if not messages:
        return

    for stream_name, entries in messages:
        for msg_id, msg_data in entries:
            start = time.monotonic()
            try:
                # Decode bytes keys/values from Redis
                decoded = {
                    (k.decode() if isinstance(k, bytes) else k): (
                        v.decode() if isinstance(v, bytes) else v
                    )
                    for k, v in msg_data.items()
                }

                if not decoded.get("url") or not decoded.get("title"):
                    # Skip malformed messages
                    await redis_client.xack(STREAM_KEY, CONSUMER_GROUP, msg_id)
                    continue

                # NLP enrichment (CPU-bound — run in thread pool)
                loop = asyncio.get_event_loop()
                enriched = await loop.run_in_executor(None, _process_article, decoded)

                # DB insert
                article = await _insert_article(enriched)

                if article:
                    # Publish to WebSocket fanout
                    await _publish_article(redis_client, article)

                    # Record pipeline lag metric: now - published_at
                    try:
                        pub_at = enriched.get("published_at")
                        if pub_at is not None:
                            now_utc = datetime.now(timezone.utc)
                            if pub_at.tzinfo is None:
                                pub_at = pub_at.replace(tzinfo=timezone.utc)
                            lag_s = (now_utc - pub_at).total_seconds()
                            if lag_s >= 0:
                                record_news_pipeline_lag(lag_s)
                    except Exception:
                        pass  # metric failure must not affect processing

                    elapsed = time.monotonic() - start
                    logger.debug(
                        "nlp.article_processed",
                        url=enriched["url"],
                        tickers=enriched.get("tickers"),
                        sentiment=enriched.get("sentiment"),
                        elapsed_ms=round(elapsed * 1000),
                    )

                # XACK — mark message as processed
                await redis_client.xack(STREAM_KEY, CONSUMER_GROUP, msg_id)

            except Exception as exc:
                logger.error(
                    "nlp.message_error",
                    msg_id=str(msg_id),
                    error=str(exc),
                    exc_info=True,
                )
                # Still ACK to avoid infinite retry loop on bad messages
                try:
                    await redis_client.xack(STREAM_KEY, CONSUMER_GROUP, msg_id)
                except Exception:
                    pass


async def main() -> None:
    """Main loop — continuously consume from Redis Stream."""
    logger.info(
        "news_nlp.start",
        stream=STREAM_KEY,
        group=CONSUMER_GROUP,
        consumer=CONSUMER_NAME,
    )

    # Pre-load models and tickers at startup
    _load_tickers()
    # Models are lazy-loaded on first use to avoid blocking startup

    # Connect Redis
    await cache.connect()
    redis_client = cache._redis
    if redis_client is None:
        logger.error("news_nlp.redis_unavailable")
        sys.exit(1)

    # Ensure consumer group exists
    await _ensure_consumer_group(redis_client)

    logger.info("news_nlp.ready")

    while True:
        try:
            await process_messages(redis_client)
        except Exception as exc:
            logger.error("news_nlp.loop_error", error=str(exc), exc_info=True)
            await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())

"""Seed ~20 financial RSS news sources into analytics.news_sources.

Revision ID: 002
Revises: 001
Create Date: 2026-05-21

Task 1.1 — News sources seed data.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "analytics"

# ~20 financial RSS sources (all public/free RSS feeds)
SOURCES = [
    {
        "name": "Reuters Business",
        "url": "https://feeds.reuters.com/reuters/businessNews",
        "language": "en",
    },
    {
        "name": "Reuters Markets",
        "url": "https://feeds.reuters.com/reuters/companyNews",
        "language": "en",
    },
    {
        "name": "Reuters Technology",
        "url": "https://feeds.reuters.com/reuters/technologyNews",
        "language": "en",
    },
    {
        "name": "Yahoo Finance",
        "url": "https://finance.yahoo.com/news/rssindex",
        "language": "en",
    },
    {
        "name": "MarketWatch Top Stories",
        "url": "https://feeds.marketwatch.com/marketwatch/topstories",
        "language": "en",
    },
    {
        "name": "MarketWatch Market Pulse",
        "url": "https://feeds.marketwatch.com/marketwatch/marketpulse",
        "language": "en",
    },
    {
        "name": "Investing.com News",
        "url": "https://www.investing.com/rss/news.rss",
        "language": "en",
    },
    {
        "name": "Investing.com Stock Market News",
        "url": "https://www.investing.com/rss/news_25.rss",
        "language": "en",
    },
    {
        "name": "CNBC Finance",
        "url": "https://www.cnbc.com/id/10000664/device/rss/rss.html",
        "language": "en",
    },
    {
        "name": "CNBC Earnings",
        "url": "https://www.cnbc.com/id/15839135/device/rss/rss.html",
        "language": "en",
    },
    {
        "name": "Forbes Business",
        "url": "https://www.forbes.com/business/feed/",
        "language": "en",
    },
    {
        "name": "Forbes Investing",
        "url": "https://www.forbes.com/investing/feed/",
        "language": "en",
    },
    {
        "name": "Business Insider Markets",
        "url": "https://markets.businessinsider.com/rss/news",
        "language": "en",
    },
    {
        "name": "Seeking Alpha Market News",
        "url": "https://seekingalpha.com/market_currents.xml",
        "language": "en",
    },
    {
        "name": "The Economist Finance",
        "url": "https://www.economist.com/finance-and-economics/rss.xml",
        "language": "en",
    },
    {
        "name": "Morningstar News",
        "url": "https://www.morningstar.com/rss/rss.aspx?section=topstories",
        "language": "en",
    },
    {
        "name": "Zerohedge",
        "url": "https://feeds.feedburner.com/zerohedge/feed",
        "language": "en",
    },
    {
        "name": "Financial Post",
        "url": "https://financialpost.com/feed",
        "language": "en",
    },
    {
        "name": "BBC Business",
        "url": "https://feeds.bbci.co.uk/news/business/rss.xml",
        "language": "en",
    },
    {
        "name": "Barron's",
        "url": "https://www.barrons.com/xml/rss/3_7510.xml",
        "language": "en",
    },
]


def upgrade() -> None:
    conn = op.get_bind()
    for src in SOURCES:
        conn.execute(
            sa.text(
                f"""
                INSERT INTO {SCHEMA}.news_sources (name, url, type, language, enabled)
                VALUES (:name, :url, 'rss', :language, true)
                ON CONFLICT DO NOTHING
                """
            ),
            {"name": src["name"], "url": src["url"], "language": src["language"]},
        )


def downgrade() -> None:
    conn = op.get_bind()
    urls = [s["url"] for s in SOURCES]
    for url in urls:
        conn.execute(
            sa.text(f"DELETE FROM {SCHEMA}.news_sources WHERE url = :url"),
            {"url": url},
        )

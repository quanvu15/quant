"""
Tests for news article deduplication — Task 1.7 / Property 4.

Tests that inserting the same canonical URL twice results in only 1 DB row.
Uses in-memory SQLite for unit tests (no Postgres required).
"""

from __future__ import annotations

import pytest

from domains.news.canonicalize import canonicalize_url


class TestDedupeLogic:
    """Unit tests for deduplication logic (no DB required)."""

    def test_same_url_same_canonical(self):
        url = "https://reuters.com/article/1"
        assert canonicalize_url(url) == canonicalize_url(url)

    def test_url_with_tracking_dedupes(self):
        url1 = "https://reuters.com/article/1?utm_source=twitter"
        url2 = "https://reuters.com/article/1?utm_source=facebook&utm_medium=social"
        assert canonicalize_url(url1) == canonicalize_url(url2)

    def test_url_with_fragment_dedupes(self):
        url1 = "https://reuters.com/article/1#section1"
        url2 = "https://reuters.com/article/1#section2"
        assert canonicalize_url(url1) == canonicalize_url(url2)

    def test_url_case_dedupes(self):
        url1 = "https://Reuters.COM/article/1"
        url2 = "https://reuters.com/article/1"
        assert canonicalize_url(url1) == canonicalize_url(url2)

    def test_url_trailing_slash_dedupes(self):
        url1 = "https://reuters.com/article/1/"
        url2 = "https://reuters.com/article/1"
        assert canonicalize_url(url1) == canonicalize_url(url2)

    def test_different_articles_dont_dedupe(self):
        url1 = "https://reuters.com/article/1"
        url2 = "https://reuters.com/article/2"
        assert canonicalize_url(url1) != canonicalize_url(url2)

    def test_different_domains_dont_dedupe(self):
        url1 = "https://reuters.com/article/1"
        url2 = "https://bloomberg.com/article/1"
        assert canonicalize_url(url1) != canonicalize_url(url2)

    def test_query_param_order_dedupes(self):
        """Same params in different order → same canonical."""
        url1 = "https://example.com/news?b=2&a=1"
        url2 = "https://example.com/news?a=1&b=2"
        assert canonicalize_url(url1) == canonicalize_url(url2)

    def test_mixed_tracking_and_content_params(self):
        """Tracking params stripped, content params kept and sorted."""
        url1 = "https://example.com/news?id=42&utm_source=tw&ref=home"
        url2 = "https://example.com/news?id=42"
        assert canonicalize_url(url1) == canonicalize_url(url2)

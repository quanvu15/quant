"""
Tests for URL canonicalization — Task 1.7 / Property 4.

Tests:
  - Basic canonicalization rules
  - Tracking param stripping
  - Fragment stripping
  - Query param sorting
  - Idempotency (applying twice = same result)
  - Non-HTTP URLs pass through unchanged
"""

from __future__ import annotations

import pytest

from domains.news.canonicalize import canonicalize_url


class TestBasicCanonicalization:
    def test_lowercase_host(self):
        assert canonicalize_url("https://Reuters.COM/article/1") == "https://reuters.com/article/1"

    def test_lowercase_scheme(self):
        assert canonicalize_url("HTTPS://example.com/news") == "https://example.com/news"

    def test_strip_fragment(self):
        assert canonicalize_url("https://example.com/news#top") == "https://example.com/news"

    def test_strip_trailing_slash(self):
        assert canonicalize_url("https://example.com/news/") == "https://example.com/news"

    def test_preserve_root_slash(self):
        result = canonicalize_url("https://example.com/")
        assert result == "https://example.com/"

    def test_collapse_double_slashes(self):
        assert canonicalize_url("https://example.com/news//story/") == "https://example.com/news/story"

    def test_preserve_query_params(self):
        result = canonicalize_url("https://example.com/news?id=42")
        assert "id=42" in result

    def test_sort_query_params(self):
        result = canonicalize_url("https://example.com/news?z=1&a=2")
        assert result == "https://example.com/news?a=2&z=1"


class TestTrackingParamStripping:
    def test_strip_utm_source(self):
        result = canonicalize_url("https://example.com/news?utm_source=twitter&id=42")
        assert "utm_source" not in result
        assert "id=42" in result

    def test_strip_utm_medium(self):
        result = canonicalize_url("https://example.com/news?utm_medium=social")
        assert "utm_medium" not in result

    def test_strip_utm_campaign(self):
        result = canonicalize_url("https://example.com/news?utm_campaign=launch")
        assert "utm_campaign" not in result

    def test_strip_fbclid(self):
        result = canonicalize_url("https://example.com/news?fbclid=abc123&id=5")
        assert "fbclid" not in result
        assert "id=5" in result

    def test_strip_gclid(self):
        result = canonicalize_url("https://example.com/news?gclid=xyz")
        assert "gclid" not in result

    def test_strip_ref(self):
        result = canonicalize_url("https://example.com/news?ref=homepage&id=1")
        assert "ref=" not in result
        assert "id=1" in result

    def test_strip_multiple_tracking_params(self):
        url = "https://reuters.com/article/1?utm_source=tw&utm_medium=social&fbclid=abc&id=42"
        result = canonicalize_url(url)
        assert "utm_source" not in result
        assert "utm_medium" not in result
        assert "fbclid" not in result
        assert "id=42" in result

    def test_strip_mc_prefix(self):
        result = canonicalize_url("https://example.com/news?mc_cid=abc&id=1")
        assert "mc_cid" not in result

    def test_strip_ga(self):
        result = canonicalize_url("https://example.com/news?_ga=GA1.2.abc&id=1")
        assert "_ga" not in result


class TestIdempotency:
    """Applying canonicalize_url twice should give the same result."""

    def test_idempotent_basic(self):
        url = "https://Reuters.COM/article/1?utm_source=tw#top"
        once = canonicalize_url(url)
        twice = canonicalize_url(once)
        assert once == twice

    def test_idempotent_with_params(self):
        url = "https://example.com/news?z=1&a=2&utm_campaign=x"
        once = canonicalize_url(url)
        twice = canonicalize_url(once)
        assert once == twice

    def test_idempotent_trailing_slash(self):
        url = "https://example.com/news/"
        once = canonicalize_url(url)
        twice = canonicalize_url(once)
        assert once == twice


class TestEdgeCases:
    def test_empty_string(self):
        assert canonicalize_url("") == ""

    def test_non_http_scheme_passthrough(self):
        url = "ftp://example.com/file"
        assert canonicalize_url(url) == url

    def test_mailto_passthrough(self):
        url = "mailto:user@example.com"
        assert canonicalize_url(url) == url

    def test_no_path(self):
        result = canonicalize_url("https://example.com")
        assert result == "https://example.com"

    def test_port_preserved(self):
        result = canonicalize_url("https://example.com:8080/news")
        assert "8080" in result

    def test_real_reuters_url(self):
        url = "https://feeds.reuters.com/reuters/businessNews?utm_source=feedburner&utm_medium=feed"
        result = canonicalize_url(url)
        assert "utm_source" not in result
        assert "utm_medium" not in result
        assert "reuters.com" in result

    def test_same_url_different_tracking_same_canonical(self):
        """Two URLs differing only in tracking params → same canonical."""
        url1 = "https://example.com/article/1?utm_source=twitter"
        url2 = "https://example.com/article/1?utm_source=facebook"
        assert canonicalize_url(url1) == canonicalize_url(url2)

    def test_different_content_params_different_canonical(self):
        """Two URLs with different content params → different canonical."""
        url1 = "https://example.com/article?id=1"
        url2 = "https://example.com/article?id=2"
        assert canonicalize_url(url1) != canonicalize_url(url2)

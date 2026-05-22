"""
URL canonicalization for news article deduplication.

Task 1.3 — Validates Property 4 (news dedupe).

Rules applied (in order):
  1. Parse URL with urllib.parse.urlparse
  2. Lowercase scheme + host
  3. Normalize path: collapse double slashes, strip trailing slash
     (except root "/")
  4. Strip fragment (#...)
  5. Filter query params: drop utm_*, fbclid, gclid, ref, source, mc_*,
     _ga, _gl, campaign, medium, content, term, s, via
  6. Sort remaining query params alphabetically
  7. Rebuild URL

The result is a stable, lowercase, fragment-free URL suitable for use as
a deduplication key in analytics.news_articles.url.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# Query parameters that are tracking/analytics noise and should be stripped.
_STRIP_PARAM_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^utm_", re.IGNORECASE),
    re.compile(r"^fbclid$", re.IGNORECASE),
    re.compile(r"^gclid$", re.IGNORECASE),
    re.compile(r"^ref$", re.IGNORECASE),
    re.compile(r"^source$", re.IGNORECASE),
    re.compile(r"^mc_", re.IGNORECASE),
    re.compile(r"^_ga$", re.IGNORECASE),
    re.compile(r"^_gl$", re.IGNORECASE),
    re.compile(r"^campaign$", re.IGNORECASE),
    re.compile(r"^medium$", re.IGNORECASE),
    re.compile(r"^content$", re.IGNORECASE),
    re.compile(r"^term$", re.IGNORECASE),
    re.compile(r"^s$", re.IGNORECASE),
    re.compile(r"^via$", re.IGNORECASE),
    re.compile(r"^cmpid$", re.IGNORECASE),
    re.compile(r"^ncid$", re.IGNORECASE),
    re.compile(r"^partner$", re.IGNORECASE),
    re.compile(r"^referrer$", re.IGNORECASE),
]


def _should_strip_param(name: str) -> bool:
    """Return True if the query parameter should be stripped."""
    return any(p.match(name) for p in _STRIP_PARAM_PATTERNS)


def canonicalize_url(url: str) -> str:
    """
    Return a canonical form of *url* for deduplication purposes.

    Args:
        url: Raw URL string (may include tracking params, fragments, etc.)

    Returns:
        Canonical URL string.  Returns the original *url* unchanged if it
        cannot be parsed (e.g. empty string, non-HTTP scheme).

    Examples::
        >>> canonicalize_url("https://Reuters.COM/article/1?utm_source=tw#top")
        'https://reuters.com/article/1'

        >>> canonicalize_url("https://example.com/news/?fbclid=abc&id=42")
        'https://example.com/news?id=42'

        >>> canonicalize_url("https://example.com/news//story/")
        'https://example.com/news/story'
    """
    if not url:
        return url

    try:
        parsed = urlparse(url)
    except Exception:
        return url

    # Only canonicalize http/https URLs
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        return url

    # Lowercase host
    netloc = parsed.netloc.lower()

    # Normalize path: collapse double slashes, strip trailing slash
    path = re.sub(r"/+", "/", parsed.path)
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    # Filter + sort query params
    raw_params = parse_qsl(parsed.query, keep_blank_values=True)
    filtered_params = [
        (k, v) for k, v in raw_params if not _should_strip_param(k)
    ]
    sorted_params = sorted(filtered_params, key=lambda kv: kv[0].lower())
    query = urlencode(sorted_params)

    # Strip fragment entirely
    canonical = urlunparse((scheme, netloc, path, parsed.params, query, ""))
    return canonical

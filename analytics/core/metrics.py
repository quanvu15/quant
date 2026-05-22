"""
Prometheus metrics — P6-T5.

Exposes /metrics endpoint with:
- analytics_http_requests_total{method,path,status} (counter)
- analytics_http_request_duration_seconds{method,path} (histogram)
- analytics_http_requests_in_flight (gauge)
- analytics_news_pipeline_lag_seconds (gauge)
- analytics_agent_runs_total{persona_id,status} (counter)
- analytics_chat_tokens_total{provider,model} (counter)
- analytics_script_executions_total{script,status} (counter)
- analytics_script_execution_duration_seconds{script} (histogram)
- analytics_cache_hits_total{module} (counter)
- analytics_cache_misses_total{module} (counter)
- analytics_active_jobs (gauge)

Uses prometheus_client if available, falls back to no-op stubs.
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Any, Callable

import structlog

logger = structlog.get_logger(__name__)

# ── Try to import prometheus_client ──────────────────────────────────────────

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False
    logger.info("metrics.prometheus_not_installed", hint="pip install prometheus-client")

# ── Metric definitions ────────────────────────────────────────────────────────

if _PROMETHEUS_AVAILABLE:
    # HTTP metrics
    HTTP_REQUESTS_TOTAL = Counter(
        "analytics_http_requests_total",
        "Total HTTP requests",
        ["method", "path", "status"],
    )
    HTTP_REQUEST_DURATION = Histogram(
        "analytics_http_request_duration_seconds",
        "HTTP request duration",
        ["method", "path"],
        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
    )
    HTTP_IN_FLIGHT = Gauge(
        "analytics_http_requests_in_flight",
        "HTTP requests currently being processed",
    )

    # News pipeline metrics
    NEWS_PIPELINE_LAG = Gauge(
        "analytics_news_pipeline_lag_seconds",
        "Lag between article published_at and when it was enriched and stored (seconds)",
    )

    # Agent metrics
    AGENT_RUNS_TOTAL = Counter(
        "analytics_agent_runs_total",
        "Total agent runs",
        ["persona_id", "status"],
    )

    # Chat / LLM token metrics
    CHAT_TOKENS_TOTAL = Counter(
        "analytics_chat_tokens_total",
        "Total LLM tokens consumed",
        ["provider", "model"],
    )

    # Script execution metrics
    SCRIPT_EXECUTIONS_TOTAL = Counter(
        "analytics_script_executions_total",
        "Total Python script executions",
        ["script", "status"],
    )
    SCRIPT_DURATION = Histogram(
        "analytics_script_execution_duration_seconds",
        "Python script execution duration",
        ["script"],
        buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
    )

    # Cache metrics
    CACHE_HITS = Counter("analytics_cache_hits_total", "Redis cache hits", ["module"])
    CACHE_MISSES = Counter("analytics_cache_misses_total", "Redis cache misses", ["module"])

    # Job metrics
    ACTIVE_JOBS = Gauge("analytics_active_jobs", "Currently running async jobs")

else:
    # No-op stubs so code works without prometheus_client installed
    class _NoOp:
        def labels(self, **_): return self
        def inc(self, *_): pass
        def dec(self, *_): pass
        def observe(self, *_): pass
        def set(self, *_): pass
        def time(self): return _NoOpCtx()

    class _NoOpCtx:
        def __enter__(self): return self
        def __exit__(self, *_): pass

    _noop = _NoOp()
    HTTP_REQUESTS_TOTAL = _noop
    HTTP_REQUEST_DURATION = _noop
    HTTP_IN_FLIGHT = _noop
    NEWS_PIPELINE_LAG = _noop
    AGENT_RUNS_TOTAL = _noop
    CHAT_TOKENS_TOTAL = _noop
    SCRIPT_EXECUTIONS_TOTAL = _noop
    SCRIPT_DURATION = _noop
    CACHE_HITS = _noop
    CACHE_MISSES = _noop
    ACTIVE_JOBS = _noop


# ── Helper functions ──────────────────────────────────────────────────────────

def record_request(method: str, path: str, status: int, duration_s: float) -> None:
    """Record an HTTP request metric."""
    # Normalize path to avoid high cardinality (strip UUIDs, IDs)
    normalized = _normalize_path(path)
    HTTP_REQUESTS_TOTAL.labels(method=method, path=normalized, status=str(status)).inc()
    HTTP_REQUEST_DURATION.labels(method=method, path=normalized).observe(duration_s)


def record_script(script: str, status: str, duration_s: float) -> None:
    """Record a Python script execution metric."""
    short = script.split("/")[-1]  # just filename
    SCRIPT_EXECUTIONS_TOTAL.labels(script=short, status=status).inc()
    SCRIPT_DURATION.labels(script=short).observe(duration_s)


def record_cache_hit(module: str) -> None:
    CACHE_HITS.labels(module=module).inc()


def record_cache_miss(module: str) -> None:
    CACHE_MISSES.labels(module=module).inc()


def record_news_pipeline_lag(lag_seconds: float) -> None:
    """Record the lag between article published_at and enrichment completion."""
    NEWS_PIPELINE_LAG.set(lag_seconds)


def record_agent_run(persona_id: str, status: str) -> None:
    """Record an agent run completion.

    Args:
        persona_id: The persona/agent identifier (e.g. 'warren_buffett').
        status: One of 'ok', 'error', 'cancelled'.
    """
    AGENT_RUNS_TOTAL.labels(persona_id=persona_id, status=status).inc()


def record_chat_tokens(provider: str, model: str, tokens: int) -> None:
    """Record LLM token consumption.

    Args:
        provider: LLM provider name (e.g. 'openai', 'groq', 'ollama').
        model: Model identifier (e.g. 'gpt-4o', 'llama3-70b').
        tokens: Number of tokens to add to the counter.
    """
    CHAT_TOKENS_TOTAL.labels(provider=provider, model=model).inc(tokens)


def _normalize_path(path: str) -> str:
    """Replace path parameters with placeholders to reduce cardinality."""
    import re
    # Replace UUIDs
    path = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "{id}", path)
    # Replace numeric IDs
    path = re.sub(r"/\d+", "/{id}", path)
    # Replace ticker symbols (all-caps 1-10 chars after /equity/ or /market/)
    path = re.sub(r"/(equity|market|derivatives)/([A-Z0-9.\-^]{1,10})/", r"/\1/{symbol}/", path)
    return path


def get_metrics_response():
    """Return Prometheus metrics as bytes + content type."""
    if not _PROMETHEUS_AVAILABLE:
        return b"# prometheus_client not installed\n", "text/plain"
    return generate_latest(), CONTENT_TYPE_LATEST

# ============================================================
# Analytics Microservice — Production multi-stage Docker build
# Base: python:3.11-slim
# Service: analytics
# ============================================================

# ── Stage 1: Build dependencies ───────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies into a prefix
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt

# Install NLP dependencies (Phase 1 — news pipeline)
# These are large; install separately to leverage Docker layer cache.
RUN pip install --no-cache-dir --prefix=/install \
    feedparser==6.0.11 \
    transformers==4.44.2 \
    torch==2.4.0 \
    spacy==3.7.6 \
    && python -m spacy download en_core_web_sm --target /install/lib/python3.11/site-packages \
    || true  # spacy download may fail in build env; models downloaded at runtime

# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# System dependencies (curl for healthcheck, libpq for asyncpg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Security: run as non-root user
RUN useradd -m -u 1000 -s /bin/bash analytics

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY --chown=analytics:analytics . .

# Switch to non-root user
USER analytics

# Environment defaults (override via docker-compose or k8s)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONIOENCODING=utf-8 \
    ENV=production \
    HOST=0.0.0.0 \
    PORT=8000 \
    LOG_FORMAT=json \
    LOG_LEVEL=INFO

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run with uvicorn directly
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--log-level", "info"]

# Analytics Microservice — Deployment Guide

> **Hướng dẫn triển khai** Analytics Microservice với Docker Compose, Caddy reverse proxy, và PostgreSQL.
>
> **Deployment guide** for Analytics Microservice with Docker Compose, Caddy reverse proxy, and PostgreSQL.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Docker Compose Deployment](#docker-compose-deployment)
3. [Environment Variables](#environment-variables)
4. [Caddy Reverse Proxy](#caddy-reverse-proxy)
5. [Database Setup (Alembic Migrations)](#database-setup-alembic-migrations)
6. [Redis Configuration](#redis-configuration)
7. [Health Check Verification](#health-check-verification)
8. [Monitoring (Prometheus + Grafana)](#monitoring-prometheus--grafana)
9. [Backup & Recovery](#backup--recovery)
10. [Troubleshooting](#troubleshooting)

---

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Docker | 24+ | [Install](https://docs.docker.com/get-docker/) |
| Docker Compose | v2+ | Bundled with Docker Desktop |
| PostgreSQL | 16 | Managed by Docker Compose |
| Redis | 7.4 | Managed by Docker Compose |
| Caddy | 2.7+ | For reverse proxy (optional for local dev) |

---

## Docker Compose Deployment

### Development (local)

```bash
cd analytics

# 1. Copy and configure environment
cp .env.example .env
# Edit .env — see Environment Variables section below

# 2. Start all services
docker compose up -d

# 3. Check all containers are running
docker compose ps
```

Expected output:

```
NAME                     STATUS          PORTS
analytics-api            Up (healthy)    0.0.0.0:8000->8000/tcp
analytics-postgres       Up (healthy)    0.0.0.0:5432->5432/tcp
analytics-redis          Up (healthy)    0.0.0.0:6379->6379/tcp
analytics-news-fetcher   Up
analytics-news-nlp       Up
```

### Production

```bash
# Production uses same docker-compose.yml with production .env values
# Key differences in production .env:
#   ENV=production
#   DEBUG=false
#   LOG_FORMAT=json
#   CORS_ORIGINS=["https://your-domain.com"]
#   POSTGRES_PASSWORD=<strong-random-password>
#   JWT_SECRET_KEY=<64-char-random-string>
#   QUANTDINGER_JWT_SECRET=<must-match-flask-secret-key>

docker compose up -d
```

### With monitoring stack

```bash
# Start with Prometheus + Grafana
docker compose --profile monitoring up -d

# Access:
# Prometheus: http://localhost:9090
# Grafana:    http://localhost:3000 (admin/admin — change on first login)
```

### Useful commands

```bash
# View logs
docker compose logs -f analytics-api
docker compose logs -f analytics-news-fetcher
docker compose logs -f analytics-news-nlp

# Restart a service
docker compose restart analytics-api

# Stop all services
docker compose down

# Stop and remove volumes (WARNING: deletes all data)
docker compose down -v

# Rebuild after code changes
docker compose build analytics-api
docker compose up -d analytics-api
```

---

## Environment Variables

Copy `.env.example` to `.env` and configure. All variables with their descriptions:

### Service Identity

| Variable | Default | Description |
|----------|---------|-------------|
| `SERVICE_NAME` | `analytics` | Service name in logs and metrics |
| `VERSION` | `1.0.0` | Service version |
| `ENV` | `development` | Environment: `development` or `production` |
| `DEBUG` | `false` | Enable debug mode (never true in production) |
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8000` | HTTP port |

### CORS

| Variable | Default | Description |
|----------|---------|-------------|
| `CORS_ORIGINS` | `["*"]` | Allowed origins. In production: `["https://your-domain.com"]` |

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/quantdinger` | Full async Postgres URL |
| `DB_SCHEMA` | `analytics` | Postgres schema for all Analytics tables |
| `POSTGRES_USER` | `postgres` | Postgres superuser (for docker-compose postgres service) |
| `POSTGRES_PASSWORD` | `postgres` | **Change in production!** |
| `POSTGRES_DB` | `quantdinger` | Database name (shared with QuantDinger) |
| `POSTGRES_PORT` | `5432` | Postgres port |

### Redis

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `REDIS_MAX_CONNECTIONS` | `20` | Connection pool size |
| `REDIS_PORT` | `6379` | Redis port (for docker-compose) |
| `REDIS_KEY_PREFIX` | `analytics:` | Prefix for all Redis keys — prevents collision with QuantDinger (`qd:`) |

### Authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_SECRET_KEY` | `change-me-in-production` | **CHANGE THIS!** Analytics-native JWT secret |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `JWT_EXPIRE_MINUTES` | `1440` | JWT expiry (24 hours) |
| `MASTER_API_KEY` | _(empty)_ | Admin API key for dev/testing. Leave empty in production |
| `QUANTDINGER_JWT_SECRET` | _(empty)_ | **Must match QuantDinger Flask `SECRET_KEY`** — enables JWT bridge |
| `QUANTDINGER_JWT_ALGORITHM` | `HS256` | Must match QuantDinger JWT algorithm |

### Rate Limiting

| Variable | Default | Description |
|----------|---------|-------------|
| `RATE_LIMIT_FREE` | `60` | Requests per minute for default tier |
| `RATE_LIMIT_PAID` | `600` | Requests per minute for paid tier |

### Python Runner (Scripts)

| Variable | Default | Description |
|----------|---------|-------------|
| `SCRIPTS_DIR` | _(auto-detect)_ | Path to `fincept-qt/scripts/`. Auto-detected if empty |
| `VENV_NUMPY2_PYTHON` | _(auto-detect)_ | Python interpreter with full deps (numpy, pandas, agno…) |
| `MAX_CONCURRENT_PROCESSES` | `5` | Max parallel Python subprocesses |
| `DEFAULT_TIMEOUT` | `60` | Default subprocess timeout (seconds) |

### Agent Timeouts

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_RUN_TIMEOUT` | `120` | Single agent run timeout (seconds) |
| `AGENT_PLAN_TIMEOUT` | `300` | Execution planner timeout (seconds) |
| `MAX_CONCURRENT_AGENT_RUNS` | `10` | Max parallel agent runs |

### News Pipeline

| Variable | Default | Description |
|----------|---------|-------------|
| `NEWS_FETCH_INTERVAL` | `30` | RSS fetch cycle interval (seconds) |
| `NEWS_SOURCE_ERROR_THRESHOLD` | `5` | Consecutive errors before auto-disabling a source |
| `NEWS_FETCH_TIMEOUT` | `10` | Per-source fetch timeout (seconds) |
| `AUDIT_LOG_RETENTION_DAYS` | `90` | Audit log retention period |

### External API Keys

These are injected into Python subprocess environments. All optional — endpoints that need them will return `MISSING_API_KEY` if not set.

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key |
| `ANTHROPIC_API_KEY` | Anthropic Claude API key |
| `GOOGLE_API_KEY` | Google AI API key |
| `POLYGON_API_KEY` | Polygon.io market data |
| `FINNHUB_API_KEY` | Finnhub market data (free tier available) |
| `ALPHA_VANTAGE_API_KEY` | Alpha Vantage market data |
| `FRED_API_KEY` | FRED economic data (free, register at [fred.stlouisfed.org](https://fred.stlouisfed.org)) |
| `MARINETRAFFIC_API_KEY` | Maritime vessel tracking |
| `ACLED_API_KEY` | Geopolitics events data |

### LLM Defaults

Server-side defaults used when client does not pass `llm_config`:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible provider URL |
| `LLM_MODEL` | `gpt-4o-mini` | Default model |
| `LLM_API_KEY` | _(empty)_ | Default API key |

### Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOG_FORMAT` | `console` | Log format: `console` (dev) or `json` (production) |

---

## Caddy Reverse Proxy

Add the following to your QuantDinger `Caddyfile` to route `/analytics/*` to the Analytics service.

### Caddyfile configuration

```caddy
your-domain.com {
    # ── QuantDinger Vue UI ────────────────────────────────────────────────────
    handle / {
        reverse_proxy quantdinger-vue:8888
    }

    # ── QuantDinger Flask API ─────────────────────────────────────────────────
    handle /api/* {
        reverse_proxy quantdinger-flask:5000
    }

    # ── Analytics REST API ────────────────────────────────────────────────────
    handle /analytics/api/* {
        reverse_proxy analytics-api:8000 {
            # Disable response buffering for SSE streaming
            flush_interval -1
        }
    }

    # ── Analytics WebSocket ───────────────────────────────────────────────────
    # WebSocket requires HTTP/1.1 transport (not HTTP/2)
    handle /analytics/ws/* {
        reverse_proxy analytics-api:8000 {
            transport http {
                versions h1 h1c
            }
        }
    }

    # ── Analytics Swagger UI (docs) ───────────────────────────────────────────
    handle /analytics/docs* {
        reverse_proxy analytics-api:8000
    }

    handle /analytics/openapi.json {
        reverse_proxy analytics-api:8000
    }

    handle /analytics/redoc* {
        reverse_proxy analytics-api:8000
    }
}
```

> **Important:** The `flush_interval -1` directive disables response buffering, which is required for SSE (Server-Sent Events) streaming to work correctly. Without it, tokens will be buffered and not delivered in real-time.

### Verify Caddy routing

```bash
# Health check through Caddy
curl https://your-domain.com/analytics/api/v1/health
# → {"status":"ok","service":"analytics","redis":"ok"}

# Swagger UI
open https://your-domain.com/analytics/docs

# WebSocket test (requires wscat: npm install -g wscat)
wscat -c "wss://your-domain.com/analytics/ws/news"
```

### Path rewriting

The Analytics FastAPI app is mounted at the root (`/`), but Caddy routes `/analytics/*` to it. The app handles this transparently — no path rewriting needed in Caddy.

If you need to strip the `/analytics` prefix, add to Caddyfile:

```caddy
handle /analytics/* {
    uri strip_prefix /analytics
    reverse_proxy analytics-api:8000
}
```

---

## Database Setup (Alembic Migrations)

Analytics uses its own Alembic migrations to manage the `analytics.*` schema in the shared QuantDinger Postgres database.

### Run migrations

```bash
# Option 1: Run via Docker (recommended for production)
docker compose exec analytics-api alembic upgrade head

# Option 2: Run locally (requires DATABASE_URL in .env)
cd analytics
alembic upgrade head
```

### Migration files

| Migration | Description |
|-----------|-------------|
| `001_init_analytics_schema.py` | Creates `analytics` schema + 6 tables: `news_sources`, `news_articles`, `chat_sessions`, `chat_messages`, `agent_runs`, `audit_log` |
| `002_news_sources_seed.py` | Seeds 20 RSS news sources (Reuters, Bloomberg, FT, Yahoo Finance, etc.) |

### Schema overview

```sql
analytics.news_sources      -- RSS feed sources (20 seeded)
analytics.news_articles     -- Enriched articles (sentiment, tickers, entities)
analytics.chat_sessions     -- Chat session metadata
analytics.chat_messages     -- Chat message history with token counts
analytics.agent_runs        -- Agent run audit log
analytics.audit_log         -- General audit trail (all POST/DELETE)
```

### Postgres role setup (production)

For production, create a dedicated Postgres role with minimal permissions:

```sql
-- Run as postgres superuser
CREATE ROLE analytics_app WITH LOGIN PASSWORD 'strong-password-here';
GRANT CONNECT ON DATABASE quantdinger TO analytics_app;
GRANT USAGE ON SCHEMA analytics TO analytics_app;
GRANT ALL ON ALL TABLES IN SCHEMA analytics TO analytics_app;
GRANT ALL ON ALL SEQUENCES IN SCHEMA analytics TO analytics_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA analytics
    GRANT ALL ON TABLES TO analytics_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA analytics
    GRANT ALL ON SEQUENCES TO analytics_app;

-- Verify: analytics_app cannot access public schema
-- REVOKE ALL ON SCHEMA public FROM analytics_app;  -- if needed
```

Then update `DATABASE_URL` in `.env`:

```env
DATABASE_URL=postgresql+asyncpg://analytics_app:strong-password-here@postgres:5432/quantdinger
```

### Check migration status

```bash
docker compose exec analytics-api alembic current
docker compose exec analytics-api alembic history
```

### Rollback

```bash
# Rollback one migration
docker compose exec analytics-api alembic downgrade -1

# Rollback to specific revision
docker compose exec analytics-api alembic downgrade 001
```

---

## Redis Configuration

Redis is used for:
- **Cache** — API response caching with TTL (`analytics:cache:*`)
- **Rate limiting** — per-user request counters (`analytics:rate:*`)
- **News pipeline** — Redis Stream queue (`analytics:news:queue`)
- **WebSocket fanout** — pubsub channels (`analytics:news:pubsub:*`)

### Docker Compose Redis settings

The included `docker-compose.yml` configures Redis with:

```yaml
command: >
  redis-server
  --maxmemory 512mb
  --maxmemory-policy allkeys-lru
  --save 60 1
  --loglevel warning
```

| Setting | Value | Description |
|---------|-------|-------------|
| `maxmemory` | `512mb` | Max memory before eviction |
| `maxmemory-policy` | `allkeys-lru` | Evict least-recently-used keys when full |
| `save 60 1` | — | Persist to disk every 60s if ≥1 key changed |

### Production Redis tuning

For production with high traffic, increase memory and add persistence:

```bash
# In docker-compose.yml or redis.conf:
--maxmemory 2gb
--maxmemory-policy allkeys-lru
--save 300 10
--appendonly yes
--appendfsync everysec
```

### Redis key namespace

All Analytics keys use the `analytics:` prefix (configurable via `REDIS_KEY_PREFIX`):

```
analytics:cache:market:quote:AAPL     ← Market data cache (TTL 5s)
analytics:cache:agents:list           ← Agent list cache (TTL 300s)
analytics:rate:user:<user_id>         ← Rate limit counter
analytics:news:queue                  ← Redis Stream (news pipeline)
analytics:news:pubsub:AAPL            ← WebSocket fanout channel
analytics:auth:user:<user_id>         ← User lookup cache (TTL 300s)
```

QuantDinger uses `qd:*` prefix — no collision possible.

### Verify Redis connection

```bash
# Check Redis is running
docker compose exec redis redis-cli ping
# → PONG

# Check Analytics keys
docker compose exec redis redis-cli keys "analytics:*"

# Monitor real-time commands
docker compose exec redis redis-cli monitor
```

---

## Health Check Verification

### Service health

```bash
# Analytics API health
curl http://localhost:8000/health
# → {"status":"ok","service":"analytics","version":"1.0.0","env":"development","redis":"ok"}

# Through Caddy (production)
curl https://your-domain.com/analytics/api/v1/health
```

### Docker health checks

All services have Docker health checks configured:

```bash
# Check health status of all containers
docker compose ps

# Detailed health check output
docker inspect analytics-api --format='{{json .State.Health}}'
```

### Verify all components

```bash
# 1. API responds
curl -s http://localhost:8000/health | python -m json.tool

# 2. Postgres connection
docker compose exec analytics-api python -c "
import asyncio
from core.database import engine
async def check():
    async with engine.connect() as conn:
        result = await conn.execute(text('SELECT 1'))
        print('Postgres: OK')
asyncio.run(check())
"

# 3. Redis connection
docker compose exec redis redis-cli ping

# 4. News workers running
docker compose ps analytics-news-fetcher analytics-news-nlp

# 5. Migrations applied
docker compose exec analytics-api alembic current

# 6. Swagger UI accessible
curl -s http://localhost:8000/docs | grep -c "swagger"
```

### Smoke test after deployment

```bash
TOKEN="your-quantdinger-jwt-here"

# Health
curl -s http://localhost:8000/health

# Auth works
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/agents/ | python -m json.tool

# News list (requires DB + migrations)
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/news?limit=5" | python -m json.tool

# Market quote
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/market/quote/AAPL | python -m json.tool
```

---

## Monitoring (Prometheus + Grafana)

### Start monitoring stack

```bash
docker compose --profile monitoring up -d
```

### Access

| Service | URL | Credentials |
|---------|-----|-------------|
| Prometheus | http://localhost:9090 | — |
| Grafana | http://localhost:3000 | admin / admin |

### Key metrics

| Metric | Description |
|--------|-------------|
| `analytics_http_requests_total{method,path,status}` | Request count by endpoint |
| `analytics_http_request_duration_seconds{method,path}` | Request latency histogram |
| `analytics_news_pipeline_lag_seconds` | News pipeline processing lag |
| `analytics_agent_runs_total{persona_id,status}` | Agent run count |
| `analytics_chat_tokens_total{provider,model}` | LLM token usage |
| `analytics_cache_hits_total{module}` | Cache hit rate |
| `analytics_active_jobs` | Active async jobs |

### Prometheus scrape config

The `deploy/prometheus.yml` is pre-configured to scrape the Analytics API:

```yaml
scrape_configs:
  - job_name: analytics
    static_configs:
      - targets: ['analytics-api:8000']
    metrics_path: /metrics
    scrape_interval: 15s
```

---

## Backup & Recovery

### Automated backup

```bash
# Run backup script (backs up analytics.* schema only)
bash analytics/scripts/backup.sh

# Schedule daily at 2am (add to crontab)
0 2 * * * /path/to/analytics/scripts/backup.sh >> /var/log/analytics-backup.log 2>&1
```

### Manual backup

```bash
# Backup analytics schema only
docker compose exec postgres pg_dump \
  -U postgres \
  -d quantdinger \
  -n analytics \
  --no-owner \
  --no-acl \
  -Fc \
  -f /tmp/analytics_backup_$(date +%Y%m%d_%H%M%S).dump

# Copy backup out of container
docker cp analytics-postgres:/tmp/analytics_backup_*.dump ./backups/
```

### Restore

```bash
# Restore from backup
docker compose exec -T postgres pg_restore \
  -U postgres \
  -d quantdinger \
  -n analytics \
  --no-owner \
  --clean \
  -Fc \
  < ./backups/analytics_backup_20241101_020000.dump
```

### Backup checklist

- [ ] Backup runs daily at 2am
- [ ] Backup files stored outside Docker volumes
- [ ] Retention policy: keep 30 days of daily backups
- [ ] Test restore drill completed (at least once before production)
- [ ] Backup size monitored (alert if > 10GB)

---

## Troubleshooting

### Container won't start

```bash
# Check logs
docker compose logs analytics-api --tail=50

# Common causes:
# 1. Postgres not ready yet → wait for health check
# 2. Missing env vars → check .env file
# 3. Port conflict → change PORT in .env
```

### Redis connection failed

```bash
# Check Redis is running
docker compose ps redis

# Test connection
docker compose exec redis redis-cli ping

# Check REDIS_URL in .env matches docker-compose service name
# In docker-compose: REDIS_URL=redis://redis:6379/0  (service name = "redis")
# Local dev:         REDIS_URL=redis://localhost:6379/0
```

### Migrations failed

```bash
# Check migration status
docker compose exec analytics-api alembic current

# Check Postgres connection
docker compose exec analytics-api python -c "
import os; print(os.environ.get('DATABASE_URL', 'NOT SET'))
"

# Run migrations manually with verbose output
docker compose exec analytics-api alembic upgrade head --sql
```

### News workers not fetching

```bash
# Check worker logs
docker compose logs analytics-news-fetcher --tail=50
docker compose logs analytics-news-nlp --tail=50

# Check Redis Stream
docker compose exec redis redis-cli xlen analytics:news:queue

# Check news sources in DB
docker compose exec analytics-api python -c "
import asyncio
from core.database import AsyncSessionLocal
from sqlalchemy import text
async def check():
    async with AsyncSessionLocal() as db:
        result = await db.execute(text('SELECT count(*) FROM analytics.news_sources WHERE enabled=true'))
        print('Active sources:', result.scalar())
asyncio.run(check())
"
```

### SSE/WebSocket not streaming through Caddy

Ensure Caddy config has:
- `flush_interval -1` for SSE endpoints
- `transport http { versions h1 h1c }` for WebSocket endpoints

See [Caddy Reverse Proxy](#caddy-reverse-proxy) section above.

### JWT authentication failing

```bash
# Verify QUANTDINGER_JWT_SECRET matches Flask SECRET_KEY
# In analytics .env:
echo $QUANTDINGER_JWT_SECRET

# Test JWT decode manually
python -c "
from jose import jwt
token = 'your-jwt-here'
secret = 'your-secret-here'
claims = jwt.decode(token, secret, algorithms=['HS256'])
print(claims)
"
```

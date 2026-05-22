# Analytics Microservice

> **Analytics** — microservice tích hợp vào QuantDinger, cung cấp News pipeline, Chatbot, AI Agents và Stock Analytics.
>
> **Analytics** — microservice integrated into QuantDinger, providing News pipeline, Chatbot, AI Agents, and Stock Analytics.

[![Tests](https://img.shields.io/badge/tests-130%20passed-brightgreen)](tests/)
[![Python](https://img.shields.io/badge/python-3.12-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.136-009688)](https://fastapi.tiangolo.com)

| Module | Base Path | Status |
|--------|-----------|--------|
| News | `/api/v1/news` + `WS /ws/news` | ✅ Live |
| Chat | `/api/v1/chat` | 🔄 Phase 2 |
| AI Agents | `/api/v1/agents` | ✅ Live |
| Analytics | `/api/v1/market`, `/api/v1/equity`, `/api/v1/portfolio` | ✅ Live |

---

## ⚡ Quick Start (< 10 phút / < 10 minutes)

### Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Docker | 24+ | [docker.com](https://docs.docker.com/get-docker/) |
| Docker Compose | v2+ | bundled with Docker Desktop |
| Git | any | [git-scm.com](https://git-scm.com) |

> Python 3.12 is only needed if you run the service **without** Docker.

---

### Step 1 — Clone & enter directory

```bash
git clone https://github.com/QuantDinger/FinceptTerminal.git
cd FinceptTerminal/analytics
```

---

### Step 2 — Configure environment

```bash
cp .env.example .env
```

Open `.env` and fill in the **minimum required** values:

```env
# QuantDinger JWT bridge — must match Flask SECRET_KEY
QUANTDINGER_JWT_SECRET=change-me-in-production

# LLM provider (choose one — Groq is free and fast)
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=llama-3.1-70b-versatile
LLM_API_KEY=gsk_your_groq_key_here
```

> **Groq free tier:** Sign up at [console.groq.com](https://console.groq.com) — no credit card needed.
> Other providers: OpenAI, Ollama (local), DeepSeek, Anthropic — see `.env.example` for examples.

---

### Step 3 — Start all services

```bash
docker compose up -d
```

This starts: **analytics-api** (port 8000) + **PostgreSQL 16** + **Redis 7** + **news workers**.

Wait ~15 seconds for startup, then verify:

```bash
curl http://localhost:8000/health
# → {"status":"ok","service":"analytics","redis":"ok"}
```

---

### Step 4 — Open Swagger UI

Navigate to **http://localhost:8000/docs** — interactive API documentation.

When deployed behind Caddy/Nginx: **https://your-domain/analytics/api/v1/docs**

---

### Step 5 — Make your first API call

```bash
# Get a real-time stock quote (no auth needed for health/docs)
curl -H "Authorization: Bearer YOUR_QD_JWT" \
     http://localhost:8000/api/v1/market/quote/AAPL

# Run an AI agent
curl -X POST http://localhost:8000/api/v1/agents/run \
  -H "Authorization: Bearer YOUR_QD_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Analyze AAPL — buy or sell?",
    "llm_config": {
      "model": "llama-3.1-70b-versatile",
      "api_key": "gsk_...",
      "base_url": "https://api.groq.com/openai/v1"
    }
  }'
```

✅ **Done!** Total time from `git clone` to running: **< 5 minutes** with Docker.

---

## Architecture Overview

```
QuantDinger Vue UI
       │
       ▼
  Caddy Proxy
  ├── /api/*          → QuantDinger Flask (port 5000)
  └── /analytics/*    → Analytics FastAPI (port 8000)
                              │
                    ┌─────────┼──────────┐
                    ▼         ▼          ▼
               Postgres    Redis     Python scripts
               (schema:   (prefix:   (fincept-qt/scripts/)
               analytics) analytics:)
```

**4 modules:**
- **News** — RSS fetcher → Redis Stream → NLP (FinBERT + spaCy) → Postgres → WebSocket fanout
- **Chat** — OpenAI-compatible proxy with session persistence (Phase 2)
- **Agents** — 37+ AI personas (Buffett, Lynch, Munger…), SSE streaming
- **Analytics** — Market data, DCF, portfolio optimization, technical indicators

---

## Authentication

All endpoints (except `/health`, `/metrics`, `/docs`) require a **QuantDinger JWT**:

```bash
# Token issued by QuantDinger Flask login
curl -H "Authorization: Bearer <jwt>" http://localhost:8000/api/v1/agents/
```

The JWT is verified using the shared `QUANTDINGER_JWT_SECRET` (HS256). No separate login needed.

---

## API Docs

| URL | Description |
|-----|-------------|
| `http://localhost:8000/docs` | Swagger UI (interactive) |
| `http://localhost:8000/redoc` | ReDoc (readable) |
| `http://localhost:8000/openapi.json` | OpenAPI 3.0 schema |
| `http://localhost:8000/metrics` | Prometheus metrics |

---

## Detailed Documentation

| Document | Description |
|----------|-------------|
| [API Guide](docs/api-guide.md) | All 4 modules, endpoints, curl examples, WebSocket & SSE |
| [Deployment Guide](docs/deployment.md) | Docker Compose, Caddy, env vars, migrations, backup |
| [SETUP.md](SETUP.md) | Local dev setup without Docker |

---

## Development

```bash
# Run tests (requires venv-numpy2)
& "g:\Code\AI-APP\FinceptTerminal\fincept-qt\venv-numpy2\Scripts\python.exe" -m pytest tests/ -v

# Lint
ruff check .

# Format
ruff format .

# With monitoring stack (Prometheus + Grafana)
docker compose --profile monitoring up -d
# Prometheus: http://localhost:9090
# Grafana:    http://localhost:3000 (admin/admin)
```

---

## Environment Variables

See [`.env.example`](.env.example) for all options. Key variables:

```env
QUANTDINGER_JWT_SECRET=   # Must match QuantDinger Flask SECRET_KEY
DATABASE_URL=             # Postgres connection string
REDIS_URL=                # Redis connection string
LLM_BASE_URL=             # OpenAI-compatible provider URL
LLM_API_KEY=              # Provider API key
```

Full reference: [Deployment Guide → Environment Variables](docs/deployment.md#environment-variables)

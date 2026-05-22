# Analytics Module — QuantDinger Documentation

> **Analytics** là microservice tích hợp vào QuantDinger, cung cấp 4 capability: News, Chat, AI Agents, và Stock Analytics.
>
> **Analytics** is a microservice integrated into QuantDinger, providing 4 capabilities: News, Chat, AI Agents, and Stock Analytics.

## Documents

| Document | Description |
|----------|-------------|
| [API Guide](api-guide.md) | Complete API reference — all endpoints, authentication, WebSocket, SSE |
| [Deployment Guide](deployment.md) | Docker Compose, Caddy, env vars, migrations, backup |

## Quick Links

- **Swagger UI:** `https://your-domain/analytics/docs`
- **Health check:** `GET /analytics/api/v1/health`
- **Source code:** [`analytics/`](../../analytics/)
- **Quick start:** [`analytics/README.md`](../../analytics/README.md)

## Architecture

```
QuantDinger Vue UI  →  Caddy  →  Analytics FastAPI (port 8000)
                                        │
                              ┌─────────┼──────────┐
                              ▼         ▼          ▼
                         Postgres    Redis     Python scripts
                         (schema:   (prefix:   (fincept-qt/scripts/)
                         analytics) analytics:)
```

## Modules

| Module | Routes | Description |
|--------|--------|-------------|
| **News** | `/analytics/api/v1/news`, `WS /analytics/ws/news` | RSS pipeline + NLP enrichment + realtime WebSocket |
| **Chat** | `/analytics/api/v1/chat` | OpenAI-compatible chat with session persistence |
| **AI Agents** | `/analytics/api/v1/agents` | 37+ AI personas, SSE streaming, multi-agent teams |
| **Analytics** | `/analytics/api/v1/market`, `/equity`, `/portfolio`, `/technical` | Market data, DCF, portfolio optimization |

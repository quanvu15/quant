# Analytics API Guide

> **Phiên bản / Version:** 1.0 — Analytics Microservice for QuantDinger
>
> Base URL (local): `http://localhost:8000`
> Base URL (via Caddy): `https://your-domain/analytics`

---

## Table of Contents

1. [Authentication](#authentication)
2. [Module 1 — News](#module-1--news)
3. [Module 2 — Chat](#module-2--chat)
4. [Module 3 — AI Agents](#module-3--ai-agents)
5. [Module 4 — Analytics](#module-4--analytics)
6. [WebSocket — News Realtime](#websocket--news-realtime)
7. [SSE Streaming — Chat & Agents](#sse-streaming--chat--agents)
8. [Error Reference](#error-reference)

---

## Authentication

### JWT Bearer (QuantDinger integration)

All endpoints except `/health`, `/metrics`, and `/docs` require a JWT issued by QuantDinger Flask.

```bash
# Login to QuantDinger first
TOKEN=$(curl -s -X POST https://your-domain/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"..."}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['token'])")

# Use the token for Analytics API calls
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/v1/agents/
```

The JWT is verified using the shared `QUANTDINGER_JWT_SECRET` (HS256 algorithm). No separate login needed — same token works for both QuantDinger and Analytics.

### JWT payload expected

```json
{
  "sub": "user-uuid",
  "email": "user@example.com",
  "role": "user",
  "exp": 1234567890
}
```

### Error responses

| Condition | HTTP | Code |
|-----------|------|------|
| Missing token | 401 | `AUTH_REQUIRED` |
| Invalid/expired token | 401 | `AUTH_REQUIRED` |
| Insufficient role | 403 | `FORBIDDEN` |

---

## Module 1 — News

> **Mô tả:** Pipeline tin tức tự host từ ~20 nguồn RSS tài chính. Bài viết được làm giàu với sentiment (FinBERT) và entity recognition (spaCy).
>
> **Description:** Self-hosted news pipeline from ~20 financial RSS sources. Articles are enriched with sentiment (FinBERT) and entity recognition (spaCy).

### Base path: `/api/v1/news`

---

### GET /api/v1/news — List articles

List news articles with optional filters and cursor-based pagination.

**Query parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `ticker` | string | Filter by ticker symbol (e.g. `AAPL`) |
| `source` | string | Source name partial match |
| `sentiment_min` | float [-1, 1] | Minimum sentiment score |
| `sentiment_max` | float [-1, 1] | Maximum sentiment score |
| `from` | ISO datetime | Published after this date |
| `to` | ISO datetime | Published before this date |
| `language` | string | Language code (e.g. `en`) |
| `limit` | int [1-100] | Number of results (default: 20) |
| `cursor` | string | `published_at` of last item for next page |

**Example:**

```bash
# Latest 10 articles about AAPL with positive sentiment
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/news?ticker=AAPL&sentiment_min=0.2&limit=10"
```

**Response:**

```json
{
  "articles": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "source_name": "Reuters Business",
      "url": "https://reuters.com/...",
      "title": "Apple reports record Q4 earnings",
      "summary": "Apple Inc. reported...",
      "published_at": "2024-11-01T18:30:00Z",
      "fetched_at": "2024-11-01T18:31:05Z",
      "tickers": ["AAPL"],
      "entities": [{"text": "Apple Inc.", "label": "ORG"}],
      "sentiment": 0.82,
      "language": "en"
    }
  ],
  "total": 142,
  "cursor": "2024-11-01T18:30:00Z"
}
```

**Pagination:**

```bash
# Get next page using cursor from previous response
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/news?ticker=AAPL&cursor=2024-11-01T18:30:00Z"
```

---

### GET /api/v1/news/search — Full-text search

Postgres full-text search over article title and summary.

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/news/search?q=federal+reserve+interest+rates&limit=20"
```

**Response:**

```json
{
  "articles": [...],
  "total": 37,
  "query": "federal reserve interest rates"
}
```

---

### GET /api/v1/news/{id} — Get article by ID

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/news/550e8400-e29b-41d4-a716-446655440000"
```

---

### Sentiment scores

| Range | Meaning |
|-------|---------|
| `0.5` to `1.0` | Positive / Bullish |
| `-0.2` to `0.2` | Neutral |
| `-1.0` to `-0.5` | Negative / Bearish |

---

## Module 2 — Chat

> **Mô tả:** Chat OpenAI-compatible với streaming SSE và session persistence. Hỗ trợ 9+ LLM providers.
>
> **Description:** OpenAI-compatible chat with SSE streaming and session persistence. Supports 9+ LLM providers.
>
> ⚠️ **Phase 2** — Full implementation coming. Current endpoints return stubs.

### Base path: `/api/v1/chat`

---

### POST /api/v1/chat/completions — Chat completions

OpenAI-compatible completions endpoint. Supports streaming SSE.

```bash
# Non-streaming
curl -X POST http://localhost:8000/api/v1/chat/completions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [
      {"role": "system", "content": "You are a financial analyst."},
      {"role": "user", "content": "What is the P/E ratio of AAPL?"}
    ],
    "llm_config": {
      "model": "gpt-4o-mini",
      "api_key": "sk-...",
      "base_url": "https://api.openai.com/v1"
    }
  }'
```

```bash
# Streaming SSE
curl -X POST http://localhost:8000/api/v1/chat/completions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "model": "llama-3.1-70b-versatile",
    "messages": [{"role": "user", "content": "Explain DCF valuation"}],
    "stream": true,
    "llm_config": {
      "model": "llama-3.1-70b-versatile",
      "api_key": "gsk_...",
      "base_url": "https://api.groq.com/openai/v1"
    }
  }'
# → data: {"choices":[{"delta":{"content":"DCF..."}}]}
# → data: [DONE]
```

---

### Session management

```bash
# Create session
curl -X POST http://localhost:8000/api/v1/chat/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "AAPL Analysis", "preset_id": "stock_analysis"}'

# List sessions (only yours)
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/chat/sessions

# Get session with messages
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/chat/sessions/SESSION_ID

# Delete session (cascade deletes messages)
curl -X DELETE -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/chat/sessions/SESSION_ID
```

---

### GET /api/v1/chat/presets — System prompt presets

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/chat/presets
```

Available presets: `stock_analysis`, `macro_outlook`, `options_strategy`, `portfolio_review`, `news_summary`

---

### Supported LLM providers

| Provider | `base_url` | Example model |
|----------|-----------|---------------|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o`, `gpt-4o-mini` |
| Groq (free) | `https://api.groq.com/openai/v1` | `llama-3.1-70b-versatile` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| Anthropic | `https://api.anthropic.com` | `claude-3-5-sonnet-20241022` |
| Together | `https://api.together.xyz/v1` | `meta-llama/Llama-3-70b-chat-hf` |
| Ollama (local) | `http://localhost:11434/v1` | `llama3.2` |
| LM Studio (local) | `http://localhost:1234/v1` | `local-model` |
| OpenRouter | `https://openrouter.ai/api/v1` | `anthropic/claude-3.5-sonnet` |
| Mistral | `https://api.mistral.ai/v1` | `mistral-large-latest` |

---

## Module 3 — AI Agents

> **Mô tả:** 37+ AI personas (Warren Buffett, Peter Lynch, Charlie Munger…). Hỗ trợ single agent, multi-agent team, execution planner.
>
> **Description:** 37+ AI personas. Supports single agent, multi-agent team, and execution planner.

### Base path: `/api/v1/agents`

---

### GET /api/v1/agents/ — List personas

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/agents/

# Filter by category
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/agents/?category=trader"
```

**Response:**

```json
{
  "agents": [
    {
      "id": "warren_buffett",
      "name": "Warren Buffett",
      "category": "value_investor",
      "description": "Value investing analysis using Buffett's principles",
      "capabilities": ["stock_analysis", "portfolio_review"]
    }
  ],
  "total": 37
}
```

---

### POST /api/v1/agents/run — Single agent run (one-shot)

```bash
curl -X POST http://localhost:8000/api/v1/agents/run \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Analyze NVDA — is it overvalued?",
    "llm_config": {
      "model": "llama-3.1-70b-versatile",
      "api_key": "gsk_...",
      "base_url": "https://api.groq.com/openai/v1"
    }
  }'
```

---

### POST /api/v1/agents/run/stream — Streaming agent run (SSE)

```bash
curl -X POST http://localhost:8000/api/v1/agents/run/stream \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "query": "What is the macro outlook for 2025?",
    "llm_config": {
      "model": "gpt-4o-mini",
      "api_key": "sk-...",
      "base_url": "https://api.openai.com/v1"
    }
  }'
```

**SSE event types:**

| Event type | Description |
|------------|-------------|
| `thinking` | Agent reasoning step (italic in UI) |
| `token` | Response token stream |
| `tool` | Tool call being executed |
| `tool_result` | Tool call result |
| `done` | Run completed |
| `error` | Error occurred |

**Example SSE stream:**

```
data: {"type": "thinking", "content": "Analyzing macro indicators..."}

data: {"type": "token", "content": "The current macro environment shows..."}

data: {"type": "tool", "content": "fetch_fred_data(series=GDP)"}

data: {"type": "tool_result", "content": "{\"value\": 27.36, \"unit\": \"trillion\"}"}

data: {"type": "token", "content": "GDP growth of 2.8% suggests..."}

data: {"type": "done", "content": "completed"}
```

---

### POST /api/v1/agents/analyze/stock — Stock analysis agent

```bash
curl -X POST http://localhost:8000/api/v1/agents/analyze/stock \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "AAPL",
    "llm_config": {
      "model": "llama-3.1-70b-versatile",
      "api_key": "gsk_...",
      "base_url": "https://api.groq.com/openai/v1"
    }
  }'
```

---

### POST /api/v1/agents/team/run — Multi-agent team

```bash
curl -X POST http://localhost:8000/api/v1/agents/team/run \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "team": [
      {"agent_id": "warren_buffett"},
      {"agent_id": "peter_lynch"},
      {"agent_id": "ray_dalio"}
    ],
    "query": "Should I buy TSLA?",
    "mode": "collaborate",
    "llm_config": {"model": "gpt-4o-mini", "api_key": "sk-...", "base_url": "https://api.openai.com/v1"}
  }'
```

---

### GET /api/v1/agents/runs — Agent run history

```bash
# Your run history
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/agents/runs?from=2024-01-01&limit=20"
```

---

## Module 4 — Analytics

> **Mô tả:** Market data, equity research, portfolio analytics, technical indicators.
>
> **Description:** Market data, equity research, portfolio analytics, technical indicators.

### Market Data

```bash
# Real-time quote (cache TTL 5s)
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/market/quote/AAPL

# Historical OHLCV
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/market/history/AAPL?start=2024-01-01&interval=1d"

# Batch quotes (up to 50 symbols)
curl -X POST http://localhost:8000/api/v1/market/quotes/batch \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["AAPL", "MSFT", "GOOGL", "NVDA", "TSLA"]}'
```

---

### Equity Research

```bash
# Company info (sector, market cap, P/E, ROE)
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/equity/AAPL/info

# Financial statements (IS/BS/CF)
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/equity/AAPL/financials

# DCF valuation
curl -X POST http://localhost:8000/api/v1/equity/AAPL/dcf \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "terminal_growth": 0.025,
    "projection_years": 5,
    "discount_rate": 0.10
  }'
```

---

### Portfolio Analytics

```bash
# Portfolio optimization (mean-variance)
curl -X POST http://localhost:8000/api/v1/portfolio/optimize \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "symbols": ["AAPL", "MSFT", "GOOGL"],
    "method": "mean_variance",
    "target_return": 0.15
  }'

# Portfolio metrics (Sharpe, Sortino, Max DD)
curl -X POST http://localhost:8000/api/v1/portfolio/metrics \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "holdings": [
      {"symbol": "AAPL", "weight": 0.4},
      {"symbol": "MSFT", "weight": 0.6}
    ],
    "start_date": "2023-01-01"
  }'

# Value at Risk
curl -X POST http://localhost:8000/api/v1/portfolio/var \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "returns": [-0.01, 0.02, -0.03, 0.01, 0.005],
    "confidence_level": 0.95,
    "method": "historical"
  }'
```

---

### Technical Indicators

```bash
# Calculate indicators
curl -X POST http://localhost:8000/api/v1/technical/indicators \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "AAPL",
    "indicators": ["RSI", "MACD", "BB"],
    "period": 14,
    "interval": "1d"
  }'

# Trading signals
curl -X POST http://localhost:8000/api/v1/technical/signals \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL", "interval": "1d"}'
```

---

## WebSocket — News Realtime

> **Mô tả:** Nhận bài viết mới ngay khi NLP pipeline xử lý xong. Hỗ trợ filter theo ticker và backfill khi reconnect.
>
> **Description:** Receive new articles as soon as the NLP pipeline processes them. Supports ticker filtering and backfill on reconnect.

### Connect

```
WS ws://localhost:8000/ws/news
WS ws://localhost:8000/ws/news?ticker=AAPL
WS ws://localhost:8000/ws/news?ticker=AAPL&since=2024-11-01T00:00:00Z
```

**Query parameters:**

| Parameter | Description |
|-----------|-------------|
| `ticker` | Filter to articles mentioning this ticker |
| `since` | ISO timestamp — backfill articles published after this time on connect |

### JavaScript example

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/news?ticker=AAPL');

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);

  if (msg.type === 'article_new') {
    console.log('New article:', msg.data.title, 'Sentiment:', msg.data.sentiment);
  } else if (msg.type === 'article_backfill') {
    console.log('Backfill:', msg.data.title);
  } else if (msg.type === 'ping') {
    ws.send(JSON.stringify({ type: 'pong' }));
  }
};

ws.onclose = () => {
  // Auto-reconnect after 3 seconds
  setTimeout(() => reconnect(), 3000);
};
```

### Server events

| Event type | Description |
|------------|-------------|
| `article_new` | New article from NLP pipeline |
| `article_backfill` | Historical article sent on reconnect (with `?since=`) |
| `ping` | Heartbeat every 30 seconds — respond with `{"type":"pong"}` |
| `error` | Server-side error |

### Event payload

```json
{
  "type": "article_new",
  "data": {
    "id": "550e8400-...",
    "title": "Fed raises rates by 25bps",
    "summary": "The Federal Reserve...",
    "url": "https://reuters.com/...",
    "source_name": "Reuters Business",
    "published_at": "2024-11-01T18:30:00Z",
    "tickers": ["SPY", "QQQ"],
    "sentiment": -0.45
  }
}
```

---

## SSE Streaming — Chat & Agents

Both chat completions and agent runs support **Server-Sent Events (SSE)** for token-by-token streaming.

### Using EventSource (browser)

```javascript
// Agent streaming
const response = await fetch('/api/v1/agents/run/stream', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json',
    'Accept': 'text/event-stream',
  },
  body: JSON.stringify({
    query: 'Analyze AAPL',
    llm_config: { model: 'gpt-4o-mini', api_key: 'sk-...', base_url: 'https://api.openai.com/v1' }
  })
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;

  const chunk = decoder.decode(value);
  const lines = chunk.split('\n');

  for (const line of lines) {
    if (line.startsWith('data: ')) {
      const data = JSON.parse(line.slice(6));
      if (data.type === 'token') {
        process.stdout.write(data.content);
      } else if (data.type === 'done') {
        console.log('\n[Done]');
      }
    }
  }
}
```

### Using curl

```bash
curl -X POST http://localhost:8000/api/v1/agents/run/stream \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -N \
  -d '{"query": "What is the macro outlook?", "llm_config": {...}}'
```

---

## Error Reference

All errors follow this format:

```json
{
  "error": {
    "code": "AUTH_REQUIRED",
    "message": "Token expired",
    "details": {},
    "request_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

| Code | HTTP | Description |
|------|------|-------------|
| `AUTH_REQUIRED` | 401 | Missing or invalid JWT |
| `FORBIDDEN` | 403 | Valid JWT but insufficient role |
| `RESOURCE_NOT_FOUND` | 404 | Resource not found or belongs to another user |
| `INVALID_PARAMS` | 422 | Request validation failed |
| `RATE_LIMITED` | 429 | Too many requests — check `Retry-After` header |
| `SCRIPT_TIMEOUT` | 504 | Python script timed out |
| `SCRIPT_ERROR` | 502 | Python script returned error |
| `EXTERNAL_API_ERROR` | 502 | Upstream data source error |
| `MISSING_API_KEY` | 400 | Required external API key not configured |
| `LLM_PROVIDER_ERROR` | 502 | LLM provider error |
| `INTERNAL_ERROR` | 500 | Unexpected server error |

### Rate limits

| Tier | Default | Agent endpoints |
|------|---------|-----------------|
| Default | 60 req/min | 10 req/min |
| Paid | 600 req/min | 60 req/min |

Rate limit headers on every response:

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
Retry-After: 30   (only on 429)
```

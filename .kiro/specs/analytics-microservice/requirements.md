# Requirements Document

> Spec: **Analytics Microservice** — tích hợp fincept-api vào QuantDinger

## Introduction

Mục tiêu của spec này là tích hợp `fincept-api` (rename thành **"Analytics"**) vào hệ sinh thái QuantDinger với 4 capability: **News, Chatbot, Agent, Analytics**. Self-host nội bộ, chưa commercial deploy. Pháp lý sạch ở Phase 2 (rewrite — out of scope spec này).

Phương án A — microservice ghép vào QuantDinger Flask + Vue:
- QuantDinger giữ nguyên (chart, IDE, backtest, live trading, billing, MCP)
- Analytics chạy độc lập (FastAPI + workers + scripts)
- Chia sẻ Postgres (schema `analytics.*`) và Redis (prefix `analytics:`)
- Frontend QuantDinger-Vue thêm 4 routes `/analytics/*`

## Glossary

- **QD**: QuantDinger (Flask backend Apache 2.0 + Vue 2 frontend)
- **Analytics**: Tên hiển thị của fincept-api sau khi rename
- **JWT bridge**: Mechanism share JWT secret giữa Flask và FastAPI
- **Subprocess bridge**: Pattern fincept-api gọi Python scripts qua `asyncio.create_subprocess_exec`
- **Persona**: AI agent với system prompt nhân cách hóa (Buffett, Lynch, …)
- **Comprehensive analysis**: Endpoint gộp DCF + technicals + sentiment + AI opinion cho 1 symbol

## Requirements

## Requirement 0: Foundation & Integration

### 0.1 — Microservice deploy độc lập

**As a** dev/ops, **I want** Analytics service chạy như một container riêng cạnh QuantDinger Flask, **so that** scale và deploy độc lập.

**Acceptance criteria:**
1. WHEN run `docker compose up -d` THEN Analytics container start cùng Flask + Postgres + Redis.
2. WHEN gọi `GET /analytics/api/v1/health` THEN trả 200 với `{"status":"ok","redis":"ok","db":"ok"}`.
3. WHEN Flask down THEN Analytics vẫn trả health 200 (loose coupling).

### 0.2 — Reverse proxy routing

**As a** user, **I want** truy cập `https://<domain>/analytics/*` qua Caddy/Nginx, **so that** không cần expose port 8000 ra ngoài.

**Acceptance:**
1. `GET /analytics/api/v1/health` → forward đến Analytics:8000.
2. `WS /analytics/ws/news` → WebSocket forward, không bị buffer.
3. CORS đồng nhất với QuantDinger (cùng origin).

### 0.3 — JWT authentication chia sẻ với QuantDinger

**As a** user đã login QuantDinger, **I want** dùng cùng token cho Analytics, **so that** không phải login 2 lần.

**Acceptance:**
1. JWT do QuantDinger Flask cấp phải verify được tại Analytics (cùng SECRET_KEY, HS256).
2. JWT invalid (sai signature, expired, missing sub) → trả `AUTH_REQUIRED` 401.
3. JWT thiếu role yêu cầu (vd: agent run cần role nào đó) → trả `FORBIDDEN` 403.
4. Cache user lookup từ Postgres trong Redis 5 phút để giảm load DB.

### 0.4 — User isolation

**As a** user A, **I want** không thể đọc/sửa data của user B, **so that** privacy.

**Acceptance:**
1. Chat session của user B → user A request → 404, không 403 (không leak existence).
2. Agent run history filter theo `user_id == jwt.sub`.
3. PBT verify với fixture 2 user.

### 0.5 — Database schema isolation

**As a** ops, **I want** Analytics chỉ access schema `analytics.*`, không touch `public.*` của QuantDinger, **so that** không gây conflict.

**Acceptance:**
1. Postgres user của Analytics chỉ có `GRANT USAGE ON SCHEMA analytics`.
2. Alembic migrations của Analytics chỉ tạo table trong `analytics.*`.
3. Test attempt `SELECT * FROM public.users` từ Analytics user → permission denied.

### 0.6 — Redis key namespace

**As a** ops, **I want** Redis keys không conflict với QuantDinger, **so that** không gây bug data.

**Acceptance:**
1. Mọi key Analytics set có prefix `analytics:`.
2. Mọi pubsub channel có prefix `analytics:`.
3. Health check verify Redis ping OK.

### 0.7 — Loại bỏ phụ thuộc `api.fincept.in`

**As a** ops, **I want** Analytics chạy fully self-host, không gọi `api.fincept.in`, **so that** không phụ thuộc bên thứ ba.

**Acceptance:**
1. Grep code `api.fincept.in` trong `analytics/` (không kể docs/) → 0 matches.
2. 3 file Python liên quan (`deepagents/orchestrator.py`, `finagent_core/registries/{fincept_model,models_registry}.py`) đã sửa.
3. Default LLM provider không còn "fincept", thay bằng OpenAI-compatible (user tự config).

### 0.8 — Audit log

**As a** compliance, **I want** mọi action được log, **so that** có thể trace.

**Acceptance:**
1. Mọi POST/DELETE endpoint ghi entry vào `analytics.audit_log`.
2. Entry chứa user_id, action, resource, request_id, ip, ts.
3. Audit log retention 90 ngày (config được).

---

## Requirement 1: News Module

### 1.1 — RSS feed aggregator

**As a** user, **I want** xem news realtime từ ~20 nguồn tài chính, **so that** theo dõi thị trường.

**Acceptance:**
1. Worker `news_fetcher` chạy mỗi 30s, fetch ≥10 RSS sources active.
2. Source bị error 5 lần liên tiếp → tự disable + alert log.
3. Articles mới push vào Redis Stream `analytics:news:queue` trong < 5s.

### 1.2 — Dedupe & ordering

**As a** user, **I want** không bị spam article trùng, **so that** UX tốt.

**Acceptance:**
1. URL canonicalization: lowercase host, normalize trailing slash, strip fragment, sort query params.
2. Cùng URL canonicalized → chỉ 1 row trong `analytics.news_articles`.
3. `GET /news?limit=N` trả N article mới nhất (`published_at DESC`).
4. PBT property 4 và 5 pass.

### 1.3 — NLP enrichment

**As a** user, **I want** article có sentiment + ticker tags + entities, **so that** filter dễ dàng.

**Acceptance:**
1. Worker `news_nlp` consume từ Redis Stream, run FinBERT sentiment + spaCy NER.
2. Sentiment ∈ [-1, 1].
3. Tickers match với watchlist được lưu trong DB (Phase later) hoặc S&P500 list.
4. Latency end-to-end (RSS → DB enriched) < 60s.

### 1.4 — REST API

**As a** developer, **I want** API tìm kiếm/list news, **so that** build UI.

**Acceptance:**
1. `GET /news?ticker=&source=&sentiment=&from=&to=&limit=` — pagination + filter.
2. `GET /news/search?q=` — Postgres FTS.
3. `GET /news/{id}` — chi tiết article.
4. Response p99 < 500ms với 100k articles trong DB.

### 1.5 — WebSocket realtime

**As a** user, **I want** thấy news mới ngay khi xuất hiện, **so that** không miss.

**Acceptance:**
1. `WS /ws/news` — fanout tất cả news mới.
2. `WS /ws/news?ticker=AAPL` — chỉ articles liên quan AAPL.
3. Latency từ NLP done → WS push < 200ms p99.
4. Reconnect tự động sau disconnect ≤ 5s.

---

## Requirement 2: Chatbot Module

### 2.1 — OpenAI-compatible completions

**As a** user, **I want** chat với LLM tự chọn provider, **so that** không bị lock-in.

**Acceptance:**
1. `POST /chat/completions` accept body `{model, messages[], stream?, llm_config?}`.
2. Auto-detect provider từ `llm_config.base_url` (OpenAI, Groq, Anthropic, Ollama, LiteLLM proxy, …).
3. `stream=true` → SSE response, TTFB < 1.5s p95.
4. Hỗ trợ tối thiểu 5 providers test pass.

### 2.2 — Session persist & ownership

**As a** user, **I want** lưu lịch sử chat, **so that** xem lại.

**Acceptance:**
1. `POST /chat/sessions { title?, persona_id?, llm_config? }` → tạo session, lưu DB.
2. `GET /chat/sessions` chỉ trả sessions của user hiện tại.
3. `GET /chat/sessions/{id}` của user khác → 404.
4. `DELETE /chat/sessions/{id}` xóa cascade messages.
5. PBT property 7 pass.

### 2.3 — Token accounting & cost

**As a** ops, **I want** track token usage per user, **so that** quota & billing.

**Acceptance:**
1. Mỗi message có `tokens_in`, `tokens_out`, `latency_ms`.
2. Tổng tokens per session = sum của messages.
3. Endpoint `GET /chat/sessions/{id}/usage` trả tổng tokens + estimated cost.
4. PBT property 8 pass.

### 2.4 — System prompt presets

**As a** user, **I want** chọn nhanh preset (stock analysis, macro, options strategy), **so that** không phải gõ system prompt mỗi lần.

**Acceptance:**
1. Endpoint `GET /chat/presets` trả ≥5 preset.
2. Khi tạo session với `preset_id` → auto inject system prompt.

### 2.5 — Markdown + tool call support

**As a** user, **I want** response có markdown + code highlight, tool call hiển thị, **so that** UX tốt.

**Acceptance:**
1. Streaming chunks giữ nguyên markdown.
2. Nếu LLM trả tool_calls → lưu vào `chat_messages.tool_calls` JSONB, render UI khác message thường.

---

## Requirement 3: Agent Module

### 3.1 — Persona discovery

**As a** user, **I want** xem tất cả personas có sẵn, **so that** chọn đúng cho task.

**Acceptance:**
1. `GET /agents/` trả ≥30 personas (đã có trong fincept-api).
2. `GET /agents/?category=trader` filter được.
3. Response < 1s (có cache).

### 3.2 — Single agent run

**As a** user, **I want** chạy 1 agent với query, **so that** nhận phân tích.

**Acceptance:**
1. `POST /agents/run` body `{agent_id, query, llm_config, session_id?}` → response sau ≤120s.
2. `POST /agents/run/stream` SSE với events `thinking|token|tool|tool_result|done|error`.
3. Client disconnect → subprocess kill trong < 2s.
4. API key trong llm_config KHÔNG xuất hiện trong log.

### 3.3 — Multi-agent team

**As a** user, **I want** chạy đội multi-agent, **so that** lấy nhiều góc nhìn.

**Acceptance:**
1. `POST /agents/team/run` với team config (mode: route/coordinate/collaborate).
2. `POST /agents/multi/run` query nhiều agents song song.
3. Aggregate response option.

### 3.4 — Audit & history

**As a** user, **I want** xem lại các lần chạy agent, **so that** review.

**Acceptance:**
1. Mỗi run lưu vào `analytics.agent_runs` với user_id, persona_id, query, response, duration, tokens.
2. `GET /agents/runs?user_id=&from=&to=` trả history (chỉ runs của user hiện tại).
3. PBT property 9 pass.

### 3.5 — Execution planner

**As a** user, **I want** tạo + execute kế hoạch phân tích phức tạp (DAG), **so that** workflow tự động.

**Acceptance:**
1. `POST /agents/plan/{stock|portfolio|dynamic}` tạo plan.
2. `POST /agents/plan/execute` chạy DAG, timeout 300s.
3. Plan steps progress visible qua streaming.

### 3.6 — Paper trading bridge

**As a** user, **I want** agent đề xuất paper trade, **so that** test ý tưởng.

**Acceptance:**
1. `POST /agents/paper/trade` execute paper trade.
2. `GET /agents/paper/portfolio/{id}` xem portfolio.
3. P&L update realtime với giá market.

---

## Requirement 4: Analytics Module

### 4.1 — Market data

**As a** user, **I want** quote real-time + historical, **so that** chart và phân tích.

**Acceptance:**
1. `GET /market/quote/{symbol}` cache TTL 5s, p99 latency < 200ms cache hit.
2. `POST /market/quotes/batch` với ≤50 symbols.
3. `GET /market/history/{symbol}?interval=1d&start=&end=` OHLCV.

### 4.2 — Equity research

**As a** user, **I want** xem fundamentals, financials, **so that** quyết định đầu tư.

**Acceptance:**
1. `GET /equity/{symbol}/info` — sector, market cap, P/E, ROE.
2. `GET /equity/{symbol}/financials` — IS/BS/CF.
3. `POST /equity/{symbol}/dcf` với params custom (growth, discount, terminal).

### 4.3 — Portfolio analytics

**As a** user, **I want** optimize và đo lường portfolio, **so that** quản lý risk.

**Acceptance:**
1. `POST /portfolio/optimize` với method (mean-variance, risk-parity, …).
2. `POST /portfolio/metrics` Sharpe/Sortino/Max DD/Alpha/Beta.
3. `POST /portfolio/var` historical/parametric/MC.

### 4.4 — Technical indicators & signals

**As a** user, **I want** tính RSI/MACD/BB, get signals, **so that** trading idea.

**Acceptance:**
1. `POST /technical/indicators` body `{symbol, indicators[], period?, interval?}`.
2. `POST /technical/signals` rule-based buy/sell/hold + confidence.

### 4.5 — Comprehensive stock analysis

**As a** user, **I want** 1 endpoint trả tất cả phân tích cho 1 symbol, **so that** UI nhanh.

**Acceptance:**
1. `POST /analytics/comprehensive/{symbol}` gộp: quote + info + DCF + technicals + recent news + AI opinion.
2. Endpoint dùng concurrent calls nội bộ, response p95 < 8s.
3. Cache aggregated TTL 60s.

---

## Requirement 5: UI Integration với QuantDinger-Vue

### 5.1 — News page

**As a** QD user, **I want** mở `/analytics/news` thấy news realtime, **so that** không phải mở tab khác.

**Acceptance:**
1. Page render trong < 2s.
2. Infinite scroll lazy load.
3. Filter sidebar: ticker, sentiment, source, language, date range.
4. WebSocket reconnect tự động.
5. Sentiment badges (xanh/đỏ/vàng).

### 5.2 — Chat page

**As a** QD user, **I want** mở `/analytics/chat` chat với LLM, **so that** research với AI.

**Acceptance:**
1. Conversation list bên trái, message stream phải.
2. LLM provider config UI (model, base_url, api_key, lưu localStorage encrypted).
3. Streaming token-by-token với markdown render.
4. Copy / regenerate / edit message.

### 5.3 — Agents page

**As a** QD user, **I want** browse + run agents, **so that** AI personas analysis.

**Acceptance:**
1. Page `/analytics/agents` gallery với category filter.
2. Page `/analytics/agents/{id}` run console với streaming.
3. Multi-agent team builder (drag & drop).
4. History panel xem lại runs.

### 5.4 — Comprehensive analysis page

**As a** QD user, **I want** mở `/analytics/stock/{symbol}` thấy mọi thứ về symbol, **so that** quyết định nhanh.

**Acceptance:**
1. Tab Overview, Chart, Fundamentals, DCF, Technicals, News, AI Analysis.
2. Mỗi tab load < 3s.
3. AI Analysis tab gọi agent streaming.

### 5.5 — Theme & i18n đồng nhất với QuantDinger

**Acceptance:**
1. Dùng Ant Design Vue components giống QuantDinger.
2. Theme dark/light đồng nhất.
3. i18n hỗ trợ ít nhất EN + VI (tận dụng locales của QD-Vue).

---

## Requirement 6: Operations & Polish

### 6.1 — Rate limiting

1. Per user: 60 req/min default, 10 req/min cho agent run, 1 req/min cho heavy job (training).
2. Header `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `Retry-After` khi 429.

### 6.2 — Monitoring

1. Prometheus `/metrics` endpoint.
2. Grafana dashboard: HTTP req/s, latency p50/p95/p99, errors, cache hit rate, news pipeline lag, agent runs.
3. Alert nếu error rate > 5% trong 5 phút.

### 6.3 — Load test

1. k6 test pass: 100 concurrent users gọi `GET /news`, p99 < 500ms.
2. k6 test pass: 50 concurrent SSE chat streams, không drop connection.
3. k6 test pass: 200 concurrent WebSocket subscribers `/ws/news`.

### 6.4 — Documentation

1. README install < 10 phút từ git clone.
2. Swagger UI tại `/analytics/api/v1/docs`.
3. API guide trong QuantDinger docs folder.

### 6.5 — Backup & recovery

1. pg_dump cron daily cho schema `analytics.*`.
2. Documentation restore procedure.
3. Test restore drill ít nhất 1 lần.

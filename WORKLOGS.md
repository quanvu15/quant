# WORKLOGS — Fincept API Implementation

> **Dự án:** Fincept Terminal API Gateway → Analytics Microservice
> **Bắt đầu:** 18/05/2026 | **Cập nhật:** 21/05/2026
> **Plan file:** [PLAN.md](./PLAN.md)
> **Repo:** `fincept-api/` trong monorepo FinceptTerminal

---

## Thống kê tiến độ

| Phase | Tasks hoàn thành | Tổng tasks | % | Test count |
|---|---|---|---|---|
| Phase 0 — Foundation | 8 | 8 | **100%** | 29 ✅ |
| Phase 1 — AI Agents | 11 | 12 | **92%** | 33 ✅ |
| Phase 2 — Multi-Asset Analytics | 10 | 10 | **100%** | 16 ✅ |
| Phase 3 — QuantLib Suite | 10 | 10 | **100%** | 14 ✅ |
| Phase 4 — Global Intelligence | 11 | 11 | **100%** | 15 ✅ |
| Phase 5 — AI Quant Lab | 13 | 13 | **100%** | 12 ✅ |
| Phase 6 — Hardening | 8 | 8 | **100%** | 27 ✅ |
| **Analytics Phase 0 (Foundation)** | 8 | 8 | **100%** | — |
| **Analytics Phase 1 (News module)** | 7 | 8 | **88%** | 37 ✅ |
| **TỔNG** | **86** | **88** | **98%** | **183 ✅** |

> Pending: P1-T12 — Postman collection; Analytics 1.8 — Vue News page (frontend)
| **TỔNG** | **71** | **72** | **99%** | **146 ✅** |
>
> **Integration test thực tế: 16/17 endpoints pass** (1 fail = rate limit đúng thiết kế)

> Pending (3 tasks): P1-T12, P2-T10, P3-T10, P5-T13 — Postman collections

---

## Nhật ký công việc

### 21/05/2026 — Analytics Phase 0 + Phase 1 (News module) ✅

**Môi trường Python:**
- Xác định venv duy nhất: `fincept-qt/venv-numpy2/Scripts/python.exe` (Python 3.12.10)
- Cài thêm: `structlog`, `python-jose`, `feedparser`, `httpx`, `pytest-asyncio`, `pytest-cov`
- Tạo steering file `.kiro/steering/python-environment.md` để agent luôn dùng đúng venv

**Analytics Phase 0 — Foundation (đã hoàn thành trước đó):**
- 0.1–0.8: Rename, config, JWT bridge, Redis prefix, schema migration, audit log ✅
- 0.9: Docker compose với 3 services (analytics-api, news-fetcher, news-nlp) ✅
- 0.10–0.12: Caddy config, smoke test, README (pending — cần QuantDinger stack)

**Analytics Phase 1 — News module:**

| Task | File | Mô tả |
|---|---|---|
| 1.1 | `alembic/versions/002_news_sources_seed.py` | 20 RSS sources seed |
| 1.2 | `workers/news_fetcher.py` | RSS fetcher async, 30s cycle, error threshold |
| 1.3 | `domains/news/canonicalize.py` | URL canonicalization (lowercase, strip tracking, sort params) |
| 1.3 | `domains/news/tickers.json` | S&P500 + NASDAQ100 ticker list |
| 1.4 | `workers/news_nlp.py` | FinBERT sentiment + spaCy NER + ticker matching, Redis Stream consumer |
| 1.5 | `app/routers/news.py` | REST API: list/search/get với filter + cursor pagination |
| 1.6 | `app/routers/news.py` (ws_router) | WebSocket realtime + backfill + heartbeat |
| 1.7 | `tests/test_news_canonicalize.py` | 28 tests canonicalize |
| 1.7 | `tests/test_news_dedupe.py` | 9 tests dedupe logic |

**Test results:**
- `test_news_canonicalize.py`: 28/28 ✅
- `test_news_dedupe.py`: 9/9 ✅
- `test_health.py` + `test_auth.py`: 35/35 ✅ (no regression)
- **Tổng: 72/72 passed**

**Bug fixes:**
- `tests/integration/test_scripts_real.py`: `_check_redis` defined after use → moved up
- `app/routers/news.py`: `CurrentUser = Depends(...)` duplicate → dùng `CurrentUser` type alias đúng cách

**Pending Phase 1:**
- 1.8 Vue News page (frontend — Phase sau khi có QuantDinger-Vue setup)

---

### 20/05/2026 — FRED API key + Full integration test ✅

**FRED API key đã được cấu hình:** `6f9a4ad1...` trong `.env`

**Bugs phát hiện và fix:**
1. **Route order conflict**: `/economics/fred/search` phải đứng TRƯỚC `/{series_id}` — FastAPI match "search" như series_id
2. **Duplicate dispatch block**: `search_series` bị duplicate trong intelligence_bridge, gây match sai vào `get_series`

**Full integration test kết quả (16/17 pass):**

| Endpoint | Status | Latency |
|----------|--------|---------|
| `GET /health` | ✅ | 4ms |
| `GET /agents/` | ✅ | 3.5s (54 agents) |
| `GET /market/quote/AAPL` | ✅ | 5.1s |
| `GET /equity/MSFT/info` | ✅ | 2ms (cache) |
| `POST /technical/indicators` | ✅ | 4.3s |
| `POST /portfolio/optimize` | ✅ | 7.2s |
| `POST /quant/option/price` | ✅ | 2.9s |
| `POST /quant/bond/price` | ✅ | 2.8s |
| `GET /fred/CPIAUCSL` | ✅ | 4ms (cache) |
| `GET /fred/search?q=inflation` | ✅ | 2.7s |
| `GET /fred/GDP` | ✅ | 6ms (cache) |
| `GET /geopolitics/events` | ✅ | 1.5s |
| `GET /economics/calendar` | ✅ | 2.0s |
| `GET /quant-lab/jobs` | ✅ | 4ms |
| `POST /quant-lab/backtest` | ⚠️ 429 | Rate limited (2/min — đúng thiết kế) |
| `GET /openapi.json` | ✅ | 326ms |
| `GET /metrics` | ✅ | 5ms |

**API keys đang hoạt động:**
- FRED: `6f9a4ad1...` ✅
- Finnhub: `d860om9r...` ✅
- Polygon: `lKxjBWEF...` ✅
- Alpha Vantage: `WVSV63G6...` ✅
- LLM (chainhub): `sk-LTbtv...` ✅ (gpt-5.4-mini, 10.3s)

---



**Vấn đề:** Tất cả scripts Phase 2-5 dùng CLI args, không phải JSON stdin protocol mà API cần.

**Giải pháp:** Tạo 4 bridge scripts mới trong `api_bridge/`:

| Bridge | Covers | Scripts wrapped |
|--------|--------|-----------------|
| `analytics_bridge.py` | Phase 2 portfolio, technical, news | optimize_portfolio_weights, quantstats_analysis, compute_technicals, fetch_company_news, relationship_map, fii_dii_scraper |
| `intelligence_bridge.py` | Phase 4 toàn bộ | fred_data, worldbank_data, acled_data, imf_data, oecd_data, ecb_data, boj_fetcher, boe_data, rba_data, bls_data, census_data, eurostat_data, eia_data, economic_calendar, marinetraffic_data, aisstream_data, hdx_data, relationship_map |
| `qlab_bridge.py` | Phase 5 toàn bộ | qlib_service, qlib_advanced_backtest, qlib_rl, qlib_portfolio_opt, qlib_feature_engineering, qlib_evaluation, qlib_reporting |
| `financepy_bridge.py` | Phase 3 bond/stochastic | derivatives_pricing (bond), GBM, Heston, Hull-White |

**script_catalog.py** cập nhật: tất cả 40+ entries đều trỏ đến bridge scripts.

**Kết quả test thực tế (tất cả ✅):**
| Endpoint | Kết quả |
|----------|---------|
| `GET /health` | ok, redis ok |
| `GET /market/quote/AAPL` | $298.51 (+0.22%) |
| `POST /technical/indicators` | 63 rows, RSI + MACD |
| `POST /portfolio/optimize` | success (AAPL/MSFT/GOOGL) |
| `GET /economics/worldbank/...` | data (timeout 90s) |
| `POST /quant/bond/price` | $980.31, duration=4.08 |
| `GET /agents/` | 54 agents |

**Vấn đề còn lại:**
- WorldBank API chậm (~30-60s) — đã tăng timeout lên 90s, cache 1h
- FRED cần API key (đúng như thiết kế)
- Qlib scripts cần pre-download data (đúng như thiết kế)

---



**Root cause phát hiện khi test thực tế:**

**1. Windows NotImplementedError (asyncio subprocess)**
- Nguyên nhân: uvicorn dùng `SelectorEventLoop` trên Windows, không hỗ trợ `create_subprocess_exec`
- Fix: `_run_via_thread()` — `subprocess.run()` trong `ThreadPoolExecutor` + `loop.run_in_executor()`
- VPS Linux: không bị ảnh hưởng, dùng asyncio subprocess trực tiếp

**2. Scripts dùng CLI args, không phải JSON stdin**
- Nguyên nhân: `yfinance_data.py`, `derivatives_pricing.py` dùng `sys.argv`/`argparse`, không có `--stdin` protocol
- Fix: Tạo `api_bridge/` layer — wrapper scripts nhận JSON stdin, gọi functions trực tiếp:
  - `api_bridge/market_bridge.py` — yfinance (quote, history, info, financials, sectors)
  - `api_bridge/quant_bridge.py` — derivatives pricing (BSM, Greeks, IV, VaR, GBM, stress test)
  - `api_bridge/financepy_bridge.py` — bond pricing, yield curve, Heston, Hull-White (fallback nếu FinancePy chưa cài)

**3. Pydantic validation fail trên agent list**
- Nguyên nhân: Agent configs có fields lạ (`book_source`, `agentic_memory: True`)
- Fix: Bỏ `response_model=AgentListResponse` trên discovery endpoints

**4. Lazy semaphore**
- Nguyên nhân: `asyncio.Semaphore` tạo trong `__init__` → sai event loop khi uvicorn reload
- Fix: Lazy init trong `_get_semaphore()` — tạo trong event loop hiện tại

**5. `PythonRunner` import thiếu trong agents.py**
- Fix: thêm `PythonRunner` vào import

**Kết quả test thực tế (tất cả ✅):**
| Endpoint | Kết quả |
|----------|---------|
| `GET /health` | `{"status":"ok","redis":"ok"}` |
| `GET /market/quote/AAPL` | AAPL: $297.55 (-0.1%) |
| `GET /equity/MSFT/info` | Microsoft Corp, $419, Technology |
| `POST /quant/option/price` | BSM: $8.66, delta=0.49 |
| `POST /quant/bond/price` | Clean: $980.31, duration=4.08 |
| `POST /quant/stochastic/gbm` | Mean final: 105-112 (random) |
| `GET /agents/` | 54 agents, 5 categories |

**Files tạo mới:**
- `fincept-qt/scripts/api_bridge/market_bridge.py`
- `fincept-qt/scripts/api_bridge/quant_bridge.py`
- `fincept-qt/scripts/api_bridge/financepy_bridge.py`

---



**1. VENV_NUMPY2_PYTHON — Giải thích và auto-detect:**
- Thêm `resolve_venv_numpy2()` validator trong `config.py` — tự tìm `venv-numpy2/Scripts/python.exe` trong project tree
- Cập nhật `.env.example` với giải thích chi tiết: tại sao cần 2 venv, cách tạo, option server (1 venv duy nhất)

**2. SCRIPTS_DIR — Giải thích:**
- Không copy scripts vào fincept-api vì: 300+ files, scripts import lẫn nhau, maintained trong fincept-qt
- Auto-detect đã hoạt động, thêm support relative path và resolve absolute

**3. Integration tests — Tạo framework:**
- `tests/integration/README.md` — checklist chuẩn bị môi trường
- `tests/integration/test_scripts_real.py` — 8 integration tests thực (yfinance, BSM, FRED, agent discover/run)
- Auto-skip nếu môi trường chưa sẵn sàng (`@skip_if_not_ready`)

**4. delete_session — Fix:**
- Thêm handler `delete_session` vào `finagent_core/main.py`
- Graceful fallback nếu repo không support delete

**5. LLM validation + Multi-model routing (`core/llm_router.py`):**
- `validate_llm_config()` — fail fast trước khi spawn subprocess (check format key, base_url)
- `detect_task_type()` — phân loại task: QUICK/STANDARD/THINKING/STREAMING/STRUCTURED/FINANCIAL
- `MODEL_PROFILES` — model tối ưu cho từng provider × task type:
  - THINKING → gpt-4o / claude-3-5-sonnet / deepseek-reasoner / llama-3.3-70b
  - QUICK → gpt-4o-mini / claude-3-haiku / llama-3.1-8b-instant / gemini-flash
  - FINANCIAL → gpt-4o / claude-3-5-sonnet / deepseek-reasoner
- `build_active_llm()` — build payload với optional auto-select
- `_build_payload()` trong agents router tích hợp validation

**6. Postman — Pending:**
- Cần `.env` thực tế trước, sau đó export từ Swagger UI `/docs`

**7. Prometheus — Đã cài:**
- `prometheus-client==0.21.0` thêm vào `requirements.txt` và cài vào venv
- `core/metrics.py` đã có no-op fallback — hoạt động cả khi chưa cài

**8. Gunicorn — Fix:**
- `gunicorn==23.0.0` thêm vào `requirements.txt` (đã có sẵn trong venv)

**Test gate:** 65/65 PASSED ✅

---



**P6-T1 — OpenAPI docs:**
- `app/openapi.py` — `custom_openapi()` với tag descriptions đầy đủ cho 5 modules
- Security schemes: `ApiKeyAuth` (X-API-Key) + `BearerAuth` (JWT)
- Error schema enum: 10 error codes với HTTP status mapping
- API description: provider table, rate limits, async job pattern, error codes table

**P6-T2 — SDK generation:**
- `scripts/generate_sdk.sh` — Python SDK + TypeScript/Axios SDK via openapi-generator-cli

**P6-T3 — Security hardening (`core/security.py`):**
- `sanitize_string()` — strip control chars (0x00-0x1f), max length
- `sanitize_symbol()` — only alphanumeric/dot/dash/caret, uppercase
- `sanitize_dict()` — recursive sanitization với max_depth
- `sign_request()` / `verify_signature()` — HMAC-SHA256 với timestamp freshness check (300s tolerance)
- `ENDPOINT_RATE_LIMITS` — per-endpoint overrides: agent run=10/min, model train=1/min, RL train=1/min
- `mask_api_key()` — safe logging (never log full keys)
- `is_valid_api_key_format()` — format validation

**P6-T4 — Performance:**
- Middleware dùng `get_endpoint_rate_limit()` thay hardcoded default
- `HTTP_IN_FLIGHT` gauge track concurrent requests

**P6-T5 — Monitoring (`core/metrics.py`):**
- Prometheus counters: `fincept_http_requests_total`, `fincept_script_executions_total`, `fincept_cache_hits_total`
- Histograms: `fincept_http_request_duration_seconds`, `fincept_script_execution_duration_seconds`
- Gauge: `fincept_http_requests_in_flight`, `fincept_active_jobs`
- `GET /metrics` endpoint (prometheus_client hoặc no-op fallback nếu chưa cài)
- `deploy/prometheus.yml` scrape config
- docker-compose `--profile monitoring` → Prometheus (9090) + Grafana (3000)

**P6-T6 — Load tests (`tests/load/`):**
- `k6_health.js` — 100 users, p99 < 200ms, 2 min sustained
- `k6_market_data.js` — cache hit/miss latency tracking, 100 users
- `k6_agents.js` — agent endpoints với rate limit awareness

**P6-T7 — Deployment:**
- `Dockerfile` — multi-stage (builder + runtime), non-root user (uid 1000), gunicorn+uvicorn
- `docker-compose.yml` — api + redis + prometheus + grafana (profiles)
- `deploy/k8s/deployment.yaml` — Deployment (2 replicas) + Service + Ingress, resource limits, liveness/readiness probes

**P6-T8 — Developer portal (`README.md`):**
- Quickstart (venv + Docker)
- Auth guide (API key + JWT)
- LLM providers table (9 providers)
- API examples (curl) cho tất cả 5 modules
- Rate limits table, error codes table
- Project structure, monitoring guide, SDK generation

**Files tạo mới:**
- `app/openapi.py`
- `core/security.py`
- `core/metrics.py`
- `tests/test_security.py` (27 tests)
- `tests/load/k6_health.js`, `k6_market_data.js`, `k6_agents.js`
- `deploy/prometheus.yml`
- `deploy/k8s/deployment.yaml`
- `scripts/generate_sdk.sh`
- `README.md` (rewrite hoàn chỉnh)

**Test gate:** 27/27 PASSED ✅

---



**Vấn đề:** `LLMConfig` cũ yêu cầu `provider` + `model_id` bắt buộc — không linh hoạt.

**Giải pháp:** Refactor sang OpenAI-compatible pattern:
- Field `model` (tên model) + `base_url` (endpoint) + `api_key`
- `provider` optional — **auto-detect từ base_url** (Groq, Together, DeepSeek, Anthropic, Google, Ollama, LM Studio, OpenRouter, Mistral...)
- `_build_payload` cập nhật: map `model` → `model_id` cho `finagent_core/main.py`
- `config.py`: thêm `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` server-side defaults
- `.env.example`: ví dụ cho 5 provider phổ biến

**Providers hỗ trợ:**
| Provider | base_url | Ví dụ model |
|---|---|---|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o`, `gpt-4o-mini` |
| Groq | `https://api.groq.com/openai/v1` | `llama-3.1-70b-versatile` |
| Together | `https://api.together.xyz/v1` | `meta-llama/Llama-3-70b` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| Anthropic | `https://api.anthropic.com` | `claude-3-5-sonnet-20241022` |
| Ollama | `http://localhost:11434/v1` | `llama3.2` |
| LM Studio | `http://localhost:1234/v1` | `local-model` |
| OpenRouter | `https://openrouter.ai/api/v1` | `anthropic/claude-3.5-sonnet` |
| Mistral | `https://api.mistral.ai/v1` | `mistral-large-latest` |

**Files thay đổi:**
- `models/requests/agents.py` — LLMConfig refactor
- `app/routers/agents.py` — `_build_payload` update
- `app/config.py` — thêm LLM_BASE_URL/MODEL/API_KEY
- `.env.example` — thêm ví dụ providers

**Tests mới:** `tests/test_llm_config.py` — 19 tests (auto-detect, validation, serialization)
**Test gate:** 52/52 PASSED ✅

---

### 19/05/2026 — Phase 5 ✅ AI Quant Lab API

**Quyết định kiến trúc:** Dùng `asyncio.create_task` + Redis thay Celery — đơn giản hơn, không cần worker riêng, đủ cho MVP.

**Files tạo mới:**
- `core/jobs.py` — Redis-backed job lifecycle (create/get/update/list/cancel/run_job_async)
- `app/routers/quant_lab.py` — 15 endpoints
- `tests/test_quant_lab.py` — 12 tests

**Endpoints:**
| Group | Endpoints | Pattern |
|---|---|---|
| Job Management | GET /jobs, GET /jobs/{id}, GET /jobs/{id}/result, DELETE /jobs/{id}, WS /jobs/{id}/stream | CRUD + WebSocket |
| Backtesting | POST /backtest | Async job (202) |
| Model Training | POST /models/train, POST /models/{id}/predict, GET /models, GET /models/{id} | Async + Sync |
| Factor Discovery | POST /factors/discover, POST /factors/evaluate | Async job |
| Portfolio Opt | POST /portfolio/optimize | Sync |
| RL Trading | POST /rl/train, POST /rl/{id}/backtest | Async job |
| Reporting | POST /report/tearsheet, POST /report/factor-attribution | Async + Sync |

**Test gate:** 12/12 PASSED ✅

---

### 19/05/2026 — Phase 4 ✅ Global Intelligence API

**Files tạo mới:**
- `app/routers/intelligence.py` — 20+ endpoints
- `models/requests/intelligence.py` — MaritimeBatchRequest, MaritimeAreaRequest
- `tests/test_intelligence.py` — 15 tests

**Endpoints theo nhóm:**
| Nhóm | Scripts wrap | Endpoints | Cache TTL |
|---|---|---|---|
| Geopolitics | acled_data.py, hdx_data.py, relationship_map.py | events, countries, categories, hdx, relationships | 2min |
| Maritime | marinetraffic_data.py, aisstream_data.py | vessel, batch, area, history | 1min |
| Economics | fred_data.py, worldbank_data.py, imf_data.py, oecd_data.py | fred, worldbank, imf, oecd, calendar | 1h |
| Central Banks | ecb/boj/boe/rba/fed scripts | 12 banks via /central-banks/{bank} | 1h |
| Gov Data | bls_data.py, census_data.py, eurostat_data.py | bls, govdata/{country}/{dataset} | 1h |
| Energy/Env | eia_data.py, worldbank_data.py | eia/{category}, co2 | 1h/24h |

**Test gate:** 15/15 PASSED ✅

---

### 19/05/2026 — Phase 3 ✅ QuantLib Suite API

**Files tạo mới:**
- `app/routers/quantlib.py` — 20+ endpoints
- `models/requests/quantlib.py` — 18 request models
- `tests/test_quantlib.py` — 14 tests

**Endpoints theo nhóm:**
| Nhóm | Endpoints | Scripts |
|---|---|---|
| Option Pricing | price, greeks, implied-vol, fx, batch-greeks | derivatives_pricing.py |
| Fixed Income | bond/price, bond/ytm, bond/duration, yield-curve/bootstrap | financepy_wrapper.py |
| Swap & Credit | swap/irs, swap/cds | derivatives_pricing.py |
| Risk Models | risk/var, risk/stress-test, risk/credit | derivatives_pricing.py |
| Stochastic | stochastic/gbm, stochastic/heston, stochastic/hull-white | financepy_wrapper.py |
| Volatility | vol/surface, vol/sabr | derivatives_pricing.py |

**Test gate:** 14/14 PASSED ✅

---

### 19/05/2026 — Phase 2 ✅ Multi-Asset Analytics API

**Files tạo mới:**
- `app/routers/analytics.py` — 25+ endpoints
- `models/requests/analytics.py` — 11 request models
- `tests/test_analytics.py` — 16 tests

**Endpoints theo nhóm:**
| Nhóm | Endpoints | Cache TTL |
|---|---|---|
| Market Data | quote, quotes/batch, history, search, sectors | 5s / 30s / 300s |
| Equity Research | info, financials, dcf, news, relationships | 1h / 30min / 5min |
| Portfolio Analytics | optimize, metrics, backtest, var | no cache |
| Derivatives | chain, greeks, implied-vol, fii-dii | 5s / 60s / 30min |
| Technical Analysis | indicators, signals | 60s |

**Test gate:** 16/16 PASSED ✅

---

### 19/05/2026 — Phase 1 ✅ AI Agents API

**Files tạo mới:**
- `app/routers/agents.py` — 20+ endpoints (full implementation)
- `models/requests/agents.py` — LLMConfig + 12 request models
- `models/responses/agents.py` — 9 response models
- `tests/test_agents.py` — 31 tests

**Endpoints:**
| Nhóm | Endpoints |
|---|---|
| Discovery | GET / (discover), GET /list (filter by category) |
| Run | POST /run (one-shot), POST /run/stream (SSE) |
| Team/Multi | POST /team/run, POST /multi/run |
| Planner | POST /plan/stock, /plan/portfolio, /plan/execute (300s), /plan/dynamic |
| Analysis | POST /analyze/stock, /portfolio, /risk, /macro, /earnings, /sector-rotation |
| Paper Trading | POST /paper/trade, GET /paper/portfolio/{id}, GET /paper/positions/{id} |
| Sessions | POST /sessions, GET /sessions/{id}, POST /sessions/{id}/messages, DELETE /sessions/{id} |

**SSE streaming format:**
```
THINKING: ... → {"type": "thinking", "content": "..."}
TOKEN: ...    → {"type": "token",    "content": "..."}
TOOL: ...     → {"type": "tool",     "content": "..."}
DONE: ...     → {"type": "done",     "content": "..."}
ERROR: ...    → {"type": "error",    "content": "..."}
```

**Test gate:** 31/31 PASSED ✅

---

### 19/05/2026 — Phase 0 ✅ Foundation & Setup

**Files tạo mới:**
- `app/main.py` — FastAPI app với lifespan, CORS, middleware
- `app/config.py` — Pydantic Settings từ .env
- `app/dependencies.py` — ApiKeyDep, JwtUserDep
- `app/middleware.py` — LoggingMiddleware (request_id, latency), RateLimitMiddleware
- `core/python_runner.py` — Async subprocess bridge (run + stream)
- `core/script_catalog.py` — 40+ script registrations
- `core/cache.py` — Redis async cache + TTL constants
- `core/auth.py` — API key + JWT (python-jose)
- `core/errors.py` — ErrorCode enum + FinceptAPIError hierarchy
- `core/logging_setup.py` — structlog với stdlib.LoggerFactory
- `core/jobs.py` — Redis-backed async job system
- `models/responses/base.py` — StandardResponse, PaginatedResponse
- `Dockerfile`, `docker-compose.yml`, `.env.example`, `requirements.txt`
- `.github/workflows/ci.yml` — lint + test + docker build
- `tests/` — conftest, test_health, test_auth, test_python_runner (29 tests)
- `.venv/` — Python 3.12 venv với tất cả dependencies

**Bug fix:** structlog `add_logger_name` cần `stdlib.LoggerFactory()` thay `PrintLoggerFactory()`.

**Test gate:** 29/29 PASSED ✅

---

## Quyết định kỹ thuật quan trọng

| Ngày | Quyết định | Lý do |
|---|---|---|
| 19/05/2026 | LLMConfig: `model` + `base_url` thay `provider` + `model_id` | OpenAI-compatible, hỗ trợ mọi provider, provider auto-detect từ URL |
| 19/05/2026 | Phase 5: asyncio.create_task thay Celery | Đơn giản hơn, không cần worker riêng, đủ cho MVP |
| 19/05/2026 | Python 3.12 thay 3.11.9 | 3.11.9 không có sẵn, 3.12 tương thích hoàn toàn |
| 19/05/2026 | structlog: `stdlib.LoggerFactory()` thay `PrintLoggerFactory()` | `add_logger_name` processor yêu cầu logger có `.name` attribute |
| 19/05/2026 | Phase 3: subprocess thay direct import | Tránh dependency conflict giữa venv API và venv scripts |
| 19/05/2026 | Phases 1-5 triển khai song song | Theo dependency map trong PLAN.md, không có blocking dependency |

---

## Vấn đề đang mở (Open Issues)

| ID | Mô tả | Phase | Ưu tiên | Trạng thái |
|---|---|---|---|---|
| OI-001 | Postman collections cho Phase 1-5 | 1-5 | Low | Open |
| OI-002 | VENV_NUMPY2_PYTHON cần config thực tế khi deploy | 0 | High | Open |
| OI-003 | Redis cần chạy thực tế cho integration tests | 0 | Medium | Open |
| OI-004 | Phase 6: OpenAPI docs, SDK, monitoring, load test | 6 | Medium | Open |

---

## Hướng dẫn chạy

```bash
# 1. Kích hoạt venv
cd fincept-api
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Linux/macOS

# 2. Chạy tests
python -m pytest tests/ -v

# 3. Chạy API server (cần Redis)
uvicorn app.main:app --reload --port 8000

# 4. Chạy với Docker
docker-compose up -d
```

**Cấu hình tối thiểu trong `.env`:**
```env
SCRIPTS_DIR=../fincept-qt/scripts
VENV_NUMPY2_PYTHON=../path/to/venv-numpy2/Scripts/python.exe
REDIS_URL=redis://localhost:6379/0
MASTER_API_KEY=fincept_admin_your_key_here
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=sk-...
```

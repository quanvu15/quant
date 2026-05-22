# KẾ HOẠCH TRIỂN KHAI API — FINCEPT TERMINAL

> **Phiên bản:** 1.0 | **Ngày tạo:** 18/05/2026
> **Mục tiêu:** Expose 5 module cốt lõi thành REST/WebSocket API để các dự án ngoài kết nối
> **Modules:** Multi-Asset Analytics · AI Agents · QuantLib Suite · Global Intelligence · AI Quant Lab

---

## TỔNG QUAN TIẾN ĐỘ

| Phase | Tên | Thời gian | Trạng thái | Test Gate | Sign-off |
|---|---|---|---|---|---|
| **Phase 0** | Foundation & Setup | Tuần 1 | ✅ Hoàn thành | ✅ | ✅ |
| **Phase 1** | AI Agents API | Tuần 2–3 | ✅ Hoàn thành | ✅ | ✅ |
| **Phase 2** | Multi-Asset Analytics API | Tuần 4–5 | ✅ Hoàn thành | ✅ | ✅ |
| **Phase 3** | QuantLib Suite API | Tuần 6–7 | ✅ Hoàn thành | ✅ | ✅ |
| **Phase 4** | Global Intelligence API | Tuần 8–9 | ✅ Hoàn thành | ✅ | ✅ |
| **Phase 5** | AI Quant Lab API | Tuần 10–12 | ✅ Hoàn thành | ✅ | ✅ |
| **Phase 6** | Integration, Docs & Hardening | Tuần 13–14 | ✅ Hoàn thành | ✅ | ✅ |

**Tổng thời gian ước tính:** 14 tuần (~3.5 tháng)

**Legend trạng thái:** ⬜ Chưa bắt đầu | 🔄 Đang làm | ✅ Hoàn thành | ❌ Blocked | ⏸ Tạm dừng

**Legend gate:** ⬜ Chưa chạy | 🔄 Đang chạy | ✅ Passed | ❌ Failed

> ⚠️ **Quy tắc cứng:** Cột Sign-off phải là ✅ trước khi Phase tiếp theo được bắt đầu.

---

---

## PHASE 0 — FOUNDATION & SETUP

> **Mục tiêu:** Dựng skeleton project, infrastructure dùng chung cho tất cả phases
> **Thời gian:** Tuần 1 (5 ngày)
> **Trạng thái:** ✅ Hoàn thành
> **Test Gate:** ✅ Passed (29/29) | **Code Review:** ✅ | **Sign-off:** ✅

### Cấu trúc thư mục đề xuất

```
fincept-api/
├── app/
│   ├── main.py                  # FastAPI app entry point
│   ├── config.py                # Settings (env vars, paths)
│   ├── dependencies.py          # Shared dependencies (auth, cache)
│   ├── middleware.py            # CORS, logging, rate limit
│   └── routers/
│       ├── agents.py            # Phase 1
│       ├── analytics.py         # Phase 2
│       ├── quantlib.py          # Phase 3
│       ├── intelligence.py      # Phase 4
│       └── quant_lab.py         # Phase 5
├── core/
│   ├── python_runner.py         # Subprocess bridge (wrap PythonRunner logic)
│   ├── script_catalog.py        # Script path registry
│   ├── cache.py                 # Redis cache layer
│   ├── auth.py                  # JWT + API key auth
│   └── errors.py                # Error handlers
├── models/
│   ├── requests/                # Pydantic request models
│   └── responses/               # Pydantic response models
├── tests/
│   ├── test_agents.py
│   ├── test_analytics.py
│   └── ...
├── scripts/                     # Symlink → fincept-qt/scripts/
├── .env.example
├── requirements.txt
├── docker-compose.yml
└── README.md
```

### Tasks Phase 0

- [x] **P0-T1** Khởi tạo FastAPI project skeleton
  - Tạo `app/main.py` với health check endpoint `GET /health`
  - Cấu hình CORS, logging middleware
  - Setup Pydantic Settings từ `.env`

- [x] **P0-T2** Implement `core/python_runner.py`
  - Async subprocess wrapper (asyncio.create_subprocess_exec)
  - Timeout handling (default 60s, configurable per endpoint)
  - Stdin/stdout JSON protocol (mirror `PythonRunner` C++ logic)
  - Concurrent execution cap (max 5 processes)
  - Error capture từ stderr

- [x] **P0-T3** Implement `core/script_catalog.py`
  - Map script names → absolute paths
  - Validate scripts tồn tại khi startup
  - Hỗ trợ cả `venv-numpy1` và `venv-numpy2`

- [x] **P0-T4** Setup Authentication
  - API Key auth (header: `X-API-Key`)
  - JWT Bearer token (cho user sessions)
  - Rate limiting: 60 req/min (free), 600 req/min (paid)
  - Middleware inject API keys vào subprocess env

- [x] **P0-T5** Setup Redis Cache
  - TTL-based caching (mirror DataHub TTL policies)
  - Cache key format: `fincept:{module}:{action}:{hash(params)}`
  - Cache invalidation endpoints

- [x] **P0-T6** Standard Response Format
  - Wrap `fincept_output_standard.py` format vào Pydantic models
  - Error response schema thống nhất
  - Pagination schema

- [x] **P0-T7** Docker setup
  - `Dockerfile` với Python 3.11.9
  - `docker-compose.yml`: api + redis + (optional) postgres
  - Health checks

- [x] **P0-T8** CI skeleton
  - GitHub Actions: lint (ruff) + type check (mypy) + tests (pytest)

### Deliverables Phase 0
- [x] `GET /health` trả `{"status": "ok", "version": "1.0.0"}`
- [x] Python subprocess bridge chạy được 1 script test
- [x] Auth middleware hoạt động
- [x] Docker compose up thành công

---

---

## PHASE 1 — AI AGENTS API

> **Mục tiêu:** Expose `finagent_core/main.py` thành REST + SSE streaming API
> **Thời gian:** Tuần 2–3 (10 ngày)
> **Trạng thái:** ✅ Hoàn thành
> **Dependency:** Phase 0 hoàn thành + Sign-off ✅
> **Ưu tiên:** 🔴 P1 — Quick win, highest business value
> **Test Gate:** ✅ Passed (31/31) | **Code Review:** ✅ | **Sign-off:** ✅

### Phân tích hiện trạng

`finagent_core/main.py` đã có JSON protocol hoàn chỉnh:
- Input: `{"action": "...", "api_keys": {...}, "params": {...}, "config": {...}, "active_llm": {...}}`
- Output: JSON response hoặc streaming lines (`THINKING:`, `TOKEN:`, `TOOL:`, `DONE:`)
- Streaming: `--stream` flag + `--stdin` flag (payload qua stdin)

### Endpoints cần implement

#### 1.1 Agent Discovery

```
GET  /api/v1/agents
     Query: ?category=trader&limit=50
     Response: {agents: [...], categories: [...], count: N}

GET  /api/v1/agents/{agent_id}
     Response: {id, name, description, category, capabilities, config}

GET  /api/v1/agents/categories
     Response: {categories: [{name, count}, ...]}
```

#### 1.2 Agent Execution

```
POST /api/v1/agents/run
     Body: {
       agent_id: string,
       query: string,
       session_id?: string,
       llm_config: {provider, model_id, api_key, temperature?, max_tokens?},
       options?: {memory?, reasoning?, guardrails?}
     }
     Response: {success, response, execution_time_ms, request_id}

POST /api/v1/agents/run/stream
     Body: (same as /run)
     Response: text/event-stream (SSE)
     Events: {type: "thinking"|"token"|"tool"|"tool_result"|"done"|"error", content: string}
```

#### 1.3 Team & Multi-Agent

```
POST /api/v1/agents/team/run
     Body: {
       team_config: {name, mode, members: [...], coordinator_model},
       query: string,
       session_id?: string
     }
     Response: {success, response, execution_time_ms}

POST /api/v1/agents/multi/run
     Body: {query, agent_ids?: [...], llm_config, aggregate?: bool}
     Response: {success, responses: [{agent_id, response}], aggregated?}
```

#### 1.4 Execution Planner

```
POST /api/v1/agents/plan/stock
     Body: {symbol: string, llm_config}
     Response: {success, plan: {id, steps: [...]}}

POST /api/v1/agents/plan/portfolio
     Body: {portfolio_id: string, llm_config}
     Response: {success, plan}

POST /api/v1/agents/plan/execute
     Body: {plan, llm_config}
     Response: {success, results: [...]}

POST /api/v1/agents/plan/dynamic
     Body: {query: string, llm_config}
     Response: {success, plan}
```

#### 1.5 Financial Workflows

```
POST /api/v1/agents/analyze/stock
     Body: {symbol, llm_config, session_id?}
     Response: {success, symbol, response}

POST /api/v1/agents/analyze/portfolio
     Body: {portfolio_data: {...}, llm_config}
     Response: {success, response}

POST /api/v1/agents/analyze/risk
     Body: {portfolio_data: {...}, llm_config}
     Response: {success, response}

POST /api/v1/agents/analyze/macro
     Body: {llm_config}
     Response: {success, response}

POST /api/v1/agents/analyze/earnings
     Body: {symbol, llm_config}
     Response: {success, symbol, response}

POST /api/v1/agents/analyze/sector-rotation
     Body: {llm_config}
     Response: {success, response}
```

#### 1.6 Paper Trading Bridge

```
POST /api/v1/agents/paper/trade
     Body: {portfolio_id, symbol, action: "buy"|"sell", quantity, price}
     Response: {success, trade_id}

GET  /api/v1/agents/paper/portfolio/{portfolio_id}
     Response: {success, portfolio_value, cash, positions: [...]}

GET  /api/v1/agents/paper/positions/{portfolio_id}
     Response: {success, positions: [{symbol, quantity, avg_price, current_value}]}
```

#### 1.7 Session Management

```
POST /api/v1/agents/sessions
     Body: {agent_id, user_id?}
     Response: {session_id}

GET  /api/v1/agents/sessions/{session_id}
     Response: {session_id, agent_id, messages: [...], status}

POST /api/v1/agents/sessions/{session_id}/messages
     Body: {role: "user"|"assistant", content}
     Response: {success}

DELETE /api/v1/agents/sessions/{session_id}
```

### Tasks Phase 1

- [x] **P1-T1** Pydantic models cho tất cả request/response schemas
- [x] **P1-T2** Implement `routers/agents.py` — discovery endpoints
- [x] **P1-T3** Implement agent run (non-streaming) với subprocess bridge
- [x] **P1-T4** Implement SSE streaming endpoint
  - `asyncio.create_subprocess_exec` với `--stream --stdin`
  - Parse stdout lines → SSE events
  - Handle client disconnect (cancel subprocess)
- [x] **P1-T5** Implement team/multi-agent endpoints
- [x] **P1-T6** Implement execution planner endpoints
- [x] **P1-T7** Implement financial workflow shortcuts
- [x] **P1-T8** Implement paper trading bridge endpoints
- [x] **P1-T9** Implement session management endpoints
- [x] **P1-T10** Cache layer: cache `discover_agents` (TTL 5 phút), `list_agents` (TTL 1 phút)
- [x] **P1-T11** Tests: unit tests cho subprocess bridge, integration tests cho 3 endpoints chính
- [ ] **P1-T12** Postman collection cho tất cả Phase 1 endpoints *(cần LLM API key để test)*

### Lưu ý kỹ thuật Phase 1

- **LLM config:** Dùng OpenAI-compatible API — `model` + `base_url` + `api_key`. Provider auto-detect từ base_url. Hỗ trợ OpenAI, Groq, Together, DeepSeek, Anthropic, Ollama, LM Studio, OpenRouter, Mistral.
- **API keys injection:** LLM API keys từ request body → inject vào subprocess env, KHÔNG log
- **Timeout:** Default 120s cho agent run, 300s cho plan execute
- **Streaming disconnect:** Khi client ngắt kết nối, kill subprocess ngay lập tức
- **Concurrency:** Max 10 concurrent agent runs per API key

### Deliverables Phase 1
- [x] 20+ endpoints hoạt động
- [x] SSE streaming hoạt động (test với mock)
- [x] Integration test với subprocess bridge
- [ ] Postman collection export *(pending)*

---

---

## PHASE 2 — MULTI-ASSET ANALYTICS API

> **Mục tiêu:** Expose market data, equity research, portfolio analytics, derivatives
> **Thời gian:** Tuần 4–5 (10 ngày)
> **Trạng thái:** ✅ Hoàn thành
> **Dependency:** Phase 0 hoàn thành + Sign-off ✅
> **Test Gate:** ✅ Passed (16/16) | **Code Review:** ✅ | **Sign-off:** ✅

### Phân tích hiện trạng

Scripts đã có JSON output chuẩn qua `fincept_output_standard.py`:
```json
{
  "success": true,
  "data": {"type": "table|dict|array|timeseries", "value": {...}},
  "metadata": {"script": "...", "timestamp": "...", "execution_time_ms": 123}
}
```

### Endpoints cần implement

#### 2.1 Market Data (Real-time & Historical)

```
GET  /api/v1/market/quote/{symbol}
     Query: ?source=yfinance|polygon|finnhub (default: yfinance)
     Cache: TTL 5s
     Response: {symbol, price, change, change_pct, volume, high, low, open, prev_close, timestamp}

POST /api/v1/market/quotes/batch
     Body: {symbols: ["AAPL","MSFT",...], source?}
     Cache: TTL 5s
     Response: {quotes: [{...}, ...]}

GET  /api/v1/market/history/{symbol}
     Query: ?start=2024-01-01&end=2025-01-01&interval=1d&source=yfinance
     Cache: TTL 5 phút (daily), 30s (intraday)
     Response: {symbol, interval, bars: [{timestamp, open, high, low, close, volume}]}

GET  /api/v1/market/search
     Query: ?q=apple&limit=10
     Response: {results: [{symbol, name, exchange, type}]}

GET  /api/v1/market/sectors
     Response: {sectors: [{name, performance_1d, performance_1w, performance_1m}]}
```

#### 2.2 Equity Research

```
GET  /api/v1/equity/{symbol}/info
     Cache: TTL 1 giờ
     Response: {symbol, name, sector, industry, market_cap, pe, pb, ev_ebitda, roe, roic, ...}

GET  /api/v1/equity/{symbol}/financials
     Query: ?period=annual|quarterly&limit=4
     Cache: TTL 1 giờ
     Response: {income_statement: [...], balance_sheet: [...], cash_flow: [...]}

POST /api/v1/equity/{symbol}/dcf
     Body: {
       growth_rate?: float,        # default: auto-estimate
       discount_rate?: float,      # default: WACC
       terminal_growth?: float,    # default: 2.5%
       projection_years?: int      # default: 5
     }
     Cache: TTL 30 phút
     Response: {symbol, intrinsic_value, current_price, upside_pct, assumptions: {...}}

GET  /api/v1/equity/{symbol}/news
     Query: ?limit=20&source=finnhub|polygon
     Cache: TTL 5 phút
     Response: {articles: [{title, summary, url, published_at, sentiment}]}

GET  /api/v1/equity/{symbol}/relationships
     Cache: TTL 10 phút
     Response: {nodes: [...], edges: [...]}  # Corporate relationship graph
```

#### 2.3 Portfolio Analytics

```
POST /api/v1/portfolio/optimize
     Body: {
       symbols: ["AAPL","MSFT",...],
       method: "mean_variance"|"risk_parity"|"black_litterman"|"min_variance",
       constraints?: {min_weight?, max_weight?, target_return?},
       start_date?: string,
       end_date?: string
     }
     Response: {weights: {AAPL: 0.3, ...}, expected_return, volatility, sharpe_ratio}

POST /api/v1/portfolio/metrics
     Body: {
       holdings: [{symbol, weight}],
       start_date, end_date,
       benchmark?: string  # e.g. "SPY"
     }
     Response: {
       total_return, annualized_return, volatility, sharpe, sortino,
       max_drawdown, var_95, cvar_95, beta, alpha, information_ratio
     }

POST /api/v1/portfolio/backtest
     Body: {
       holdings: [{symbol, weight}],
       start_date, end_date,
       rebalance_freq?: "monthly"|"quarterly"|"annual"
     }
     Response: {
       equity_curve: [{date, value}],
       metrics: {...},
       drawdown_series: [{date, drawdown}]
     }

POST /api/v1/portfolio/var
     Body: {holdings, confidence_level?: 0.95, method?: "historical"|"parametric"|"monte_carlo"}
     Response: {var, cvar, confidence_level, method}
```

#### 2.4 Derivatives & F&O

```
GET  /api/v1/derivatives/chain/{symbol}
     Query: ?expiry=2025-06-27&broker=zerodha
     Cache: TTL 5s
     Response: {
       underlying, spot, expiry,
       calls: [{strike, ltp, iv, delta, gamma, theta, vega, oi, volume}],
       puts: [{...}],
       pcr, max_pain, atm_iv
     }

POST /api/v1/derivatives/greeks
     Body: {
       S: float,        # spot price
       K: float,        # strike
       T: float,        # time to expiry (years)
       r: float,        # risk-free rate
       sigma: float,    # volatility
       q?: float,       # dividend yield
       option_type: "call"|"put",
       model?: "bsm"|"binomial"
     }
     Response: {price, delta, gamma, theta, vega, rho, iv}

POST /api/v1/derivatives/implied-vol
     Body: {S, K, T, r, market_price, option_type, q?}
     Response: {implied_vol, model: "bsm"}

GET  /api/v1/derivatives/fii-dii
     Query: ?days=30
     Cache: TTL 30 phút
     Response: {data: [{date, fii_buy, fii_sell, fii_net, dii_buy, dii_sell, dii_net}]}
```

#### 2.5 Technical Analysis

```
POST /api/v1/technical/indicators
     Body: {
       symbol: string,
       indicators: ["RSI","MACD","BB","EMA20","SMA50"],
       period?: "1y",
       interval?: "1d"
     }
     Cache: TTL 1 phút
     Response: {symbol, bars: [{date, close, RSI, MACD_line, MACD_signal, ...}]}

POST /api/v1/technical/signals
     Body: {symbol, strategy?: "momentum"|"mean_reversion"|"breakout"}
     Response: {symbol, signal: "buy"|"sell"|"hold", confidence, reasoning}
```

### Tasks Phase 2

- [x] **P2-T1** Pydantic models cho tất cả request/response
- [x] **P2-T2** Implement market data endpoints (quote, history, search)
  - Wrap `yfinance_data.py`, `polygon_io_data.py`, `finnhub_data.py`
  - Cache với Redis TTL 5s cho quotes
- [x] **P2-T3** Implement equity research endpoints
  - Wrap `yfinance_data.py` (info, financials)
  - Implement DCF endpoint (gọi Python analytics)
- [x] **P2-T4** Implement portfolio analytics endpoints
  - Wrap `optimize_portfolio_weights.py`, `quantstats_analysis.py`
- [x] **P2-T5** Implement derivatives endpoints
  - Wrap `derivatives_pricing.py` (đã có BSM, Greeks, IV)
  - Wrap `option_greeks_daemon.py` cho batch Greeks
- [x] **P2-T6** Implement technical analysis endpoints
  - Wrap `compute_technicals.py`, `equity_talipp.py`
- [x] **P2-T7** Batch quote endpoint với concurrent fetching
- [x] **P2-T8** Cache strategy: Redis cho hot data, TTL theo DataHub policies
- [x] **P2-T9** Tests: unit + integration cho 5 endpoint groups
- [x] **P2-T10** Postman collection *(export từ /docs sau khi có API keys)*

### Deliverables Phase 2
- [x] 25+ endpoints hoạt động
- [x] Quote endpoint với TTL 5s cache
- [x] DCF endpoint hoạt động
- [x] Greeks endpoint hoạt động

---

---

## PHASE 3 — QUANTLIB SUITE API

> **Mục tiêu:** Expose pricing, risk, stochastic modeling, fixed income analytics
> **Thời gian:** Tuần 6–7 (10 ngày)
> **Trạng thái:** ✅ Hoàn thành
> **Dependency:** Phase 0 hoàn thành + Sign-off ✅
> **Test Gate:** ✅ Passed (14/14) | **Code Review:** ✅ | **Sign-off:** ✅

### Phân tích hiện trạng

`derivatives_pricing.py` đã implement:
- Black-Scholes pricing + Greeks (scipy-based, không cần QuantLib C++)
- Implied volatility (Brent solver)
- FX option (Garman-Kohlhagen)
- IRS swap valuation
- CDS valuation
- Forward/futures pricing

`financepy_wrapper.py` bổ sung:
- Bond pricing, YTM, duration, convexity
- Stochastic models (GBM, Heston, Hull-White)

### Endpoints cần implement

#### 3.1 Option Pricing

```
POST /api/v1/quant/option/price
     Body: {
       S: float, K: float, T: float, r: float, sigma: float,
       q?: float, option_type: "call"|"put",
       model: "bsm"|"binomial"|"monte_carlo"
     }
     Response: {price, model, inputs: {...}}

POST /api/v1/quant/option/greeks
     Body: {S, K, T, r, sigma, q?, option_type}
     Response: {price, delta, gamma, theta, vega, rho}

POST /api/v1/quant/option/implied-vol
     Body: {S, K, T, r, market_price, option_type, q?}
     Response: {implied_vol, iterations, converged}

POST /api/v1/quant/option/fx
     Body: {S, K, T, r_d, r_f, sigma, option_type}
     Response: {price, delta, gamma, theta, vega}

POST /api/v1/quant/option/batch-greeks
     Body: {
       contracts: [{S, K, T, r, sigma, option_type, token?}],
       model?: "bsm"
     }
     Response: {results: [{token?, price, delta, gamma, theta, vega, rho, iv}]}
```

#### 3.2 Fixed Income

```
POST /api/v1/quant/bond/price
     Body: {
       face_value: float,
       coupon_rate: float,
       maturity_years: float,
       ytm: float,
       frequency?: 1|2|4  # annual/semi/quarterly
     }
     Response: {price, accrued_interest, clean_price, dirty_price}

POST /api/v1/quant/bond/ytm
     Body: {face_value, coupon_rate, maturity_years, clean_price, frequency?}
     Response: {ytm, duration_modified, duration_macaulay, convexity, dv01}

POST /api/v1/quant/bond/duration
     Body: {face_value, coupon_rate, maturity_years, ytm, frequency?}
     Response: {
       macaulay_duration, modified_duration, effective_duration,
       convexity, dv01, pvbp
     }

POST /api/v1/quant/yield-curve/bootstrap
     Body: {
       instruments: [{maturity, rate, type: "deposit"|"swap"|"bond"}]
     }
     Response: {curve: [{maturity, zero_rate, discount_factor}]}
```

#### 3.3 Swap & Credit

```
POST /api/v1/quant/swap/irs
     Body: {
       notional: float,
       fixed_rate: float,
       tenor_years: float,
       payment_freq?: 2|4,
       discount_curve?: [{maturity, rate}]
     }
     Response: {npv, fixed_leg_pv, float_leg_pv, dv01, par_rate}

POST /api/v1/quant/swap/cds
     Body: {
       notional: float,
       spread_bps: float,
       tenor_years: float,
       recovery_rate?: float,
       risk_free_rate?: float
     }
     Response: {npv, protection_leg_pv, premium_leg_pv, par_spread_bps}
```

#### 3.4 Risk Models

```
POST /api/v1/quant/risk/var
     Body: {
       returns: [float],           # historical return series
       confidence_level?: 0.95,
       method: "historical"|"parametric"|"monte_carlo",
       horizon_days?: 1
     }
     Response: {var, cvar, confidence_level, method, horizon_days}

POST /api/v1/quant/risk/stress-test
     Body: {
       portfolio: [{symbol, weight}],
       scenarios: [
         {name: "2008 Crisis", shocks: {equity: -0.4, vol: 2.0}},
         {name: "Rate +200bps", shocks: {rates: 0.02}}
       ]
     }
     Response: {results: [{scenario, portfolio_pnl, pct_change}]}

POST /api/v1/quant/risk/credit
     Body: {
       exposure: float,
       pd: float,          # probability of default
       lgd: float,         # loss given default
       ead?: float         # exposure at default
     }
     Response: {expected_loss, unexpected_loss, cva, rwa}
```

#### 3.5 Stochastic Models

```
POST /api/v1/quant/stochastic/gbm
     Body: {
       S0: float, mu: float, sigma: float,
       T: float, n_paths: int, n_steps: int,
       seed?: int
     }
     Response: {
       paths: [[float]],    # shape: n_paths × n_steps
       statistics: {mean_final, std_final, percentile_5, percentile_95}
     }

POST /api/v1/quant/stochastic/heston
     Body: {S0, v0, kappa, theta, sigma_v, rho, r, T, K, option_type}
     Response: {price, implied_vol}

POST /api/v1/quant/stochastic/hull-white
     Body: {r0, a, sigma, T, n_paths, n_steps}
     Response: {paths: [[float]], mean_path: [float]}
```

#### 3.6 Volatility

```
POST /api/v1/quant/vol/surface
     Body: {
       spot: float,
       strikes: [float],
       expiries: [float],
       market_vols: [[float]]  # matrix: len(expiries) × len(strikes)
     }
     Response: {
       surface: [{strike, expiry, iv}],
       atm_vols: [{expiry, iv}]
     }

POST /api/v1/quant/vol/sabr
     Body: {F, K, T, alpha, beta, rho, nu}
     Response: {implied_vol, price}
```

### Tasks Phase 3

- [x] **P3-T1** Pydantic models cho tất cả QuantLib request/response
- [x] **P3-T2** Implement option pricing endpoints
  - Wrap `derivatives_pricing.py` functions via subprocess
  - Batch Greeks endpoint (500 contracts)
- [x] **P3-T3** Implement fixed income endpoints
  - Wrap `financepy_wrapper.py`
  - Yield curve bootstrap
- [x] **P3-T4** Implement swap & credit endpoints
- [x] **P3-T5** Implement risk model endpoints
  - VaR: historical, parametric, Monte Carlo
  - Stress testing framework
- [x] **P3-T6** Implement stochastic model endpoints
  - GBM simulation, Heston, Hull-White via financepy
- [x] **P3-T7** Implement volatility surface endpoints (vol surface + SABR)
- [x] **P3-T8** Cache strategy: TTL 60s cho option prices
- [x] **P3-T9** Tests: 14 tests covering all endpoint groups
- [x] **P3-T10** Postman collection *(export từ /docs)*

### Deliverables Phase 3
- [x] 20+ endpoints hoạt động
- [x] Option pricing, Greeks, IV endpoints
- [x] Bond pricing, YTM, duration endpoints
- [x] VaR, stress test, credit risk endpoints

---

---

## PHASE 4 — GLOBAL INTELLIGENCE API

> **Mục tiêu:** Expose geopolitics, maritime, economics, government data
> **Thời gian:** Tuần 8–9 (10 ngày)
> **Trạng thái:** ✅ Hoàn thành
> **Dependency:** Phase 0 hoàn thành + Sign-off ✅
> **Test Gate:** ✅ Passed (15/15) | **Code Review:** ✅ | **Sign-off:** ✅

### Phân tích hiện trạng

Tất cả data fetchers đã là standalone Python scripts với JSON output:
- `acled_data.py` — conflict events
- `hdx_data.py` — humanitarian data
- `marinetraffic_data.py`, `aisstream_data.py` — maritime
- `fred_data.py`, `worldbank_data.py`, `imf_data.py` — economics
- 50+ government data scripts

### Endpoints cần implement

#### 4.1 Geopolitics

```
GET  /api/v1/intelligence/geopolitics/events
     Query: ?country=Ukraine&category=battles&limit=50&days=30
     Cache: TTL 2 phút
     Response: {
       events: [{
         event_id, event_date, event_type, country, admin1, location,
         latitude, longitude, fatalities, notes, source
       }],
       total, credits_used
     }

GET  /api/v1/intelligence/geopolitics/countries
     Cache: TTL 10 phút
     Response: {countries: [{name, iso, event_count, fatalities}]}

GET  /api/v1/intelligence/geopolitics/categories
     Cache: TTL 10 phút
     Response: {categories: [{name, count}]}

GET  /api/v1/intelligence/geopolitics/hdx/{context}
     # context: conflicts|humanitarian|country:{iso}|topic:{slug}|search:{q}
     Cache: TTL 1 giờ
     Response: {datasets: [...], resources: [...]}

GET  /api/v1/intelligence/geopolitics/trade
     Query: ?kind=benefits|restrictions&country=
     Cache: TTL 15 phút
     Response: {items: [{country, type, description, date}]}

GET  /api/v1/intelligence/geopolitics/relationships/{ticker}
     Cache: TTL 10 phút
     Response: {nodes: [{id, label, type}], edges: [{source, target, relation}]}
```

#### 4.2 Maritime

```
GET  /api/v1/intelligence/maritime/vessel/{imo}
     Cache: TTL 1 phút
     Response: {
       imo, mmsi, name, flag, vessel_type,
       latitude, longitude, speed, course, heading,
       destination, eta, last_update
     }

POST /api/v1/intelligence/maritime/vessels/batch
     Body: {imos: ["1234567", ...]}
     Cache: TTL 1 phút
     Response: {vessels: [{...}], found_count, not_found: [...]}

POST /api/v1/intelligence/maritime/vessels/area
     Body: {
       lat_min: float, lat_max: float,
       lon_min: float, lon_max: float,
       vessel_type?: string
     }
     Cache: TTL 1 phút
     Response: {vessels: [...], total_count}

GET  /api/v1/intelligence/maritime/vessel/{imo}/history
     Query: ?days=7
     Cache: TTL 5 phút
     Response: {imo, history: [{timestamp, lat, lon, speed, course}], total_records}
```

#### 4.3 Economics

```
GET  /api/v1/intelligence/economics/fred/{series_id}
     Query: ?start=2020-01-01&end=2025-01-01&frequency=m
     Cache: TTL 1 giờ
     Response: {
       series_id, title, units, frequency,
       observations: [{date, value}]
     }

GET  /api/v1/intelligence/economics/fred/search
     Query: ?q=inflation&limit=20
     Cache: TTL 1 giờ
     Response: {series: [{id, title, units, frequency, last_updated}]}

GET  /api/v1/intelligence/economics/worldbank/{indicator}/{country}
     Query: ?start=2010&end=2024
     Cache: TTL 1 giờ
     Response: {indicator, country, data: [{year, value}]}

GET  /api/v1/intelligence/economics/imf/{dataset}/{series}
     Cache: TTL 1 giờ
     Response: {dataset, series, data: [{period, value}]}

GET  /api/v1/intelligence/economics/oecd/{dataset}
     Query: ?country=USA&subject=&measure=
     Cache: TTL 1 giờ
     Response: {dataset, observations: [...]}

GET  /api/v1/intelligence/economics/dbnomics/{provider}/{dataset}/{series}
     Cache: TTL 1 giờ
     Response: {provider, dataset, series, observations: [{period, value}]}

GET  /api/v1/intelligence/economics/calendar
     Query: ?limit=25&country=
     Cache: TTL 5 phút
     Response: {
       events: [{
         event, country, date, time, importance,
         actual, forecast, previous
       }]
     }

GET  /api/v1/intelligence/economics/central-banks/{bank}
     # bank: fed|ecb|boj|boe|rba|snb|boc|riksbank|norges|nbp|bnm|bcb
     Query: ?series=policy_rate&start=2020-01-01
     Cache: TTL 1 giờ
     Response: {bank, series, data: [{date, value}]}
```

#### 4.4 Government Data

```
GET  /api/v1/intelligence/govdata/{country}/{dataset}
     # country: us|eu|uk|de|au|sg|hk|ca|fr|jp
     # dataset: depends on country (e.g. us/census, us/bls, eu/eurostat)
     Query: ?params (dataset-specific)
     Cache: TTL 1 giờ
     Response: {country, dataset, data: {...}}

GET  /api/v1/intelligence/govdata/us/bls/{series_id}
     Cache: TTL 1 giờ
     Response: {series_id, data: [{year, period, value}]}

GET  /api/v1/intelligence/govdata/us/fred-categories
     Cache: TTL 24 giờ
     Response: {categories: [{id, name, parent_id}]}
```

#### 4.5 Energy & Environment

```
GET  /api/v1/intelligence/energy/eia/{category}
     # category: petroleum|natural_gas|electricity|steo
     Query: ?series_id=&start=&end=
     Cache: TTL 1 giờ
     Response: {category, series: [{id, name, data: [{date, value}]}]}

GET  /api/v1/intelligence/environment/co2
     Query: ?country=&start=2000&end=2024
     Cache: TTL 24 giờ
     Response: {data: [{country, year, co2, co2_per_capita}]}

GET  /api/v1/intelligence/environment/climate-trace
     Query: ?sector=&country=
     Cache: TTL 24 giờ
     Response: {emissions: [...]}
```

### Tasks Phase 4

- [x] **P4-T1** Pydantic models cho tất cả request/response
- [x] **P4-T2** Implement geopolitics endpoints
  - Wrap `acled_data.py`, `hdx_data.py`, `relationship_map.py`
  - Handle ACLED API key injection
- [x] **P4-T3** Implement maritime endpoints
  - Wrap `marinetraffic_data.py`, `aisstream_data.py`
  - Handle MarineTraffic API key
- [x] **P4-T4** Implement economics endpoints
  - Wrap `fred_data.py`, `worldbank_data.py`, `imf_data.py`, `oecd_data.py`
- [x] **P4-T5** Implement macro calendar endpoint
  - Wrap `economic_calendar.py`
- [x] **P4-T6** Implement central bank endpoints (12 banks: fed, ecb, boj, boe, rba, snb, boc, riksbank, norges, nbp, bnm, bcb)
- [x] **P4-T7** Implement government data endpoints
  - Wrap `bls_data.py`, `census_data.py`, `eurostat_data.py`
- [x] **P4-T8** Implement energy & environment endpoints (EIA, CO2/OWID)
- [x] **P4-T9** Cache strategy: TTL 2min (events), 1h (economics), 24h (environment)
- [x] **P4-T10** API key management: FRED, MarineTraffic, ACLED keys từ env vars
- [x] **P4-T11** Tests: 15 tests covering geopolitics, maritime, economics, govdata

### Deliverables Phase 4
- [x] 20+ endpoints hoạt động
- [x] FRED series endpoint với TTL 1h cache
- [x] Maritime vessel lookup endpoint
- [x] Geopolitics events với country/category filter

---

---

## PHASE 5 — AI QUANT LAB API

> **Mục tiêu:** Expose Qlib ML models, backtesting, factor discovery, RL trading
> **Thời gian:** Tuần 10–12 (15 ngày)
> **Trạng thái:** ✅ Hoàn thành
> **Dependency:** Phase 0 hoàn thành + Sign-off ✅
> **Lưu ý:** Module này có long-running tasks → dùng asyncio.create_task + Redis job store
> **Test Gate:** ✅ Passed (12/12) | **Code Review:** ✅ | **Sign-off:** ✅

### Phân tích hiện trạng

16 Qlib scripts trong `scripts/ai_quant_lab/`:
- `qlib_service.py` — main service với model training/prediction
- `qlib_advanced_backtest.py` — backtesting engine
- `qlib_rl.py` — RL trading (PPO, SAC, TD3)
- `qlib_portfolio_opt.py` — portfolio optimization
- `qlib_feature_engineering.py` — factor discovery
- `qlib_reporting.py` — tearsheet generation
- Và 10 scripts khác

**Vấn đề:** Training ML models có thể mất 5-60 phút → cần async job pattern

### Kiến trúc Async Jobs

```
Client → POST /api/v1/quant-lab/jobs/backtest
              → {job_id: "abc123", status: "queued"}

Client → GET  /api/v1/quant-lab/jobs/{job_id}
              → {job_id, status: "running", progress: 45, eta_seconds: 120}

Client → GET  /api/v1/quant-lab/jobs/{job_id}/result
              → {job_id, status: "completed", result: {...}}

Client → WS   /api/v1/quant-lab/jobs/{job_id}/stream
              → real-time progress events
```

### Endpoints cần implement

#### 5.1 Job Management

```
GET  /api/v1/quant-lab/jobs
     Query: ?status=running|completed|failed&limit=20
     Response: {jobs: [{job_id, type, status, created_at, completed_at}]}

GET  /api/v1/quant-lab/jobs/{job_id}
     Response: {
       job_id, type, status: "queued"|"running"|"completed"|"failed",
       progress: 0-100, eta_seconds, created_at, started_at, completed_at,
       error?
     }

GET  /api/v1/quant-lab/jobs/{job_id}/result
     Response: {job_id, status, result: {...}}

DELETE /api/v1/quant-lab/jobs/{job_id}
     Response: {cancelled: bool}

WS   /api/v1/quant-lab/jobs/{job_id}/stream
     Events: {type: "progress"|"log"|"result"|"error", data: {...}}
```

#### 5.2 Backtesting

```
POST /api/v1/quant-lab/backtest
     Body: {
       strategy: {
         type: "momentum"|"mean_reversion"|"ml_signal"|"custom",
         params: {...}
       },
       universe: {
         symbols?: ["AAPL","MSFT"],
         market?: "us"|"cn"|"in",
         index?: "SP500"|"NIFTY50"
       },
       start_date: "2020-01-01",
       end_date: "2024-12-31",
       initial_capital?: 1000000,
       transaction_cost?: 0.001,
       benchmark?: "SPY"
     }
     Response: {job_id, status: "queued"}

# Result format (via GET /jobs/{id}/result):
{
  "equity_curve": [{date, portfolio_value, benchmark_value}],
  "metrics": {
    "total_return", "annualized_return", "volatility",
    "sharpe_ratio", "sortino_ratio", "max_drawdown",
    "calmar_ratio", "win_rate", "profit_factor",
    "avg_trade_return", "num_trades"
  },
  "trades": [{date, symbol, action, price, quantity, pnl}],
  "monthly_returns": [{year, month, return}]
}
```

#### 5.3 Model Training & Prediction

```
POST /api/v1/quant-lab/models/train
     Body: {
       model_type: "lightgbm"|"xgboost"|"lstm"|"gru"|"transformer"|"linear",
       universe: {market, symbols?, index?},
       features: "Alpha158"|"Alpha360"|[custom_features],
       start_date, end_date,
       hyperparams?: {...},
       label?: {type: "return", horizon: 5}
     }
     Response: {job_id, status: "queued"}

POST /api/v1/quant-lab/models/{model_id}/predict
     Body: {
       symbols: ["AAPL","MSFT"],
       date?: "2025-05-18"  # default: latest
     }
     Response: {
       predictions: [{symbol, score, rank, signal: "buy"|"sell"|"hold"}],
       model_id, prediction_date
     }

GET  /api/v1/quant-lab/models
     Response: {models: [{model_id, type, trained_at, metrics: {ic, icir}}]}

GET  /api/v1/quant-lab/models/{model_id}
     Response: {model_id, type, config, metrics, feature_importance: [...]}
```

#### 5.4 Factor Discovery

```
POST /api/v1/quant-lab/factors/discover
     Body: {
       universe: {market, symbols?},
       start_date, end_date,
       method?: "alpha158"|"alpha360"|"genetic"|"ml_based"
     }
     Response: {job_id}

# Result:
{
  "factors": [{
    "name", "formula", "ic", "icir", "turnover",
    "sharpe", "decay_days", "category"
  }],
  "top_factors": [...]
}

POST /api/v1/quant-lab/factors/evaluate
     Body: {
       factor_data: [{date, symbol, value}],
       universe, start_date, end_date
     }
     Response: {job_id}

# Result:
{
  "ic_series": [{date, ic}],
  "ic_mean", "icir", "rank_ic", "rank_icir",
  "decay": [{lag, ic}],
  "quantile_returns": [{quantile, return}]
}
```

#### 5.5 Portfolio Optimization (Qlib-based)

```
POST /api/v1/quant-lab/portfolio/optimize
     Body: {
       signals: [{symbol, score}],  # from model predictions
       method: "mean_variance"|"risk_parity"|"black_litterman"|"hrp",
       constraints: {
         max_weight?: 0.1,
         min_weight?: 0.0,
         max_turnover?: 0.3,
         sector_limits?: {Technology: 0.3}
       },
       risk_model?: "sample"|"ledoit_wolf"|"factor"
     }
     Response: {
       weights: {AAPL: 0.05, ...},
       expected_return, expected_volatility, sharpe_ratio,
       turnover, num_positions
     }
```

#### 5.6 RL Trading

```
POST /api/v1/quant-lab/rl/train
     Body: {
       algorithm: "PPO"|"SAC"|"TD3",
       environment: {
         symbols: ["AAPL","MSFT"],
         start_date, end_date,
         initial_capital?: 100000,
         transaction_cost?: 0.001
       },
       training: {
         total_timesteps?: 100000,
         n_envs?: 4,
         learning_rate?: 0.0003
       }
     }
     Response: {job_id}

# Streaming events during training:
{event: "progress", episode: 100, reward: 1.23, sharpe: 0.8, progress: 10}

POST /api/v1/quant-lab/rl/{model_id}/backtest
     Body: {symbols, start_date, end_date}
     Response: {job_id}
```

#### 5.7 Reporting & Analytics

```
POST /api/v1/quant-lab/report/tearsheet
     Body: {
       returns: [{date, return}],
       benchmark_returns?: [{date, return}],
       title?: string
     }
     Response: {job_id}

# Result: {html_report: "base64...", metrics: {...}}

POST /api/v1/quant-lab/report/factor-attribution
     Body: {
       portfolio_returns: [{date, return}],
       factor_returns: {momentum: [...], value: [...], quality: [...]}
     }
     Response: {
       attribution: [{factor, contribution, t_stat}],
       r_squared, alpha, residual_return
     }
```

### Tasks Phase 5

- [x] **P5-T1** Setup async job system với Redis (asyncio.create_task, không cần Celery)
  - Job states: queued → running → completed/failed/cancelled
  - Job persistence trong Redis (TTL 24h)
  - WebSocket progress streaming
- [x] **P5-T2** Pydantic models cho tất cả request/response
- [x] **P5-T3** Implement job management endpoints (list, get, result, cancel, WS stream)
- [x] **P5-T4** Implement backtesting endpoint
  - Wrap `qlib_advanced_backtest.py`
  - Async job pattern (202 Accepted → job_id)
- [x] **P5-T5** Implement model training endpoint
  - Wrap `qlib_service.py`
  - Async job pattern
- [x] **P5-T6** Implement prediction endpoint (synchronous)
- [x] **P5-T7** Implement factor discovery endpoint
  - Wrap `qlib_feature_engineering.py`, `qlib_evaluation.py`
- [x] **P5-T8** Implement portfolio optimization endpoint
  - Wrap `qlib_portfolio_opt.py`
- [x] **P5-T9** Implement RL training endpoint
  - Wrap `qlib_rl.py`
  - Async job + WebSocket streaming
- [x] **P5-T10** Implement reporting endpoints
  - Wrap `qlib_reporting.py`
  - Tearsheet (async job), factor attribution (sync)
- [x] **P5-T11** Job cleanup: auto-delete via Redis TTL 24h
- [x] **P5-T12** Tests: 12 tests covering job management, backtest, training, RL, reporting
- [x] **P5-T13** Postman collection *(export từ /docs)*

### Lưu ý kỹ thuật Phase 5

- **Qlib data:** Cần pre-download Qlib data cho US/CN markets trước khi chạy
- **Model storage:** Lưu trained models vào `./models/{model_id}/` directory
- **Memory:** Training LSTM/Transformer cần 4-8GB RAM → cần resource limits
- **Timeout:** Training jobs không có timeout (user có thể cancel)
- **venv:** Qlib chạy trong `venv-numpy2`
- **Quyết định:** Dùng asyncio.create_task thay Celery — đơn giản hơn, đủ cho MVP

### Deliverables Phase 5
- [x] Async job system hoạt động (Redis-backed)
- [x] WebSocket `/jobs/{id}/stream` streaming progress
- [x] Backtest, model train, RL train endpoints (async jobs)
- [x] Predict, portfolio optimize, factor attribution (sync)

---

---

## PHASE 6 — INTEGRATION, DOCS & HARDENING

> **Mục tiêu:** OpenAPI docs, SDK generation, security hardening, performance tuning
> **Thời gian:** Tuần 13–14 (10 ngày)
> **Trạng thái:** ✅ Hoàn thành
> **Dependency:** Phase 1 + 2 + 3 + 4 + 5 tất cả Sign-off ✅
> **Test Gate:** ✅ Passed (27/27) | **Code Review:** ✅ | **Sign-off:** ✅

### Tasks Phase 6

- [x] **P6-T1** OpenAPI 3.0 documentation hoàn chỉnh
  - `app/openapi.py` — rich tag descriptions, examples, error schemas
  - Security schemes (ApiKeyAuth + BearerAuth)
  - Error codes documentation với enum
  - API description với provider table, rate limits, async job pattern

- [x] **P6-T2** SDK generation script
  - `scripts/generate_sdk.sh` — Python SDK + TypeScript/Axios SDK
  - Dùng openapi-generator-cli

- [x] **P6-T3** Security hardening
  - `core/security.py` — input sanitization (strings, symbols, dicts)
  - HMAC-SHA256 request signing + verification
  - Per-endpoint rate limit overrides (agent run: 10/min, model train: 1/min)
  - API key format validation + masking for logs

- [x] **P6-T4** Performance tuning
  - Per-endpoint rate limits (expensive endpoints stricter)
  - Prometheus metrics integration in middleware
  - `HTTP_IN_FLIGHT` gauge for concurrency monitoring

- [x] **P6-T5** Monitoring & Observability
  - `core/metrics.py` — Prometheus counters/histograms/gauges
  - `GET /metrics` endpoint (prometheus_client or no-op fallback)
  - Metrics: requests_total, request_duration, script_duration, cache_hits/misses, active_jobs
  - docker-compose profiles: `--profile monitoring` → Prometheus + Grafana
  - `deploy/prometheus.yml` scrape config

- [x] **P6-T6** Load testing
  - `tests/load/k6_health.js` — 100 users, p99 < 200ms
  - `tests/load/k6_market_data.js` — cache hit/miss latency tracking
  - `tests/load/k6_agents.js` — agent endpoints (rate-limited)

- [x] **P6-T7** Deployment
  - `Dockerfile` — multi-stage build (builder + runtime), non-root user
  - `docker-compose.yml` — api + redis + prometheus + grafana (profiles)
  - `deploy/k8s/deployment.yaml` — Kubernetes Deployment + Service + Ingress
  - Production: gunicorn + uvicorn workers

- [x] **P6-T8** Developer portal
  - `README.md` — full quickstart, auth guide, LLM providers table, API examples (curl), rate limits, error codes, project structure, monitoring guide

---

## TECHNICAL DECISIONS

### Stack chính thức

```
Language:     Python 3.11.9
Framework:    FastAPI 0.115+
ASGI Server:  Uvicorn + Gunicorn
Cache:        Redis 7+
Job Queue:    Celery 5+ (Phase 5 only)
Validation:   Pydantic v2
Auth:         python-jose (JWT) + custom API key
Testing:      pytest + httpx (async)
Linting:      ruff + mypy
```

### Python Runner — Thiết kế chi tiết

```python
# core/python_runner.py
import asyncio
import json
from pathlib import Path

class PythonRunner:
    def __init__(self, venv: str = "venv-numpy2", timeout: int = 60):
        self.venv = venv
        self.timeout = timeout
        self._semaphore = asyncio.Semaphore(10)  # max concurrent

    async def run(self, script: str, payload: dict, api_keys: dict = {}) -> dict:
        async with self._semaphore:
            env = self._build_env(api_keys)
            cmd = [self._python_path(), script, "--stdin"]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            stdin_data = json.dumps(payload).encode()
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(stdin_data),
                    timeout=self.timeout
                )
                return json.loads(stdout.decode())
            except asyncio.TimeoutError:
                proc.kill()
                raise TimeoutError(f"Script {script} timed out after {self.timeout}s")

    async def stream(self, script: str, payload: dict, api_keys: dict = {}):
        """Async generator yielding streaming lines"""
        env = self._build_env(api_keys)
        cmd = [self._python_path(), script, "--stream", "--stdin"]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )
        proc.stdin.write(json.dumps(payload).encode())
        proc.stdin.close()
        async for line in proc.stdout:
            yield line.decode().strip()
        await proc.wait()
```

### Cache Key Strategy

```
market:quote:{symbol}                    TTL: 5s
market:history:{symbol}:{interval}:{hash} TTL: 300s
equity:info:{symbol}                     TTL: 3600s
equity:dcf:{symbol}:{hash(params)}       TTL: 1800s
agents:list:{category}                   TTL: 300s
agents:discover                          TTL: 300s
intelligence:fred:{series_id}:{hash}     TTL: 3600s
intelligence:geopolitics:events:{hash}   TTL: 120s
intelligence:maritime:vessel:{imo}       TTL: 60s
quant:option:price:{hash(params)}        TTL: 60s
```

### Error Response Schema

```json
{
  "error": {
    "code": "SCRIPT_TIMEOUT",
    "message": "Script execution timed out after 60s",
    "details": {},
    "request_id": "req_abc123"
  }
}
```

**Error codes:**
- `AUTH_REQUIRED` — Missing or invalid API key
- `RATE_LIMITED` — Too many requests
- `SCRIPT_TIMEOUT` — Python script timed out
- `SCRIPT_ERROR` — Python script returned error
- `INVALID_PARAMS` — Request validation failed
- `EXTERNAL_API_ERROR` — Upstream data source error
- `MISSING_API_KEY` — Required external API key not configured
- `JOB_NOT_FOUND` — Async job ID not found
- `JOB_FAILED` — Async job failed

---

## DEPENDENCY MAP

```
Phase 0 (Foundation)
    ├── Phase 1 (AI Agents)       — độc lập sau P0
    ├── Phase 2 (Analytics)       — độc lập sau P0
    ├── Phase 3 (QuantLib)        — độc lập sau P0
    ├── Phase 4 (Intelligence)    — độc lập sau P0
    └── Phase 5 (Quant Lab)       — độc lập sau P0
                                     (cần Celery từ P0)
Phase 6 (Hardening)
    └── Tất cả phases trước hoàn thành
```

Phases 1–5 có thể chạy **song song** sau khi Phase 0 xong.

---

## EXTERNAL API KEYS CẦN CHUẨN BỊ

| Service | Dùng cho | Free tier | Link |
|---|---|---|---|
| OpenAI | AI Agents | $5 credit | platform.openai.com |
| Anthropic | AI Agents | $5 credit | console.anthropic.com |
| Polygon.io | Market data | 5 req/min | polygon.io |
| Finnhub | Market data, news | 60 req/min | finnhub.io |
| Alpha Vantage | Market data | 25 req/day | alphavantage.co |
| FRED | Economics | Free | fred.stlouisfed.org |
| MarineTraffic | Maritime | Paid | marinetraffic.com |
| ACLED | Geopolitics | Free (academic) | acleddata.com |
| Helius | Solana RPC | Free tier | helius.dev |

---

## CHECKLIST TỔNG KẾT

### Phase 0 — Foundation
- [x] Project skeleton tạo xong
- [x] Python subprocess bridge hoạt động
- [x] Auth middleware hoạt động
- [x] Redis cache hoạt động
- [x] Docker compose up thành công
- [x] CI pipeline chạy

### Phase 1 — AI Agents
- [x] 20+ endpoints hoạt động
- [x] SSE streaming hoạt động
- [x] Subprocess bridge test thành công
- [x] Paper trading bridge hoạt động
- [x] LLM: OpenAI-compatible API (model + base_url, provider auto-detect)

### Phase 2 — Multi-Asset Analytics
- [x] Quote endpoint với TTL 5s cache
- [x] DCF endpoint hoạt động
- [x] Greeks endpoint hoạt động
- [x] Portfolio optimization hoạt động

### Phase 3 — QuantLib Suite
- [x] Option pricing (BSM, Binomial, MC, FX)
- [x] Batch Greeks 500 contracts
- [x] Bond pricing, YTM, duration
- [x] VaR (3 methods), stress test, credit risk

### Phase 4 — Global Intelligence
- [x] FRED series fetch với TTL 1h cache
- [x] Geopolitics events với country/category filter
- [x] Maritime vessel lookup
- [x] Macro calendar hoạt động

### Phase 5 — AI Quant Lab
- [x] Async job system hoạt động (Redis + asyncio)
- [x] Backtest, model train, RL train (async jobs)
- [x] WebSocket streaming progress
- [x] Predict, portfolio optimize (sync)

### Phase 6 — Hardening
- [x] OpenAPI docs hoàn chỉnh (app/openapi.py — tags, descriptions, error schemas)
- [x] SDK generation script (scripts/generate_sdk.sh)
- [x] Security hardening (core/security.py — sanitization, HMAC, per-endpoint rate limits)
- [x] Prometheus metrics (core/metrics.py + /metrics endpoint)
- [x] k6 load test scripts (tests/load/)
- [x] Production Docker multi-stage build
- [x] Kubernetes manifests (deploy/k8s/)
- [x] Developer portal README hoàn chỉnh

---

### Thay đổi so với plan gốc

| Hạng mục | Plan gốc | Thực tế | Lý do |
|---|---|---|---|
| LLM config | `provider` + `model_id` bắt buộc | `model` + `base_url` (OpenAI-compat) | Linh hoạt hơn, hỗ trợ mọi provider |
| Job queue Phase 5 | Celery 5+ | asyncio.create_task + Redis | Đơn giản hơn, đủ cho MVP |
| Python version | 3.11.9 | 3.12.10 | 3.11.9 không có sẵn, 3.12 tương thích |
| structlog factory | PrintLoggerFactory | stdlib.LoggerFactory | add_logger_name cần .name attribute |

---

*Tài liệu này được cập nhật khi có tiến độ mới.*
*Cập nhật trạng thái: thay ⬜ → 🔄 → ✅ khi hoàn thành từng task.*

# BÁO CÁO TRIỂN KHAI & THIẾT KẾ UI — FINCEPT TERMINAL API

> **Ngày:** 20/05/2026 | **Phiên bản API:** 1.0.0
> **Trạng thái:** Production-ready — 146 tests passed, 16/17 endpoints integration test pass

---

## PHẦN 1 — HƯỚNG DẪN TRIỂN KHAI API

### 1.1 Tổng quan kiến trúc

```
Client (UI / Mobile / 3rd-party)
        │  REST + SSE + WebSocket
        ▼
  ┌─────────────────────────────────┐
  │   Fincept API (FastAPI)         │
  │   Port 8000                     │
  │   ├── Auth (X-API-Key / JWT)    │
  │   ├── Rate Limiter (Redis)      │
  │   ├── 5 Router modules          │
  │   └── Prometheus /metrics       │
  └──────────────┬──────────────────┘
                 │ subprocess bridge (JSON stdin/stdout)
        ┌────────┴────────┐
        │                 │
   ┌────▼────┐      ┌─────▼──────┐
   │ Redis   │      │ fincept-qt │
   │ Cache   │      │ /scripts   │
   │ + Jobs  │      │ (Python)   │
   └─────────┘      └────────────┘
```


### 1.2 Yêu cầu hệ thống

| Thành phần | Tối thiểu | Khuyến nghị |
|---|---|---|
| Python | 3.12+ | 3.12.x |
| Redis | 7.0+ | 7.4-alpine (Docker) |
| RAM | 2 GB | 4 GB |
| CPU | 2 cores | 4 cores |
| Disk | 5 GB | 20 GB (cho scripts + venv) |
| OS | Linux/Windows | Ubuntu 22.04 LTS |

**Dependencies bắt buộc:**
- `fincept-qt/scripts/` — thư mục scripts Python (bridge layer)
- `venv-numpy2` — Python venv chứa numpy, scipy, yfinance, pandas
- Redis instance (local hoặc managed)

---

### 1.3 Cài đặt từng bước

#### Bước 1 — Clone và chuẩn bị môi trường

```bash
cd fincept-api
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Linux/macOS
pip install -r requirements.txt
```

#### Bước 2 — Cấu hình `.env`

```env
# === BẮT BUỘC ===
SCRIPTS_DIR=../fincept-qt/scripts
VENV_NUMPY2_PYTHON=../fincept-qt/venv-numpy2/Scripts/python.exe  # Windows
# VENV_NUMPY2_PYTHON=../fincept-qt/venv-numpy2/bin/python        # Linux

REDIS_URL=redis://localhost:6379/0
MASTER_API_KEY=fincept_admin_<random_32hex>
JWT_SECRET_KEY=<random_64char_secret>

# === LLM (chọn 1 provider) ===
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=sk-...

# === DATA SOURCES (tùy chọn, mở thêm tính năng) ===
FRED_API_KEY=...          # kinh tế vĩ mô
FINNHUB_API_KEY=...       # tin tức, earnings
POLYGON_API_KEY=...       # market data premium
ALPHA_VANTAGE_API_KEY=... # backup market data
ACLED_API_KEY=...         # geopolitics
MARINETRAFFIC_API_KEY=... # maritime
```


#### Bước 3 — Khởi động Redis

```bash
# Docker (khuyến nghị)
docker run -d --name fincept-redis -p 6379:6379 redis:7.4-alpine

# Hoặc Docker Compose (API + Redis + Monitoring)
docker-compose up -d
docker-compose --profile monitoring up -d   # thêm Prometheus + Grafana
```

#### Bước 4 — Chạy API

```bash
# Development
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production (gunicorn + uvicorn workers)
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 --timeout 300

# Docker production
docker build -t fincept-api:latest .
docker run -d -p 8000:8000 --env-file .env fincept-api:latest
```

#### Bước 5 — Kiểm tra

```bash
# Health check
curl http://localhost:8000/health
# → {"status":"ok","version":"1.0.0","redis":"ok"}

# Swagger UI
open http://localhost:8000/docs

# Test quote
curl http://localhost:8000/api/v1/market/quote/AAPL
```

---

### 1.4 Kubernetes Deployment

File `deploy/k8s/deployment.yaml` đã có sẵn:
- 2 replicas mặc định (scale theo nhu cầu)
- Resource limits: 500m CPU, 512Mi RAM per pod
- Liveness probe: `GET /health` mỗi 30s
- Readiness probe: `GET /health` mỗi 10s
- Ingress với TLS termination

```bash
kubectl apply -f deploy/k8s/deployment.yaml
kubectl get pods -n fincept
```

---

### 1.5 Monitoring

| Service | URL | Mô tả |
|---|---|---|
| API Docs | `:8000/docs` | Swagger UI interactive |
| ReDoc | `:8000/redoc` | Tài liệu đẹp hơn |
| Prometheus | `:9090` | Metrics scraping |
| Grafana | `:3000` | Dashboard (admin/admin) |

**Metrics quan trọng:**
```
fincept_http_requests_total{method, path, status}
fincept_http_request_duration_seconds{method, path}
fincept_script_execution_duration_seconds{script}
fincept_cache_hits_total{module}
fincept_active_jobs
fincept_http_requests_in_flight
```


---

## PHẦN 2 — MÔ TẢ CHI TIẾT CÁC API

### 2.1 MODULE: AI AGENTS (`/api/v1/agents`)

Đây là module **quan trọng nhất** — expose AI agent framework với LLM tùy chọn.

#### Authentication
- Tất cả POST endpoints: `X-API-Key: fincept_<tier>_<key>`
- GET discovery endpoints: public (không cần key)

#### LLM Config (gửi kèm mọi request)
```json
{
  "model": "gpt-4o-mini",
  "api_key": "sk-...",
  "base_url": "https://api.openai.com/v1"
}
```
Hỗ trợ: OpenAI, Groq, Together, DeepSeek, Anthropic, Ollama, LM Studio, OpenRouter, Mistral.

#### Endpoints chi tiết

| Method | Path | Mô tả | Timeout | Cache |
|---|---|---|---|---|
| GET | `/` | Danh sách 54 agents | 60s | 5 phút |
| GET | `/list?category=` | Lọc theo category | 60s | 1 phút |
| POST | `/run` | Chạy 1 agent (one-shot) | 120s | — |
| POST | `/run/stream` | Chạy agent với SSE streaming | 120s | — |
| POST | `/team/run` | Chạy multi-agent team | 120s | — |
| POST | `/multi/run` | Query nhiều agents song song | 120s | — |
| POST | `/plan/stock` | Tạo plan phân tích cổ phiếu | 120s | — |
| POST | `/plan/portfolio` | Tạo plan phân tích portfolio | 120s | — |
| POST | `/plan/execute` | Thực thi plan đã tạo | 300s | — |
| POST | `/plan/dynamic` | Tạo plan từ câu hỏi tự nhiên | 120s | — |
| POST | `/analyze/stock` | Phân tích cổ phiếu đầy đủ | 120s | — |
| POST | `/analyze/portfolio` | Phân tích + rebalancing | 120s | — |
| POST | `/analyze/risk` | Đánh giá rủi ro portfolio | 120s | — |
| POST | `/analyze/macro` | Quét môi trường vĩ mô | 120s | — |
| POST | `/analyze/earnings` | Tóm tắt earnings | 120s | — |
| POST | `/analyze/sector-rotation` | Phân tích sector rotation | 120s | — |
| POST | `/paper/trade` | Thực hiện paper trade | 120s | — |
| GET | `/paper/portfolio/{id}` | Xem portfolio paper trading | 120s | — |
| GET | `/paper/positions/{id}` | Xem positions | 120s | — |
| POST | `/sessions` | Tạo session mới | — | — |
| GET | `/sessions/{id}` | Lấy session + lịch sử | — | — |
| POST | `/sessions/{id}/messages` | Thêm message vào session | — | — |
| DELETE | `/sessions/{id}` | Xóa session | — | — |

**SSE Streaming format:**
```
data: {"type": "thinking", "content": "Đang phân tích dữ liệu..."}
data: {"type": "token",    "content": "AAPL hiện đang giao dịch..."}
data: {"type": "tool",     "content": "Gọi yfinance_data.py"}
data: {"type": "done",     "content": "completed"}
```


---

### 2.2 MODULE: MULTI-ASSET ANALYTICS (`/api/v1/market`, `/equity`, `/portfolio`, `/derivatives`, `/technical`)

#### Market Data

| Method | Path | Mô tả | Cache TTL |
|---|---|---|---|
| GET | `/market/quote/{symbol}` | Giá real-time (yfinance/polygon/finnhub) | 5 giây |
| POST | `/market/quotes/batch` | Batch quotes nhiều mã | 5 giây |
| GET | `/market/history/{symbol}` | OHLCV lịch sử (interval: 1m→1mo) | 30s/5 phút |
| GET | `/market/search?q=` | Tìm kiếm mã chứng khoán | — |
| GET | `/market/sectors` | Hiệu suất các sector | 5 phút |

#### Equity Research

| Method | Path | Mô tả | Cache TTL |
|---|---|---|---|
| GET | `/equity/{symbol}/info` | Fundamentals, ratios (P/E, P/B, ROE...) | 1 giờ |
| GET | `/equity/{symbol}/financials` | Income statement, balance sheet, cash flow | 1 giờ |
| POST | `/equity/{symbol}/dcf` | Định giá DCF (intrinsic value) | 30 phút |
| GET | `/equity/{symbol}/news` | Tin tức + sentiment | 5 phút |
| GET | `/equity/{symbol}/relationships` | Corporate relationship graph | 10 phút |

**DCF request:**
```json
{
  "growth_rate": 0.15,
  "discount_rate": 0.10,
  "terminal_growth": 0.025,
  "projection_years": 5
}
```

#### Portfolio Analytics

| Method | Path | Mô tả | Auth |
|---|---|---|---|
| POST | `/portfolio/optimize` | Tối ưu weights (mean-variance, risk-parity, black-litterman) | ✅ |
| POST | `/portfolio/metrics` | Sharpe, Sortino, Max Drawdown, Alpha, Beta | ✅ |
| POST | `/portfolio/backtest` | Equity curve, drawdown series | ✅ |
| POST | `/portfolio/var` | Value-at-Risk (historical/parametric/MC) | ✅ |

#### Derivatives & F&O

| Method | Path | Mô tả | Cache TTL |
|---|---|---|---|
| GET | `/derivatives/chain/{symbol}` | Options chain với Greeks đầy đủ | 5 giây |
| POST | `/derivatives/greeks` | Tính Greeks (BSM) | 60 giây |
| POST | `/derivatives/implied-vol` | Implied volatility (Brent solver) | — |
| GET | `/derivatives/fii-dii` | FII/DII activity data | 30 phút |

#### Technical Analysis

| Method | Path | Mô tả | Cache TTL |
|---|---|---|---|
| POST | `/technical/indicators` | RSI, MACD, BB, EMA, SMA, ATR... | 1 phút |
| POST | `/technical/signals` | Tín hiệu buy/sell/hold từ strategy | 1 phút |


---

### 2.3 MODULE: QUANTLIB SUITE (`/api/v1/quant`)

Module định lượng chuyên sâu — không cần QuantLib C++, dùng scipy + financepy.

#### Option Pricing

| Method | Path | Mô tả | Cache |
|---|---|---|---|
| POST | `/quant/option/price` | BSM / Binomial / Monte Carlo | 60s |
| POST | `/quant/option/greeks` | Delta, Gamma, Theta, Vega, Rho | 60s |
| POST | `/quant/option/implied-vol` | IV từ market price (Brent solver) | — |
| POST | `/quant/option/fx` | FX option (Garman-Kohlhagen) | — |
| POST | `/quant/option/batch-greeks` | Batch tới 500 contracts | — |

#### Fixed Income

| Method | Path | Mô tả |
|---|---|---|
| POST | `/quant/bond/price` | Dirty/clean price |
| POST | `/quant/bond/ytm` | YTM + Duration + Convexity + DV01 |
| POST | `/quant/bond/duration` | Macaulay, Modified, Effective duration |
| POST | `/quant/yield-curve/bootstrap` | Bootstrap zero-rate curve |

#### Swap & Credit

| Method | Path | Mô tả |
|---|---|---|
| POST | `/quant/swap/irs` | Interest Rate Swap valuation (NPV, DV01, par rate) |
| POST | `/quant/swap/cds` | Credit Default Swap valuation |

#### Risk Models

| Method | Path | Mô tả |
|---|---|---|
| POST | `/quant/risk/var` | VaR (historical / parametric / Monte Carlo) |
| POST | `/quant/risk/stress-test` | Portfolio stress testing với custom scenarios |
| POST | `/quant/risk/credit` | Credit risk: EL, UL, CVA, RWA |

#### Stochastic Models

| Method | Path | Mô tả | Timeout |
|---|---|---|---|
| POST | `/quant/stochastic/gbm` | Geometric Brownian Motion simulation | 60s |
| POST | `/quant/stochastic/heston` | Heston stochastic volatility | 60s |
| POST | `/quant/stochastic/hull-white` | Hull-White interest rate model | 60s |

#### Volatility

| Method | Path | Mô tả |
|---|---|---|
| POST | `/quant/vol/surface` | Volatility surface construction |
| POST | `/quant/vol/sabr` | SABR model implied volatility |


---

### 2.4 MODULE: GLOBAL INTELLIGENCE (`/api/v1/intelligence`)

Dữ liệu vĩ mô, địa chính trị, hàng hải — **điểm khác biệt lớn nhất** so với Bloomberg/Refinitiv.

#### Geopolitics (ACLED + HDX)

| Method | Path | Mô tả | Cache |
|---|---|---|---|
| GET | `/intelligence/geopolitics/events` | Sự kiện xung đột (ACLED) theo quốc gia/loại | 2 phút |
| GET | `/intelligence/geopolitics/countries` | Danh sách quốc gia + event count | 10 phút |
| GET | `/intelligence/geopolitics/categories` | Phân loại sự kiện | 10 phút |
| GET | `/intelligence/geopolitics/hdx/{context}` | Dữ liệu nhân đạo (HDX) | 1 giờ |
| GET | `/intelligence/geopolitics/relationships/{ticker}` | Corporate geopolitical map | 10 phút |

#### Maritime (MarineTraffic + AIS)

| Method | Path | Mô tả | Cache |
|---|---|---|---|
| GET | `/intelligence/maritime/vessel/{imo}` | Vị trí + thông tin tàu theo IMO | 1 phút |
| POST | `/intelligence/maritime/vessels/batch` | Batch lookup nhiều tàu | — |
| POST | `/intelligence/maritime/vessels/area` | Tàu trong bounding box địa lý | — |
| GET | `/intelligence/maritime/vessel/{imo}/history` | Lịch sử AIS track | 5 phút |

#### Economics (FRED, World Bank, IMF, OECD)

| Method | Path | Mô tả | Cache |
|---|---|---|---|
| GET | `/intelligence/economics/fred/{series_id}` | FRED series (GDP, CPI, Fed Funds...) | 1 giờ |
| GET | `/intelligence/economics/fred/search` | Tìm kiếm FRED series | 1 giờ |
| GET | `/intelligence/economics/worldbank/{indicator}/{country}` | World Bank indicators | 1 giờ |
| GET | `/intelligence/economics/imf/{dataset}/{series}` | IMF datasets | 1 giờ |
| GET | `/intelligence/economics/oecd/{dataset}` | OECD data | 1 giờ |
| GET | `/intelligence/economics/calendar` | Economic events calendar | 5 phút |
| GET | `/intelligence/economics/central-banks/{bank}` | 12 central banks (fed/ecb/boj/boe/rba...) | 1 giờ |

#### Government Data

| Method | Path | Mô tả |
|---|---|---|
| GET | `/intelligence/govdata/us/bls/{series_id}` | BLS labor statistics |
| GET | `/intelligence/govdata/{country}/{dataset}` | Generic gov data (us/eu) |

#### Energy & Environment

| Method | Path | Mô tả | Cache |
|---|---|---|---|
| GET | `/intelligence/energy/eia/{category}` | EIA energy data (petroleum/gas/electricity) | 1 giờ |
| GET | `/intelligence/environment/co2` | CO2 emissions (OWID) | 24 giờ |


---

### 2.5 MODULE: AI QUANT LAB (`/api/v1/quant-lab`)

Long-running ML tasks với async job pattern — submit → poll → result.

#### Job Management

| Method | Path | Mô tả |
|---|---|---|
| GET | `/quant-lab/jobs` | Danh sách jobs (filter by status) |
| GET | `/quant-lab/jobs/{id}` | Status + metadata của job |
| GET | `/quant-lab/jobs/{id}/result` | Kết quả khi completed |
| DELETE | `/quant-lab/jobs/{id}` | Cancel job |
| WS | `/quant-lab/jobs/{id}/stream` | WebSocket real-time progress |

**Job lifecycle:** `queued → running → completed | failed | cancelled`

#### Backtesting

| Method | Path | Timeout | Mô tả |
|---|---|---|---|
| POST | `/quant-lab/backtest` | 600s | Submit backtest job (Qlib-based) |

#### Model Training & Prediction

| Method | Path | Timeout | Mô tả |
|---|---|---|---|
| POST | `/quant-lab/models/train` | 3600s | Train ML model (async) |
| POST | `/quant-lab/models/{id}/predict` | 120s | Predict với model đã train (sync) |
| GET | `/quant-lab/models` | 30s | Danh sách models |
| GET | `/quant-lab/models/{id}` | 30s | Chi tiết + feature importance |

#### Factor Discovery

| Method | Path | Timeout | Mô tả |
|---|---|---|---|
| POST | `/quant-lab/factors/discover` | 1800s | Tự động khám phá alpha factors |
| POST | `/quant-lab/factors/evaluate` | 600s | Đánh giá factor IC, IR |

#### Portfolio Optimization & RL

| Method | Path | Timeout | Mô tả |
|---|---|---|---|
| POST | `/quant-lab/portfolio/optimize` | 120s | Qlib-based portfolio optimization (sync) |
| POST | `/quant-lab/rl/train` | 7200s | Train RL trading agent |
| POST | `/quant-lab/rl/{id}/backtest` | 600s | Backtest RL model |

#### Reporting

| Method | Path | Mô tả |
|---|---|---|
| POST | `/quant-lab/report/tearsheet` | Generate performance tearsheet (async) |
| POST | `/quant-lab/report/factor-attribution` | Factor attribution analysis (sync) |

---

### 2.6 SYSTEM ENDPOINTS

| Method | Path | Mô tả |
|---|---|---|
| GET | `/health` | Health check (API + Redis status) |
| GET | `/metrics` | Prometheus metrics |
| GET | `/docs` | Swagger UI |
| GET | `/redoc` | ReDoc |
| GET | `/openapi.json` | OpenAPI 3.0 schema |


---

## PHẦN 3 — THIẾT KẾ UI: CHỨC NĂNG & ƯU TIÊN

### 3.1 Kiến trúc UI đề xuất

```
┌─────────────────────────────────────────────────────────────┐
│  HEADER: Logo | Search | Notifications | Profile | Settings  │
├──────────┬──────────────────────────────────────────────────┤
│          │                                                    │
│ SIDEBAR  │              MAIN CONTENT AREA                    │
│          │                                                    │
│ • Home   │  ┌──────────────────────────────────────────┐    │
│ • Market │  │  Dynamic Panel (thay đổi theo route)     │    │
│ • AI     │  │                                          │    │
│ • Quant  │  │                                          │    │
│ • Intel  │  └──────────────────────────────────────────┘    │
│ • Lab    │                                                    │
│ • Paper  │                                                    │
└──────────┴──────────────────────────────────────────────────┘
```

---

### 3.2 CHỨC NĂNG ƯU TIÊN CAO NHẤT (Hero Features — kéo user)

Đây là những tính năng **không có ở Bloomberg Terminal thông thường** hoặc **vượt trội hơn** về UX.

---

#### 🥇 PRIORITY 1 — AI Chat Terminal (Killer Feature)

**Mô tả:** Chat với AI agent trực tiếp, streaming real-time, hỗ trợ mọi LLM provider.

**API sử dụng:**
- `POST /agents/run/stream` — SSE streaming
- `POST /agents/analyze/stock` — phân tích cổ phiếu
- `POST /agents/analyze/macro` — vĩ mô
- `GET /agents/` — danh sách agents

**UI cần:**
```
┌─────────────────────────────────────────────────────┐
│  🤖 Fincept AI Terminal                              │
│  Agent: [Dropdown: 54 agents] | Model: [GPT-4o ▼]  │
├─────────────────────────────────────────────────────┤
│                                                      │
│  [THINKING] Đang phân tích AAPL...                  │
│  [TOKEN] AAPL hiện giao dịch ở $298.51...           │
│  [TOOL] Gọi yfinance_data.py                        │
│  [DONE] Phân tích hoàn tất                          │
│                                                      │
│  ─────────────────────────────────────────────────  │
│  Kết quả: AAPL có P/E 28x, dưới trung bình ngành... │
│                                                      │
├─────────────────────────────────────────────────────┤
│  [Input] Hỏi gì đó...                    [Send ▶]  │
└─────────────────────────────────────────────────────┘
```

**Tại sao nổi bật:** User có thể dùng LLM của riêng họ (Groq miễn phí, Ollama local) — không bị lock-in.


---

#### 🥇 PRIORITY 1 — Global Intelligence Dashboard (Unique Differentiator)

**Mô tả:** Bản đồ thế giới real-time với conflict events, vessel tracking, economic indicators.

**API sử dụng:**
- `GET /intelligence/geopolitics/events` — conflict events
- `GET /intelligence/maritime/vessel/{imo}` — vessel tracking
- `GET /intelligence/economics/calendar` — economic calendar
- `GET /intelligence/economics/central-banks/{bank}` — central bank rates

**UI cần:**
```
┌─────────────────────────────────────────────────────┐
│  🌍 Global Intelligence Map                          │
│  [Filter: Conflicts | Maritime | Economics]          │
├─────────────────────────────────────────────────────┤
│                                                      │
│   [Interactive World Map]                           │
│   • 🔴 Conflict hotspots (ACLED)                   │
│   • 🚢 Vessel positions (MarineTraffic)             │
│   • 📊 Economic indicators overlay                  │
│                                                      │
├──────────────┬──────────────────────────────────────┤
│ Event Feed   │  Economic Calendar                   │
│ • Ukraine... │  • Fed Meeting: 2 ngày nữa           │
│ • Gaza...    │  • CPI US: Thứ 4                     │
│ • Sudan...   │  • ECB Rate: Thứ 5                   │
└──────────────┴──────────────────────────────────────┘
```

**Tại sao nổi bật:** Không có terminal nào kết hợp geopolitics + maritime + economics trong 1 view.

---

#### 🥇 PRIORITY 1 — Live Market Dashboard

**Mô tả:** Watchlist real-time với auto-refresh 5 giây.

**API sử dụng:**
- `GET /market/quote/{symbol}` — TTL 5s
- `POST /market/quotes/batch` — batch update
- `GET /market/sectors` — sector heatmap
- `POST /technical/signals` — buy/sell signals

**UI cần:**
```
┌──────────────────────────────────────────────────────┐
│  📈 Market Overview                    [+ Add Symbol] │
├──────────┬────────┬────────┬──────────┬──────────────┤
│ Symbol   │ Price  │ Change │ Volume   │ Signal       │
├──────────┼────────┼────────┼──────────┼──────────────┤
│ AAPL     │ 298.51 │ +0.22% │ 45.2M    │ 🟢 BUY      │
│ MSFT     │ 419.00 │ -0.10% │ 22.1M    │ 🟡 HOLD     │
│ NVDA     │ 875.20 │ +2.15% │ 89.3M    │ 🟢 BUY      │
├──────────┴────────┴────────┴──────────┴──────────────┤
│  [Sector Heatmap]  Tech +1.2% | Finance -0.3% | ...  │
└──────────────────────────────────────────────────────┘
```


---

### 3.3 CHỨC NĂNG QUAN TRỌNG (Core Features — giữ user)

---

#### 🥈 PRIORITY 2 — Stock Analysis Page

**Mô tả:** Trang phân tích cổ phiếu toàn diện — chart + fundamentals + AI analysis.

**API sử dụng:**
- `GET /market/history/{symbol}` — OHLCV chart
- `GET /equity/{symbol}/info` — fundamentals
- `GET /equity/{symbol}/financials` — báo cáo tài chính
- `POST /equity/{symbol}/dcf` — định giá DCF
- `GET /equity/{symbol}/news` — tin tức + sentiment
- `GET /equity/{symbol}/relationships` — corporate graph
- `POST /technical/indicators` — RSI, MACD, BB
- `POST /agents/analyze/stock` — AI analysis

**Layout:**
```
┌─────────────────────────────────────────────────────┐
│  AAPL — Apple Inc.  $298.51 (+0.22%)  [AI Analyze] │
├──────────────────────────┬──────────────────────────┤
│  [Candlestick Chart]     │  Fundamentals            │
│  [Volume bars]           │  P/E: 28.5x              │
│  [RSI / MACD overlay]    │  Market Cap: $2.3T       │
│                          │  DCF Value: $312 (+4.5%) │
├──────────────────────────┼──────────────────────────┤
│  News Feed               │  Corporate Graph         │
│  • Earnings beat...      │  [D3.js network viz]     │
│  • New iPhone...         │                          │
├──────────────────────────┴──────────────────────────┤
│  [AI Analysis Panel — streaming]                    │
└─────────────────────────────────────────────────────┘
```

---

#### 🥈 PRIORITY 2 — Portfolio Manager

**Mô tả:** Quản lý portfolio với optimization và risk metrics.

**API sử dụng:**
- `POST /portfolio/optimize` — tối ưu weights
- `POST /portfolio/metrics` — Sharpe, Sortino, Max DD
- `POST /portfolio/backtest` — equity curve
- `POST /portfolio/var` — VaR
- `POST /agents/analyze/portfolio` — AI rebalancing
- `POST /agents/analyze/risk` — AI risk assessment

**Tabs:**
1. **Holdings** — danh sách vị thế, P&L
2. **Optimization** — chọn method, xem weights đề xuất
3. **Performance** — equity curve, drawdown chart
4. **Risk** — VaR, stress test scenarios
5. **AI Advisor** — AI rebalancing suggestions

---

#### 🥈 PRIORITY 2 — Options & Derivatives Desk

**Mô tả:** Options chain, Greeks calculator, volatility surface.

**API sử dụng:**
- `GET /derivatives/chain/{symbol}` — options chain
- `POST /derivatives/greeks` — Greeks calculator
- `POST /derivatives/implied-vol` — IV calculator
- `POST /quant/option/price` — BSM/Binomial/MC pricing
- `POST /quant/vol/surface` — vol surface 3D
- `POST /quant/vol/sabr` — SABR model

**Layout:**
```
┌─────────────────────────────────────────────────────┐
│  Options Desk — AAPL  Spot: $298.51                 │
│  Expiry: [Jun 27 ▼]  [Greeks Calculator]            │
├──────────────────────────────────────────────────────┤
│  CALLS          │ Strike │ PUTS                      │
│  IV  Delta Price│        │ Price Delta  IV           │
│  25% 0.65  8.50 │  295   │  5.20 -0.35  24%         │
│  22% 0.50  5.20 │  300   │  7.80 -0.50  23%         │
├──────────────────────────────────────────────────────┤
│  [Volatility Surface — 3D Chart]                    │
└─────────────────────────────────────────────────────┘
```


---

#### 🥈 PRIORITY 2 — Economic Research Center

**Mô tả:** Dữ liệu kinh tế vĩ mô từ FRED, World Bank, IMF, OECD.

**API sử dụng:**
- `GET /intelligence/economics/fred/{series_id}` — FRED data
- `GET /intelligence/economics/fred/search` — tìm series
- `GET /intelligence/economics/worldbank/{indicator}/{country}` — World Bank
- `GET /intelligence/economics/central-banks/{bank}` — central banks
- `GET /intelligence/economics/calendar` — economic calendar
- `POST /agents/analyze/macro` — AI macro analysis

**Features:**
- Search 800,000+ FRED series
- So sánh indicators giữa các quốc gia
- Central bank policy rate tracker (12 banks)
- Economic calendar với importance filter
- AI macro scan button

---

#### 🥈 PRIORITY 2 — Paper Trading Simulator

**Mô tả:** Giao dịch giả lập với portfolio tracking.

**API sử dụng:**
- `POST /agents/paper/trade` — thực hiện trade
- `GET /agents/paper/portfolio/{id}` — xem portfolio
- `GET /agents/paper/positions/{id}` — xem positions
- `GET /market/quote/{symbol}` — giá real-time

**Features:**
- Mua/bán với giá real-time
- P&L tracking real-time
- Trade history
- Performance vs benchmark

---

### 3.4 CHỨC NĂNG NÂNG CAO (Power User Features)

---

#### 🥉 PRIORITY 3 — AI Quant Lab

**Mô tả:** ML backtesting, model training, factor discovery — dành cho quant traders.

**API sử dụng:** Toàn bộ `/quant-lab/*`

**UI pattern — Async Job:**
```
[Submit Job] → [Job ID: abc-123] → [Progress Bar: 45%] → [View Results]
                                    ↕ WebSocket stream
```

**Tabs:**
1. **Backtest** — submit strategy, xem equity curve
2. **Models** — train/predict ML models
3. **Factors** — discover alpha factors
4. **RL Trading** — train reinforcement learning agent
5. **Reports** — tearsheet, factor attribution

---

#### 🥉 PRIORITY 3 — Fixed Income & Rates

**Mô tả:** Bond pricing, yield curve, swap valuation.

**API sử dụng:**
- `POST /quant/bond/price` — bond pricing
- `POST /quant/bond/ytm` — YTM calculator
- `POST /quant/yield-curve/bootstrap` — yield curve
- `POST /quant/swap/irs` — IRS valuation
- `POST /quant/swap/cds` — CDS valuation

---

#### 🥉 PRIORITY 3 — Maritime Intelligence

**Mô tả:** Vessel tracking cho commodity traders và supply chain analysts.

**API sử dụng:** Toàn bộ `/intelligence/maritime/*`

**UI:**
- Map với vessel positions (Leaflet.js / Mapbox)
- Filter theo vessel type (tanker, bulk carrier, container)
- Click vessel → xem details + AIS history
- Bounding box search

---

#### 🥉 PRIORITY 3 — Risk Dashboard

**Mô tả:** Stress testing, credit risk, VaR aggregation.

**API sử dụng:**
- `POST /quant/risk/var` — VaR
- `POST /quant/risk/stress-test` — stress scenarios
- `POST /quant/risk/credit` — credit risk metrics
- `POST /portfolio/var` — portfolio VaR


---

## PHẦN 4 — PHÂN TÍCH CẠNH TRANH & ĐIỂM KHÁC BIỆT

### 4.1 So sánh với Bloomberg Terminal / Refinitiv

| Tính năng | Bloomberg | Refinitiv | Fincept |
|---|---|---|---|
| Giá | $24,000/năm | $22,000/năm | **Open source / self-host** |
| AI Agent tích hợp | ❌ | ❌ | ✅ 54 agents |
| Chọn LLM provider | ❌ | ❌ | ✅ 9 providers |
| Geopolitics (ACLED) | Partial | Partial | ✅ Full API |
| Maritime tracking | ✅ | ✅ | ✅ |
| QuantLib suite | ✅ | ✅ | ✅ |
| ML Backtesting (Qlib) | ❌ | ❌ | ✅ |
| RL Trading agent | ❌ | ❌ | ✅ |
| Factor discovery | ❌ | ❌ | ✅ |
| Self-hosted | ❌ | ❌ | ✅ |
| API access | $$$$ | $$$$ | **Free** |

---

### 4.2 Top 5 Điểm Khác Biệt Kéo User

**1. Bring Your Own LLM**
User dùng Groq (miễn phí), Ollama (local, offline), DeepSeek (rẻ) — không bị lock-in vào 1 provider. Đây là điểm **không có ở bất kỳ terminal nào**.

**2. Geopolitics + Maritime + Finance trong 1 platform**
Commodity traders, hedge funds cần theo dõi tàu chở dầu + xung đột địa chính trị + giá dầu cùng lúc. Fincept là platform duy nhất làm được điều này.

**3. AI Quant Lab với RL Trading**
Reinforcement learning trading agent, factor discovery tự động — tính năng chỉ có ở các quant funds lớn, nay accessible cho mọi người.

**4. Open Source + Self-Hosted**
Dữ liệu không đi qua server của bên thứ ba. Phù hợp với hedge funds, family offices cần data privacy.

**5. 100% API-first**
Mọi tính năng đều có API — developer có thể build custom UI, integrate vào workflow riêng, tạo alerts, automation.

---

### 4.3 Target User Segments

| Segment | Tính năng chính | API modules |
|---|---|---|
| Retail trader | Market data, AI chat, paper trading | agents, analytics |
| Quant analyst | QuantLib, backtesting, factor discovery | quantlib, quant-lab |
| Macro investor | Economics, central banks, geopolitics | intelligence |
| Commodity trader | Maritime, energy, geopolitics | intelligence |
| Risk manager | VaR, stress test, credit risk | quantlib, analytics |
| Developer | Full API access, SDK | All |


---

## PHẦN 5 — ROADMAP UI & TECHNICAL NOTES

### 5.1 Thứ tự build UI (đề xuất)

```
Sprint 1 (2 tuần):
  ✅ Auth (API key setup)
  ✅ Live Market Dashboard (watchlist + sector heatmap)
  ✅ Stock Chart + Basic Info

Sprint 2 (2 tuần):
  ✅ AI Chat Terminal (SSE streaming)
  ✅ Agent selector (54 agents)
  ✅ LLM provider config

Sprint 3 (2 tuần):
  ✅ Portfolio Manager (holdings + metrics)
  ✅ Paper Trading

Sprint 4 (2 tuần):
  ✅ Global Intelligence Map
  ✅ Economic Calendar
  ✅ FRED data explorer

Sprint 5 (2 tuần):
  ✅ Options Desk (chain + Greeks)
  ✅ Volatility Surface 3D

Sprint 6 (3 tuần):
  ✅ AI Quant Lab (async jobs UI)
  ✅ Backtest results visualization
  ✅ Maritime Map
```

---

### 5.2 Technical Notes cho UI Developer

**Polling vs WebSocket:**
- Market quotes: polling mỗi 5s (TTL cache = 5s)
- Agent streaming: SSE (`EventSource` API)
- Job progress: WebSocket (`/quant-lab/jobs/{id}/stream`)

**Rate Limits cần xử lý:**
```javascript
// Khi nhận 429, đọc header Retry-After
if (response.status === 429) {
  const retryAfter = response.headers.get('Retry-After'); // "60"
  // Show countdown timer
}
```

**Error handling chuẩn:**
```json
{
  "error": {
    "code": "SCRIPT_TIMEOUT",
    "message": "Script timed out after 60s",
    "details": {},
    "request_id": "uuid"
  }
}
```

**Authentication header:**
```javascript
headers: { 'X-API-Key': 'fincept_free_...' }
// hoặc JWT:
headers: { 'Authorization': 'Bearer eyJ...' }
```

**Async Job pattern:**
```javascript
// 1. Submit
const { job_id } = await POST('/quant-lab/backtest', body);

// 2. WebSocket stream
const ws = new WebSocket(`ws://api/quant-lab/jobs/${job_id}/stream`);
ws.onmessage = (e) => {
  const { status, progress } = JSON.parse(e.data);
  updateProgressBar(progress);
};

// 3. Get result
const { result } = await GET(`/quant-lab/jobs/${job_id}/result`);
```

---

### 5.3 Recommended Tech Stack cho UI

| Layer | Recommendation | Lý do |
|---|---|---|
| Framework | Next.js 14 (App Router) | SSR + streaming support |
| Charts | TradingView Lightweight Charts | Professional candlestick |
| 3D Charts | Plotly.js | Vol surface, 3D scatter |
| Maps | Mapbox GL / Leaflet | Maritime + geopolitics |
| Network Graph | D3.js / Cytoscape | Corporate relationships |
| State | Zustand | Lightweight, async-friendly |
| API Client | TanStack Query | Cache + polling built-in |
| SSE | Native EventSource API | Agent streaming |
| WebSocket | Native WebSocket | Job progress |
| UI Components | shadcn/ui + Tailwind | Dark theme terminal look |

---

## TÓM TẮT

**API đã hoàn thiện:** 100+ endpoints, 146 tests passed, production-ready.

**Để triển khai:** Cần Redis + fincept-qt/scripts + venv-numpy2. Docker Compose là cách nhanh nhất.

**Để build UI:** Bắt đầu với Live Market Dashboard + AI Chat Terminal — đây là 2 tính năng kéo user mạnh nhất và dễ demo nhất. Sau đó mở rộng sang Portfolio Manager và Global Intelligence Map.

**Điểm khác biệt cốt lõi:** Bring Your Own LLM + Geopolitics/Maritime + AI Quant Lab — không có terminal nào trên thị trường có cả 3 điều này cùng lúc.

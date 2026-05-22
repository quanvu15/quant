# BÁO CÁO: VIẾT LẠI 4 MODULE FINCEPT (PHÂN TÍCH / AGENT / CHATBOT / NEWS) THÀNH BACKEND ĐỘC LẬP

> **Ngày:** 20/05/2026
> **Câu hỏi của bạn:** "Để không liên quan tới pháp lý có thể viết lại fincept-qt không, chỉ viết lại các thành phần liên quan tới phân tích, Agent, chatbot và tin tức thôi."
>
> **Câu trả lời ngắn:** **Có**, hoàn toàn khả thi. Đây không phải dịch lại C++ Qt mà là viết lại Python pure 4 capability trên, dùng technology + công cụ open-source phổ biến. Tổng effort ~6–8 tuần cho MVP. Báo cáo này phân tích phạm vi, kiến trúc, effort và phương án triển khai sạch về pháp lý.

---

## 1. CƠ SỞ PHÁP LÝ — VÌ SAO VIẾT LẠI LÀ PHƯƠNG ÁN AN TOÀN

### 1.1 Vấn đề pháp lý hiện tại

| Repo | License | Vấn đề khi tích hợp với QuantDinger |
|---|---|---|
| FinceptTerminal (`fincept-qt` + `fincept-api`) | **AGPL-3.0 + Commercial của Fincept Corporation** | AGPL incompatible với Apache 2.0 của QuantDinger nếu phân phối. Commercial license thuộc Fincept Corp → cần xin phép. |
| `fincept-qt/scripts/agents/finagent_core/...` | Hầu hết import `agno` framework + có code của bên thứ ba | Phụ thuộc license của agno (Apache 2.0 — OK) nhưng config personas + persona_runtime + execution_planner là **code của Fincept** |
| QuantDinger backend | Apache 2.0 | Apache 2.0 không thể merge với AGPL nếu code AGPL được link cứng vào |

### 1.2 Quy tắc viết lại sạch (clean-room rewrite)

Để **không bị ràng buộc bởi AGPL hay commercial license của Fincept Corp**, code mới phải:

1. **Không copy-paste** trực tiếp source code từ `fincept-qt/scripts/`. Chỉ tham chiếu tài liệu công khai (README, design pattern, ý tưởng).
2. **Không reuse** các file `.json` config persona đặc thù của Fincept (vd: `agent_definitions.json` của TraderInvestorsAgent — đây là intellectual property của Fincept Corp).
3. **Dùng prompts mới**: persona Warren Buffett / Peter Lynch / Howard Marks là **public knowledge**, ai cũng có thể viết prompt riêng. Tự viết prompt từ đầu, không dùng prompt của Fincept.
4. **Dùng API public**: yfinance, FRED, ACLED, MarineTraffic — tất cả đều có Python SDK chính thức hoặc REST API public, không cần wrapper của Fincept.
5. **Dùng thư viện open-source standard**: agno, LangChain, LangGraph, LiteLLM, Prophet, FinBERT, spaCy — tất cả Apache 2.0 / MIT.
6. **Tạo repo mới hoàn toàn** với commit history sạch, license của bạn (Apache 2.0 hoặc MIT để compatible với QuantDinger).

→ Sau khi viết lại theo các quy tắc trên, **bạn là chủ sở hữu code mới**, không có ràng buộc với Fincept Corp.

### 1.3 Những gì có thể "kế thừa" hợp pháp

| Thành phần | Kế thừa được? | Lý do |
|---|---|---|
| Cấu trúc thư mục, naming convention | ✅ | Không có IP |
| Idea về JSON stdin/stdout protocol cho subprocess | ✅ | Pattern phổ biến |
| Idea expose 5 module qua REST | ✅ | Pattern phổ biến |
| Idea OpenAI-compatible LLM auto-detect từ base_url | ✅ | Pattern phổ biến (LiteLLM cũng làm thế) |
| Tên 37 personas (Buffett, Graham...) | ✅ | Public figure, ai cũng dùng được |
| Prompts cụ thể của 37 personas trong fincept-qt | ❌ | IP của Fincept, viết prompt mới |
| Code Python nguyên xi | ❌ | AGPL — phải viết lại |
| Endpoint URL pattern `/api/v1/agents/run` | ✅ | REST convention phổ biến |
| List 200+ data sources Fincept đã tích hợp | ✅ | Idea về sources, nhưng tự gọi API public |
| Logic algorithm (DCF, BSM, VaR, Greeks) | ✅ | Math chung, không có IP |

---

## 2. PHẠM VI 4 MODULE CẦN VIẾT LẠI

### 2.1 Module 1 — News (tin tức)

**Capability cần có:**

| # | Capability | Reference (chỉ để hiểu, không copy code) |
|---|---|---|
| 1 | RSS aggregator: ~20 nguồn tài chính (Reuters, Bloomberg public, FT public, Yahoo Finance, MarketWatch, Investing.com, Seeking Alpha…) | Có thư viện `feedparser` Python (BSD) — dùng trực tiếp |
| 2 | Web scraper fallback khi RSS không có (Playwright + BeautifulSoup) | Open-source standard |
| 3 | Dedupe theo URL canonicalization (normalize query/fragment) | Tự viết — logic đơn giản |
| 4 | Sentiment analysis: financial-context (tài chính có từ vựng riêng) | **FinBERT** (HuggingFace, Apache 2.0) hoặc **VADER** (MIT) — open-source |
| 5 | Entity extraction: tickers, companies, countries, organizations | **spaCy** (MIT) + custom dictionary nhỏ; **không cần copy** dictionary 200+ countries của Fincept (tự viết, hoặc dùng pycountry MIT) |
| 6 | Ticker matching: link bài news với tickers liên quan | Dùng pycountry + danh sách S&P500 / NASDAQ100 từ Wikipedia (public domain) |
| 7 | WebSocket fanout cho client realtime | FastAPI built-in WebSocket + Redis pub/sub |
| 8 | Search FTS theo title/body | PostgreSQL full-text search (built-in) |
| 9 | Filter theo ticker, sector, country, sentiment, importance | Pydantic query params |
| 10 | News correlation engine: phát hiện cluster sự kiện | Tự viết với scikit-learn KMeans/DBSCAN (BSD) |

**Effort:** ~1.5 tuần

---

### 2.2 Module 2 — Chatbot

**Capability cần có:**

| # | Capability | Reference |
|---|---|---|
| 1 | OpenAI-compatible chat completions endpoint | LiteLLM gateway (MIT) hoặc tự wrap với httpx |
| 2 | Multi-provider auto-detect: OpenAI, Anthropic, Groq, Together, DeepSeek, Ollama, LM Studio, OpenRouter, Mistral | LiteLLM hỗ trợ sẵn 100+ providers |
| 3 | SSE streaming token-by-token | FastAPI `StreamingResponse` + `text/event-stream` |
| 4 | Session persist: chat_sessions + chat_messages tables | PostgreSQL schema mới (xem section 4) |
| 5 | Token counting + cost tracking | LiteLLM trả token usage trong response |
| 6 | System prompt presets: "phân tích cổ phiếu", "macro outlook", "options strategy" | Tự viết YAML config |
| 7 | Markdown + code highlight ở client | Frontend (vue-markdown / shiki) |
| 8 | Tool calling: gọi data fetcher tools trong câu trả lời | LangChain tools / OpenAI tool calling spec (open standard) |
| 9 | RAG (optional Phase 2): trả lời từ news + báo cáo | LangChain + pgvector (PostgreSQL extension) |

**Effort:** ~1 tuần (không có RAG), ~2 tuần (có RAG cơ bản)

---

### 2.3 Module 3 — Agent

**Capability cần có:**

| # | Capability | Reference |
|---|---|---|
| 1 | Framework chạy agent với LLM tools | **agno** (Apache 2.0) hoặc **LangGraph** (MIT) — chọn 1 |
| 2 | Persona registry: Buffett, Graham, Lynch, Munger, Klarman, Marks, Greenblatt, Einhorn, Miller, Eveillard, Whitman… (11 trader/investor + 6 economic + N geopolitics) | Tự viết YAML/JSON config với prompt mới của bạn |
| 3 | Single-agent run (one-shot + streaming) | agno `Agent.run()` / `Agent.stream()` built-in |
| 4 | Multi-agent team (coordinate / route / collaborate modes) | agno `Team` hoặc LangGraph `StateGraph` |
| 5 | Execution planner: stock plan / portfolio plan / dynamic plan (DAG-based) | Tự viết với LangGraph (planner pattern phổ biến) |
| 6 | Tools: market_data, news, fred, sec_filings, technicals | Tự wrap, phân biệt rõ với "fake tools" cũ của Fincept |
| 7 | Paper trading bridge: agent có thể đề xuất + execute paper trade | Tự viết — dùng schema portfolios + holdings của bạn |
| 8 | Memory: short-term (conversation) + long-term (vector store) | agno built-in memory hoặc LangChain ConversationBufferMemory |
| 9 | Guardrails: ngăn agent gọi `eval()`, hạn chế domain HTTP | Tự viết hook layer |
| 10 | Audit log mỗi lần agent run | Postgres `agent_runs` table |

**Effort:** ~2.5 tuần (cơ bản 11 personas + multi-agent + planner)

**Lưu ý quan trọng về personas:** Bạn cần tự viết prompts từ đầu. Ví dụ Warren Buffett — đọc *The Essays of Warren Buffett* (đã public) hoặc tham khảo Berkshire annual letters (publicly available), tự đúc kết thành prompt:

```yaml
# personas/warren_buffett.yaml (tự bạn viết)
id: warren_buffett
name: Warren Buffett Style Analyst
system_prompt: |
  You analyze businesses in the spirit of long-term value investing principles
  publicly associated with Warren Buffett's investing philosophy:
  - Focus on durable competitive advantages (economic moats)
  - Predictable, growing earnings over 5-10 year horizons
  - Strong returns on equity (ideally >15% sustained)
  - Conservative balance sheet (low debt-to-equity)
  - Quality management with rational capital allocation
  - Margin of safety: buy at meaningful discount to intrinsic value
  ...
analysis_framework:
  - moat_assessment: ...
  - earnings_predictability: ...
  - financial_strength: ...
  - management_quality: ...
  - valuation: ...
```

Đây là **kiến thức đầu tư công khai** trong sách của Buffett, Lynch, Graham → ai cũng viết được prompt riêng, không vi phạm IP.

---

### 2.4 Module 4 — Phân tích (Analytics)

**Capability cần có:**

| # | Capability | Reference |
|---|---|---|
| 1 | Stock fundamentals: P/E, P/B, ROE, market cap, sector | `yfinance` (Apache 2.0) trực tiếp — không cần wrapper Fincept |
| 2 | Financial statements: income, balance sheet, cash flow | yfinance |
| 3 | DCF valuation | Tự viết (math chung): cash flow → discount → terminal value |
| 4 | Technical indicators: RSI, MACD, BB, EMA, SMA, ATR... | **TA-Lib** (BSD) hoặc **pandas-ta** (MIT) hoặc **ta** (MIT) |
| 5 | Buy/sell signals từ chiến lược: momentum, mean reversion, breakout | Tự viết — logic đơn giản |
| 6 | Portfolio optimization: mean-variance, risk-parity, Black-Litterman, min-variance | **PyPortfolioOpt** (MIT) — dùng trực tiếp |
| 7 | Portfolio metrics: Sharpe, Sortino, Max DD, VaR, CVaR, Alpha, Beta | **quantstats** (Apache 2.0) hoặc **empyrical** (Apache 2.0) |
| 8 | Backtest đơn giản (walk-forward) | **vectorbt** (Apache 2.0) hoặc **backtrader** (GPL — tránh) hoặc tự viết |
| 9 | Forecast: Prophet, ARIMA | **prophet** (MIT) + **statsmodels** (BSD) |
| 10 | Regime detection: bull/bear/sideways | **hmmlearn** (BSD) HMM + tự viết rule-based |
| 11 | Comprehensive analysis page (gộp DCF + technical + AI opinion + news sentiment) | Orchestrator code, gọi các module trên |

**Effort:** ~2 tuần (tận dụng nhiều thư viện sẵn → nhanh)

---

### 2.5 Tổng phạm vi & effort

| Module | Capabilities chính | Effort (1 dev FT) |
|---|---|---|
| News | 10 | 1.5 tuần |
| Chatbot | 9 (không RAG) | 1 tuần |
| Agent | 10 (11 personas cơ bản) | 2.5 tuần |
| Analytics | 11 | 2 tuần |
| Foundation (auth, DB, cache, deploy) | 8 | 1 tuần |
| **Tổng MVP** | | **~8 tuần** |
| Polish + integration với QuantDinger Vue | | +2 tuần |
| **Tổng production-ready** | | **~10 tuần** |

---

## 3. KIẾN TRÚC ĐỀ XUẤT — `<NEW_BRAND>` (tên placeholder)

### 3.1 Sơ đồ tổng thể

```
                    ┌─────────────────────────────┐
                    │  QuantDinger Vue UI         │
                    │  (đã có, port 8888)         │
                    │  + 4 trang mới:             │
                    │    /research/news           │
                    │    /research/chat           │
                    │    /research/agents         │
                    │    /research/analysis       │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │ Reverse Proxy (Caddy)       │
                    └──┬───────────────────────┬──┘
                       │                       │
         /api/* (Flask)│              /research/api/* (mới)
                       │                       │
            ┌──────────▼─────────┐  ┌──────────▼──────────────┐
            │ QuantDinger Flask  │  │ <NEW_BRAND> Backend     │
            │ port 5000          │  │ FastAPI + Python 3.12   │
            │ - charting         │  │ port 8000               │
            │ - indicator IDE    │  │ - News pipeline         │
            │ - backtest         │  │ - Chat completions      │
            │ - live trading     │  │ - Agent framework       │
            │ - billing          │  │ - Analytics             │
            │ - MCP /agent/v1    │  └──────┬──────────────────┘
            └────────────────────┘         │
                                  ┌────────┴──────────┐
                                  │                   │
                          ┌───────▼────────┐ ┌────────▼─────────┐
                          │ News workers   │ │ LLM provider     │
                          │ (RSS+NLP+      │ │ (OpenAI / Groq / │
                          │  WebSocket)    │ │  Ollama / ...)   │
                          └───────┬────────┘ └──────────────────┘
                                  │
                          ┌───────┴──────────┐
                          │ Postgres + Redis │
                          │ (share với QD,   │
                          │  schema riêng)   │
                          └──────────────────┘
```

### 3.2 Cấu trúc thư mục backend mới

```
<new-brand>-backend/                  ← Repo mới, license Apache 2.0
├── app/
│   ├── main.py                        FastAPI entry
│   ├── config.py                      Pydantic Settings
│   ├── deps.py                        Auth, DB, Redis deps
│   ├── middleware.py                  Logging, rate limit, request_id
│   └── routers/
│       ├── news.py                    Module 1
│       ├── chat.py                    Module 2
│       ├── agents.py                  Module 3
│       ├── analytics.py               Module 4
│       └── health.py
├── core/
│   ├── auth.py                        JWT verify (share secret với QuantDinger)
│   ├── cache.py                       Redis async client
│   ├── db.py                          asyncpg / SQLAlchemy 2.x
│   ├── llm.py                         LiteLLM wrapper
│   ├── errors.py                      Error code enum + handlers
│   └── audit.py                       Audit log writer
├── domains/
│   ├── news/
│   │   ├── fetcher.py                 RSS + scraper
│   │   ├── nlp.py                     FinBERT + spaCy
│   │   ├── correlation.py             Cluster + signal detection
│   │   ├── ws.py                      WebSocket fanout
│   │   ├── repository.py              CRUD news_articles
│   │   └── workers.py                 Background workers (news_fetcher,
│   │                                  nlp_worker)
│   ├── chat/
│   │   ├── completions.py             Streaming + non-stream
│   │   ├── sessions.py                CRUD session
│   │   └── prompts.py                 System presets
│   ├── agents/
│   │   ├── runtime.py                 agno-based runner
│   │   ├── personas/                  11 prompts mới
│   │   │   ├── buffett.yaml
│   │   │   ├── graham.yaml
│   │   │   ├── lynch.yaml
│   │   │   └── ...
│   │   ├── teams.py                   Multi-agent
│   │   ├── planner.py                 Execution planner DAG
│   │   ├── tools.py                   Tools: market, news, fred...
│   │   └── paper_trading.py
│   └── analytics/
│       ├── fundamentals.py            yfinance wrapper
│       ├── dcf.py                     Tự viết
│       ├── technicals.py              TA-Lib / pandas-ta
│       ├── portfolio.py               PyPortfolioOpt + quantstats
│       ├── forecast.py                Prophet + ARIMA
│       └── regime.py                  HMM + rule-based
├── workers/
│   ├── news_fetcher.py                Standalone worker process
│   ├── news_nlp.py
│   └── job_runner.py                  (Phase 2: backtest, training)
├── migrations/                        Alembic
│   └── versions/
│       └── 001_init.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── load/
├── docker-compose.yml                 Cùng stack với QuantDinger
├── Dockerfile
├── pyproject.toml
├── .env.example
└── README.md
```

### 3.3 Tech stack đề xuất (chỉ dùng license-friendly)

| Layer | Lựa chọn | License | Lý do |
|---|---|---|---|
| Web framework | **FastAPI** 0.115+ | MIT | Async native, SSE built-in, OpenAPI tự sinh |
| Validation | Pydantic v2 | MIT | Default với FastAPI |
| Database driver | asyncpg + SQLAlchemy 2.x async | BSD / MIT | Async-first |
| Migrations | Alembic | MIT | |
| Cache + Queue | Redis 7 + Redis Streams | BSD | Đã có sẵn trong QuantDinger stack |
| LLM gateway | LiteLLM | MIT | Hỗ trợ 100+ providers, drop-in OpenAI-compatible |
| Agent framework | **agno** | Apache 2.0 | Lightweight, không lock-in (alternative: LangGraph MIT) |
| LLM tracing (optional) | OpenTelemetry | Apache 2.0 | |
| News fetching | feedparser | BSD | RSS standard |
| News scraping fallback | Playwright | Apache 2.0 | Robust JS rendering |
| Sentiment | FinBERT (HuggingFace) | Apache 2.0 | Financial-aware |
| NLP / NER | spaCy | MIT | |
| Market data | **yfinance** | Apache 2.0 | Direct, no Fincept wrapper |
| Macro data | **fredapi** | Apache 2.0 | FRED Python SDK official |
| Technicals | **pandas-ta** | MIT | Pure Python, không cần TA-Lib C |
| Portfolio opt | **PyPortfolioOpt** | MIT | |
| Portfolio metrics | **quantstats** | Apache 2.0 | |
| Forecast | **prophet** | MIT | |
| Stats | statsmodels | BSD | |
| Regime detection | hmmlearn | BSD | |
| Vector DB (RAG) | pgvector (Postgres ext) | PostgreSQL License | Dùng chung Postgres |
| Observability | Prometheus client + Grafana | Apache 2.0 | |
| Logging | structlog | Apache 2.0 / MIT | |
| Test | pytest + httpx + Hypothesis | MIT / BSD | |
| Container | docker-compose | Apache 2.0 | |

**Toàn bộ license tương thích với Apache 2.0 / MIT** — sản phẩm cuối của bạn có thể chọn license tự do (Apache 2.0 khuyến nghị để đồng bộ với QuantDinger).

---

## 4. TÍCH HỢP VỚI QUANTDINGER

### 4.1 Auth chia sẻ

QuantDinger Flask cấp JWT khi user login. `<NEW_BRAND>` backend verify cùng JWT đó:

```python
# core/auth.py
from jose import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer

security = HTTPBearer()

async def get_current_user(token = Depends(security)):
    try:
        payload = jwt.decode(
            token.credentials,
            settings.QUANTDINGER_JWT_SECRET,  # share env var với Flask
            algorithms=["HS256"],
        )
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(401, "Invalid token")
        # (Optional) cache user lookup trong Redis 5 phút
        return await get_user(user_id)
    except jwt.JWTError:
        raise HTTPException(401, "Invalid token")
```

QuantDinger không cần thay đổi gì. Chỉ cần share `SECRET_KEY` qua env var.

### 4.2 Database chia sẻ

Cùng Postgres database `quantdinger`, schema riêng `<new_brand>.*`:

```sql
-- migrations/001_init.sql
CREATE SCHEMA IF NOT EXISTS <new_brand>;

CREATE TABLE <new_brand>.news_articles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source          TEXT NOT NULL,
    url             TEXT UNIQUE NOT NULL,
    title           TEXT NOT NULL,
    summary         TEXT,
    body            TEXT,
    published_at    TIMESTAMPTZ NOT NULL,
    fetched_at      TIMESTAMPTZ DEFAULT now(),
    language        TEXT,
    tickers         TEXT[],
    entities        JSONB DEFAULT '[]'::jsonb,
    sentiment       NUMERIC(4,3),
    importance      NUMERIC(3,2),
    raw             JSONB
);
CREATE INDEX idx_news_published ON <new_brand>.news_articles(published_at DESC);
CREATE INDEX idx_news_tickers ON <new_brand>.news_articles USING gin(tickers);

CREATE TABLE <new_brand>.chat_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL,                    -- FK soft, ref public.users(id)
    title           TEXT,
    persona_id      TEXT,
    model           TEXT,
    base_url        TEXT,
    metadata        JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE <new_brand>.chat_messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL REFERENCES <new_brand>.chat_sessions(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    tool_calls      JSONB,
    tokens_in       INT,
    tokens_out      INT,
    latency_ms      INT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE <new_brand>.agent_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL,
    persona_id      TEXT NOT NULL,
    query           TEXT,
    response        TEXT,
    duration_ms     INT,
    tokens_in       INT,
    tokens_out      INT,
    cost_usd        NUMERIC(10,6),
    status          TEXT,                             -- ok | error | cancelled
    error           JSONB,
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_agent_runs_user ON <new_brand>.agent_runs(user_id, created_at DESC);

CREATE TABLE <new_brand>.audit_log (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id         UUID,
    action          TEXT NOT NULL,
    resource        TEXT,
    request_id      UUID,
    metadata        JSONB
);
```

QuantDinger không bị ảnh hưởng. Backup chung 1 lệnh `pg_dump`.

### 4.3 Redis chia sẻ với prefix

Redis cùng instance, prefix key: `<new_brand>:cache:*`, `<new_brand>:rate:*`, `<new_brand>:news:queue`, `<new_brand>:news:pubsub:*`. QuantDinger keys thường dùng prefix khác → không xung đột.

### 4.4 Frontend integration

QuantDinger-Vue (Vue 2) thêm 4 routes mới:

```javascript
// router/research.js
{
  path: '/research',
  component: ResearchLayout,
  children: [
    { path: 'news', component: NewsPage },           // gọi /research/api/news
    { path: 'chat', component: ChatPage },           // gọi /research/api/chat
    { path: 'agents', component: AgentsPage },       // gọi /research/api/agents
    { path: 'agents/:id', component: AgentRun },
    { path: 'analysis/:ticker', component: AnalysisPage }, // gọi /research/api/analytics
  ]
}
```

Reverse proxy (Caddy) route `/research/api/*` → `<new-brand>:8000`. Frontend dùng axios với baseURL khác cho research module.

### 4.5 docker-compose tích hợp

Trong `QuantDinger/docker-compose.yml` thêm 3 service mới:

```yaml
services:
  # ... (giữ nguyên các service QuantDinger)

  research-api:
    build: ./<new-brand>-backend
    environment:
      DATABASE_URL: postgresql://app:app@postgres:5432/quantdinger
      REDIS_URL: redis://redis:6379/1
      QUANTDINGER_JWT_SECRET: ${SECRET_KEY}        # share với Flask
      LLM_BASE_URL: ${LLM_BASE_URL}
      LLM_API_KEY: ${LLM_API_KEY}
      FRED_API_KEY: ${FRED_API_KEY}
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }

  research-news-fetcher:
    build: ./<new-brand>-backend
    command: python -m workers.news_fetcher
    environment: ...
    depends_on: [research-api]

  research-nlp-worker:
    build: ./<new-brand>-backend
    command: python -m workers.news_nlp
    environment: ...
    depends_on: [research-api, postgres]
```

---

## 5. KẾ HOẠCH TRIỂN KHAI THEO PHASE

### Phase 0 — Foundation (Tuần 1)

- [ ] Tạo repo mới `<new-brand>-backend`, license Apache 2.0
- [ ] FastAPI skeleton + Pydantic Settings + structlog
- [ ] Postgres schema + Alembic migrations init
- [ ] Redis async client + cache helper
- [ ] JWT verify share với QuantDinger
- [ ] docker-compose tích hợp với QuantDinger stack
- [ ] Caddy/Nginx route `/research/api/*`
- [ ] CI: GitHub Actions lint + test
- [ ] Smoke test: 2 backend up, gọi `/api/health` cả hai

**Deliverable:** Login QuantDinger → token gọi được `/research/api/health` qua proxy.

---

### Phase 1 — News module (Tuần 2–3) ⭐ Quick win

**Tuần 2 — Backend:**
- [ ] Schema `news_articles`, `news_sources`
- [ ] feedparser-based RSS fetcher worker (~20 sources)
- [ ] Dedupe theo URL canonicalization
- [ ] FinBERT sentiment analysis worker
- [ ] spaCy entity extraction
- [ ] Ticker matching với S&P500 + NASDAQ100 list
- [ ] Endpoints: `GET /news`, `GET /news/{id}`, `GET /news/search`
- [ ] WebSocket `/ws/news` + filter theo ticker

**Tuần 3 — Frontend Vue 2 page:**
- [ ] Page `/research/news` với infinite scroll
- [ ] Filter sidebar: ticker, sentiment, source, language
- [ ] Sentiment badges (xanh/đỏ/vàng)
- [ ] WebSocket client với reconnect logic
- [ ] Article detail modal

**Success metrics:**
- ≥ 10 sources active, ≥ 500 articles/day
- WebSocket fanout latency p99 < 200ms
- Sentiment + ticker tags hiển thị

---

### Phase 2 — Chatbot (Tuần 4)

**Backend:**
- [ ] Schema `chat_sessions`, `chat_messages`
- [ ] Endpoint `POST /chat/completions` (OpenAI-compatible) với LiteLLM
- [ ] SSE streaming token-by-token
- [ ] Endpoints CRUD sessions
- [ ] Token counting + cost tracking từ LiteLLM response
- [ ] System prompt presets (~5 presets cơ bản)

**Frontend:**
- [ ] Page `/research/chat` với conversation list + message stream
- [ ] LLM provider config UI (chọn model, set base_url + api_key)
- [ ] Markdown rendering + code highlight
- [ ] Copy / regenerate / edit message

**Success metrics:**
- TTFB streaming < 1.5s
- Hỗ trợ ≥ 5 LLM providers (test: OpenAI, Anthropic, Groq, Ollama, OpenRouter)
- Session restore < 200ms

---

### Phase 3 — Agent framework (Tuần 5–6.5)

**Tuần 5 — Backend cốt lõi:**
- [ ] Setup agno framework
- [ ] Persona registry: viết 11 prompts mới (Buffett, Graham, Lynch, Munger, Klarman, Marks, Greenblatt, Einhorn, Miller, Eveillard, Whitman) → từ tài liệu công khai
- [ ] Tools: market_data (yfinance), news (gọi nội bộ Module 1), fred (fredapi), sec_filings (sec-api hoặc EDGAR public)
- [ ] Endpoint `POST /agents/run` (one-shot)
- [ ] Endpoint `POST /agents/run/stream` (SSE)

**Tuần 6 — Multi-agent + Planner:**
- [ ] Multi-agent team: route / coordinate / collaborate
- [ ] Execution planner DAG (LangGraph hoặc tự viết)
- [ ] Endpoint `POST /agents/team/run`
- [ ] Endpoint `POST /agents/plan/{stock|portfolio|dynamic}`
- [ ] Paper trading bridge: `POST /agents/paper/trade`
- [ ] Audit log per run

**Tuần 6.5 — Frontend:**
- [ ] Page `/research/agents` gallery 11 agents với category filter
- [ ] Page `/research/agents/{id}` run console với streaming
- [ ] Multi-agent team builder UI
- [ ] Execution planner visualizer (vue-flow MIT)
- [ ] Paper trading panel

**Success metrics:**
- 11 personas chạy được với streaming
- Agent run success rate ≥ 95%
- TTFB streaming < 500ms

---

### Phase 4 — Analytics & Predictions (Tuần 7–8)

**Tuần 7 — Backend:**
- [ ] Endpoint `GET /analytics/{ticker}/info` (yfinance)
- [ ] Endpoint `GET /analytics/{ticker}/financials`
- [ ] Endpoint `POST /analytics/{ticker}/dcf` (tự viết)
- [ ] Endpoint `POST /analytics/technicals` (pandas-ta)
- [ ] Endpoint `POST /analytics/signals` (rule-based)
- [ ] Endpoint `POST /analytics/portfolio/optimize` (PyPortfolioOpt)
- [ ] Endpoint `POST /analytics/portfolio/metrics` (quantstats)
- [ ] Endpoint `POST /predictions/forecast/{ticker}` (Prophet)
- [ ] Endpoint `POST /predictions/regime` (HMM)
- [ ] Endpoint `POST /analytics/comprehensive/{ticker}` — gộp tất cả

**Tuần 8 — Frontend Comprehensive Analysis Page:**
- [ ] Page `/research/analysis/{ticker}` với 6 tab:
  - Tab Overview: price + sentiment + key ratios
  - Tab Chart: TradingView Lightweight Charts (Apache 2.0) với indicators
  - Tab Fundamentals: ratios, financials
  - Tab DCF: intrinsic value + sensitivity sliders
  - Tab Forecast: Prophet chart với confidence band
  - Tab AI Analysis: streaming agent opinion (gọi Module 3)
  - Tab News: filter theo ticker (gọi Module 1)
- [ ] Page `/research/screener` filter stocks theo criteria

**Success metrics:**
- Forecast endpoint < 10s
- DCF + technicals < 3s
- Comprehensive page load tất cả tab < 5s

---

### Phase 5 — Polish & Production hardening (Tuần 9–10)

- [ ] Rate limiting per user / per endpoint
- [ ] Audit log review UI (admin only)
- [ ] Prometheus metrics + Grafana dashboards
- [ ] Load test với k6: 100 concurrent users
- [ ] E2E test với Playwright
- [ ] Documentation: README, API docs, deployment guide
- [ ] Backup script: pg_dump cron
- [ ] Kubernetes manifests (optional, nếu scale)

---

## 6. SO SÁNH 3 PHƯƠNG ÁN — CẬP NHẬT

| Tiêu chí | A. fincept-api microservice | B. Giữ desktop + microservice | **C. Viết lại sạch (báo cáo này)** |
|---|---|---|---|
| **Pháp lý** | ⚠️ AGPL/Commercial Fincept | ⚠️ AGPL/Commercial Fincept | ✅ **Sạch hoàn toàn** |
| Effort | 4–5 tuần | 6–7 tuần | **8–10 tuần** |
| Tận dụng fincept-api | 100% | 100% | 0% (tham khảo idea) |
| Sở hữu IP | Phụ thuộc Fincept Corp | Phụ thuộc Fincept Corp | **Bạn 100%** |
| License compatibility với QuantDinger | ❌ | ❌ | ✅ Apache 2.0 ↔ Apache 2.0 |
| Risk pháp lý nếu commercial | Cao | Cao | Thấp (gần như 0) |
| Quality code | Phụ thuộc Fincept | Phụ thuộc Fincept | Bạn kiểm soát |
| Maintenance dài hạn | Phụ thuộc upstream Fincept | Phụ thuộc upstream | Bạn chủ động |
| Stack đơn giản | Trung bình | Phức tạp | **Đơn giản** (chỉ Python) |

→ **Phương án C là phương án duy nhất sạch về pháp lý** nếu bạn muốn build một sản phẩm fintech commercial mà không vướng vào AGPL hoặc commercial license của Fincept Corp.

---

## 7. RỦI RO & MITIGATION

| Rủi ro | Mức độ | Mitigation |
|---|---|---|
| Effort 8–10 tuần dài hơn dự kiến | Trung bình | Phase rõ, mỗi 2 tuần có deliverable demo được |
| Persona prompts viết lại không hay bằng Fincept | Trung bình | Dùng tài liệu công khai (sách Buffett, Munger, Lynch — đã in hàng triệu bản). Iterate qua test |
| FinBERT chậm trên CPU | Thấp | Dùng DistilBERT-fin (nhỏ hơn). Hoặc OpenAI embeddings cho production |
| RSS sources thay đổi format | Thấp | feedparser xử lý standard tốt. Health check mỗi source định kỳ |
| News scraper bị block | Thấp | Bắt đầu chỉ với RSS, scraper là Phase 2 |
| LiteLLM thay đổi API | Thấp | LiteLLM stable, được dùng rộng rãi |
| Conflict dependency với QuantDinger | Thấp | Tách container riêng, mỗi backend có venv riêng |
| Frontend Vue 2 cũ, khó add page mới | Trung bình | QuantDinger-Vue đã migrate sang Vite — dễ dev |
| User confused vì 2 brand | Trung bình | Đặt tên module trong UI là "Research" / "Analytics" — không expose brand riêng |
| Forecast model gây hiểu lầm "investment advice" | Trung bình | Disclaimer rõ ràng ở UI + API response |

---

## 8. PHÁP LÝ — CHECKLIST TRƯỚC KHI BẮT ĐẦU

- [ ] **Repo mới hoàn toàn**, không clone từ FinceptTerminal
- [ ] License **Apache 2.0** (đề xuất, đồng bộ QuantDinger backend) hoặc **MIT**
- [ ] **Không có file Python copy** từ `fincept-qt/scripts/`
- [ ] **Không có file JSON config** copy từ `fincept-qt/scripts/agents/*/configs/`
- [ ] Prompts persona **tự viết** dựa trên sách / public articles, **không paraphrase** prompts của Fincept
- [ ] Naming: tránh dùng "fincept" / "Fincept Terminal" trong code và UI. Dùng `<NEW_BRAND>` hoặc tên QuantDinger module
- [ ] Documentation: trong README ghi rõ "Apache 2.0", không reference FinceptTerminal
- [ ] Dependencies: chỉ thư viện open-source license-friendly (Apache 2.0 / MIT / BSD / PostgreSQL License)
- [ ] **Không** import `agno` framework theo cách của Fincept (vd: gọi `finagent_core.persona_runtime`). Dùng agno official API.
- [ ] **Tránh** tham chiếu `api.fincept.in` ở mọi nơi
- [ ] Nếu cần verify pháp lý chặt chẽ: tham vấn luật sư IP một lần trước khi commercial deploy

---

## 9. ĐỀ XUẤT CỤ THỂ

### 9.1 Đặt tên brand

Đề xuất 5 phương án tên cho module/repo mới (chọn 1):

| Tên | Ý nghĩa | Phù hợp |
|---|---|---|
| **QuantDinger Research** | Module mở rộng của QuantDinger | Đơn giản, gắn với QuantDinger ecosystem |
| **QuantDinger Insights** | Tập trung vào "insights" — phân tích + tin tức | Gắn nhãn rõ |
| **InsightLab** | Tên độc lập | Có thể tái sử dụng cho dự án khác |
| **AlphaScope** | "Alpha" trong quant + "Scope" như Bloomberg | Branding fintech |
| **Forge Research** | "Forge" gợi ý xây dựng + "Research" rõ scope | Tên ngắn, mạnh |

### 9.2 Roadmap tinh giản (10 tuần)

```
Tuần 1     │ Phase 0 — Foundation (auth, DB, deploy)
Tuần 2-3   │ Phase 1 — News (backend + UI)            ⭐ MVP demo được
Tuần 4     │ Phase 2 — Chatbot (backend + UI)
Tuần 5-6.5 │ Phase 3 — Agent (11 personas + multi-agent + planner)
Tuần 7-8   │ Phase 4 — Analytics + Predictions + Comprehensive page
Tuần 9-10  │ Phase 5 — Polish, monitoring, load test, docs
```

Sau Tuần 3 đã có **News module live** trong QuantDinger UI — đủ cho demo và bắt đầu thu thập feedback user.

### 9.3 Quyết định cần làm trước

1. **Tên brand cuối cùng** (chọn từ section 9.1 hoặc tự đặt)
2. **License**: Apache 2.0 (đề xuất) hay MIT?
3. **Agent framework**: agno (Apache 2.0, lightweight, focus financial) hay LangGraph (MIT, generic graph-based)?
4. **Có self-host LLM không?** (Ollama)
5. **Có thư mục riêng** trong repo QuantDinger (`QuantDinger/research/`) hay **repo riêng** (`<new-brand>-backend`)?
6. **Frontend**: thêm pages vào QuantDinger-Vue (Vue 2) hay **build Vue 3 SPA riêng** rồi nhúng iframe / link out?

---

## 10. NHỮNG THỨ NÊN VÀ KHÔNG NÊN MANG TỪ FINCEPT

### 10.1 Mang được (idea, không phải code)

| Thứ | Cách dùng |
|---|---|
| Danh sách 11 trader/investor personas | Public knowledge — viết prompt mới |
| Idea về 6 economic personas (Capitalism, Keynesian, Neoliberal, Socialist, Mixed, Mercantilist) | Public — viết prompt mới |
| Ý tưởng JSON stdin/stdout protocol cho subprocess | Pattern phổ biến — implement riêng |
| Endpoint URL convention `/api/v1/{module}/{resource}` | REST best practice |
| Idea OpenAI-compatible LLM auto-detect base_url | LiteLLM hỗ trợ sẵn |
| List 200+ data sources tham khảo | Tự gọi API public, không dùng wrapper Fincept |
| Pattern bridge layer (cho subprocess JSON) | Implement riêng đơn giản hơn |

### 10.2 KHÔNG mang được

| Thứ | Lý do |
|---|---|
| Bất kỳ file `.py` nào từ `fincept-qt/scripts/` | AGPL — phải viết lại |
| Bất kỳ file `.json` config nào từ `fincept-qt/scripts/agents/` | IP của Fincept |
| `finagent_core/main.py` JSON dispatch logic | Code Fincept |
| Persona prompts cụ thể (system_prompt content) | IP — viết mới |
| Agent runtime/loader/factory code | IP — implement với agno official |
| Code C++ Qt từ `fincept-qt/src/` | Không cần (không build desktop nữa) |
| Toàn bộ bridge layer `api_bridge/*.py` của fincept-api | IP — viết mới |

---

## 11. KẾT LUẬN

**Câu trả lời cho câu hỏi của bạn:**

✅ **Có thể viết lại** 4 module (phân tích, agent, chatbot, news) một cách hoàn toàn sạch về pháp lý.

✅ **Effort 8–10 tuần** (1 dev FT) cho một MVP production-ready.

✅ **Stack chỉ Python pure** — đơn giản hơn nhiều so với hệ thống hiện tại (C++/Qt + Python + FastAPI).

✅ **License Apache 2.0** tương thích hoàn toàn với QuantDinger backend, có thể commercial freely.

✅ **Tận dụng được toàn bộ ecosystem QuantDinger**: auth, database, Redis, frontend Vue 2, deploy stack, MCP server.

✅ **Mở rộng QuantDinger** đúng những điểm nó thiếu: news pipeline, AI personas, chatbot streaming, comprehensive analysis — không trùng với core trading của QuantDinger.

❌ **Phải vứt bỏ** fincept-api (146 tests đã viết) và toàn bộ scripts của fincept-qt — nhưng đổi lại là **sản phẩm sạch**, **bạn 100% chủ động**, **không vướng pháp lý**.

### Quyết định khuyến nghị

**Tiến hành Phương án C — viết lại sạch.** Effort 8–10 tuần đáng để có một sản phẩm:
- Sạch về pháp lý → có thể commercial / SaaS
- Sạch về kỹ thuật → stack Python pure dễ maintain
- Tích hợp tốt với QuantDinger → user QuantDinger có thêm 4 capability mạnh ngay trong UI quen thuộc
- Mở rộng được → có thể tách ra làm sản phẩm riêng nếu QuantDinger đổi hướng

### Bước kế tiếp

Nếu bạn đồng ý Phương án C:

1. **Trả lời 6 câu hỏi ở section 9.3** (tên, license, framework, self-host LLM, repo location, frontend strategy)
2. Tôi sẽ **update spec `fintech-production-platform/design.md`** thành version mới phù hợp với hướng "viết lại sạch + tích hợp QuantDinger"
3. Hoặc **tạo spec mới** `<new-brand>-backend` chuyên biệt cho backend này
4. Bắt đầu **Phase 0 — Foundation** trong tuần đầu tiên

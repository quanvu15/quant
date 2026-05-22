# BÁO CÁO PHÂN TÍCH CHI TIẾT DỰ ÁN FINCEPT TERMINAL

> **Phiên bản tài liệu:** 1.0 — Ngày: 18/05/2026
> **Nguồn phân tích:** Source code tại `g:\Code\AI-APP\FinceptTerminal`
> **Kiến trúc tham chiếu:** `docs/ARCHITECTURE.md` (v5.0.0-draft, cập nhật 2026-05-15)

---

## MỤC LỤC

1. [Tổng quan dự án](#1-tổng-quan-dự-án)
2. [Kiến trúc hệ thống](#2-kiến-trúc-hệ-thống)
3. [Tech Stack & Quy mô](#3-tech-stack--quy-mô)
4. [Phân tích chi tiết 8 chức năng cốt lõi](#4-phân-tích-chi-tiết-8-chức-năng-cốt-lõi)
   - 4.1 [Multi-Asset Analytics](#41-multi-asset-analytics)
   - 4.2 [AI Agents](#42-ai-agents)
   - 4.3 [QuantLib Suite](#43-quantlib-suite)
   - 4.4 [Global Intelligence](#44-global-intelligence)
   - 4.5 [Node Editor (Visual Workflow)](#45-node-editor-visual-workflow)
   - 4.6 [AI Quant Lab](#46-ai-quant-lab)
   - 4.7 [Crypto Center](#47-crypto-center)
   - 4.8 [Alpha Arena](#48-alpha-arena)
5. [Phân tích khả năng API hóa](#5-phân-tích-khả-năng-api-hóa)
6. [Đề xuất kiến trúc API Gateway](#6-đề-xuất-kiến-trúc-api-gateway)
7. [Rủi ro & Lưu ý](#7-rủi-ro--lưu-ý)
8. [Kết luận](#8-kết-luận)

---

## 1. TỔNG QUAN DỰ ÁN

### 1.1 Định danh

| Thuộc tính | Giá trị |
|---|---|
| **Tên** | Fincept Terminal |
| **Phiên bản hiện tại** | v4.0.3 (stable) / v5.0.0-draft (architecture) |
| **Tổ chức** | Fincept Corporation |
| **License** | AGPL-3.0 (open source) + Commercial License |
| **Repository** | https://github.com/Fincept-Corporation/FinceptTerminal |
| **Liên hệ** | support@fincept.in |
| **Discord** | https://discord.gg/ae87a8ygbN |

### 1.2 Mô tả

Fincept Terminal là một **Bloomberg-style financial workstation** mã nguồn mở, được xây dựng hoàn toàn bằng C++20 native với Qt6. Đây là một ứng dụng desktop đa nền tảng (Windows/macOS/Linux) tích hợp:

- **Analytics tài chính cấp tổ chức** (institutional-grade)
- **AI agents** với 37+ personas đầu tư nổi tiếng
- **Real-time trading** qua 16 broker + 2 sàn crypto
- **100+ data connectors** từ các nguồn toàn cầu
- **Python analytics engine** nhúng trong C++ runtime

Slogan: *"Your Thinking is the Only Limit. The Data Isn't."*

### 1.3 Định vị thị trường

Fincept Terminal cạnh tranh trực tiếp với Bloomberg Terminal ($24,000/năm) và Refinitiv Eikon, nhưng là **mã nguồn mở và miễn phí** cho cá nhân. Mô hình kinh doanh dựa trên:
- Commercial License cho doanh nghiệp
- University License ($799/tháng cho 20 tài khoản)
- Community token $FNCPT trên Solana (pump.fun)
- GitHub Sponsors (development grant mục tiêu $17,000)

---

## 2. KIẾN TRÚC HỆ THỐNG

### 2.1 Mô hình kiến trúc: Modular Monolith

```
┌─────────────────────────────────────────────────────────────┐
│  PRESENTATION — 54 Screens (lazy-loaded qua DockScreenRouter)│
│  ADS Docking System · IStatefulScreen · ScreenStateManager  │
├─────────────────────────────────────────────────────────────┤
│  APPLICATION — 13 Bounded Contexts                          │
│  Markets · News · Economics · Geopolitics · Trading         │
│  Portfolio · Crypto · Derivatives · Predictions             │
│  Agents · AI Chat · Workflow · Identity                     │
├─────────────────────────────────────────────────────────────┤
│  DATA PLANE                                                 │
│  DataHub (pub/sub by topic) · CacheManager (SQLite TTL)     │
├─────────────────────────────────────────────────────────────┤
│  INTEGRATION ADAPTERS                                       │
│  BrokerAdapter · McpTools · PythonRunner · HttpClient · WS  │
├─────────────────────────────────────────────────────────────┤
│  INFRASTRUCTURE                                             │
│  Logger · AppConfig · EventBus · SessionManager · AuthManager│
│  SQLite DB · SecureStorage (AES-256-GCM) · 26 Repositories  │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Quy tắc dependency (bất biến)

```
Presentation → Application → Data Plane → Adapters → Infrastructure → Platform
```
Không bao giờ đảo ngược. Cross-context calls đi qua DataHub topics hoặc typed events.

### 2.3 DataHub — Data Plane trung tâm

DataHub là hệ thống pub/sub in-process với topic format `domain:subdomain:id[:modifier]`.
- **One-fetch/many-subscribers**: chỉ fetch một lần dù có nhiều subscriber
- **TTL cache**: mọi topic đều có TTL và min_interval
- **Thread-safe**: `publish()` an toàn từ bất kỳ thread nào
- **Push-only topics**: cho WebSocket feeds (Kraken, HyperLiquid, Polymarket)

---

## 3. TECH STACK & QUY MÔ

### 3.1 Ngôn ngữ & Framework

| Layer | Công nghệ | Vai trò |
|---|---|---|
| Core runtime | **C++20** | Toàn bộ logic ứng dụng |
| UI | **Qt6 Widgets + Qt6 Charts** | Native retained-mode UI |
| Async (target) | **QCoro** (C++20 coroutines) | `co_await` HTTP/DB/Python |
| Async (hiện tại) | Callbacks + QPointer, signals/slots | Backward-compatible |
| Networking | Qt6 Network (HTTP/TLS) + Qt6 WebSockets | Tất cả I/O |
| Database | Qt6 Sql + **SQLite** | Local persistence (2 DB files) |
| Encryption | **AES-256-GCM** (SQLite-backed) | SecureStorage |
| JSON | QJsonDocument | Tất cả wire formats |
| Python | **3.11.9** via UV-managed venv | Analytics, agents, data fetchers |
| Docking | **ADS** (Advanced Docking System) | Multi-window/multi-panel |
| Build | **CMake 3.27 + Ninja** | One binary per OS |
| Packaging | windeployqt / AppImage / DMG + QtIFW | Per-OS installers |

### 3.2 Quy mô codebase

| Metric | Số lượng |
|---|---|
| C++ source files (.cpp/.h) | ~1,626 |
| C++ lines of code | ~342,000 |
| Python scripts | ~1,423 |
| Screens (UI panels) | 54 |
| Services | ~50 |
| Broker integrations | 16 equity/F&O + 2 crypto |
| Repositories (typed) | 26 |
| MCP tools | 40+ |
| DataHub topic families | 30+ |
| Python data connectors | 250+ scripts |

### 3.3 Hai Python venvs

| Venv | Mục đích | Thư viện đặc trưng |
|---|---|---|
| `venv-numpy1` | Legacy analytics | vectorbt, gluonts (NumPy 1.x) |
| `venv-numpy2` | Default | qlib, py_vollib, statsmodels, scikit-learn |

---

## 4. PHÂN TÍCH CHI TIẾT 8 CHỨC NĂNG CỐT LÕI

---

### 4.1 MULTI-ASSET ANALYTICS

#### Mô tả tổng quan

Multi-Asset Analytics là bộ công cụ phân tích tài chính toàn diện bao phủ tất cả các lớp tài sản: cổ phiếu (equity), thu nhập cố định (fixed income), phái sinh (derivatives), danh mục đầu tư (portfolio), và tài sản thay thế (alternatives). Đây là "trái tim" của Fincept Terminal.

#### Các screens liên quan

| Screen | Mô tả |
|---|---|
| `equity_research/` | DCF models, fundamental analysis, earnings briefs |
| `portfolio/` | Holdings aggregation, P&L, allocation, optimization |
| `derivatives/` | Option chains, F&O, surface analytics |
| `fno/` | Futures & Options (NSE-focused), PCR, Max Pain, OI |
| `markets/` | Real-time quotes, watchlists, sector heatmaps |
| `surface_analytics/` | Volatility surface, IV percentile |
| `alt_investments/` | Alternative assets |
| `backtesting/` | Strategy backtesting engine |
| `ma_analytics/` | M&A: DCF, merger model, LBO returns |

#### Tính năng chi tiết

**Equity Research:**
- DCF (Discounted Cash Flow) valuation với Python backend
- Fundamental analysis: P/E, P/B, EV/EBITDA, ROE, ROIC
- Earnings brief generation (AI-assisted)
- Sector rotation analysis
- Corporate relationship mapping (yfinance-backed graph)
- Adanos Market Sentiment integration (Reddit, X, Polymarket)

**Portfolio Analytics:**
- Portfolio optimization (Mean-Variance, Black-Litterman)
- Risk metrics: VaR (Value at Risk), CVaR, Sharpe Ratio, Sortino
- P&L tracking real-time qua DataHub `portfolio:*` topics
- Multi-portfolio management (Q3 2026 roadmap)
- Sparklines cho từng holding

**Derivatives / F&O:**
- Option chain với Greeks (Delta, Gamma, Theta, Vega, Rho)
- IV (Implied Volatility) tính qua `option_greeks_daemon.py` (py_vollib)
- ATM IV publishing: `option:atm_iv:<broker>:<underlying>`
- PCR (Put/Call Ratio): `fno:pcr:<broker>:<underlying>:<expiry>`
- Max Pain calculation
- OI (Open Interest) history snapshots (7-day rolling)
- FII/DII daily institutional flows (NSE scraper)
- IV Percentile pill (90-day trailing window)

**Data Sources cho Multi-Asset:**
- Yahoo Finance (yfinance), Polygon.io, Alpha Vantage, Finnhub
- AkShare (China markets: stocks, bonds, futures, funds, REITs)
- Baostock (China A-shares historical + fundamentals)
- EODHD, Tiingo, IEX Cloud, Intrinio, SimFin
- CBOE (VIX data), CME, NYMEX, COMEX, LME (metals)
- Stooq, TradingView, MarketStack

---

---

### 4.2 AI AGENTS

#### Mô tả tổng quan

Hệ thống AI Agents là một trong những tính năng độc đáo nhất của Fincept Terminal. Đây là một **multi-agent framework** hoàn chỉnh được xây dựng trên Python (Agno framework), tích hợp sâu vào C++ runtime qua `PythonRunner` subprocess bridge.

#### Kiến trúc Agent System

```
AgentConfigScreen (C++ UI — 9 panels)
        │
        ▼
AgentService (C++ — discovery, execution, routing)
        │
        ▼ QProcess (PythonRunner)
finagent_core/main.py (Python entry point)
        │
        ├── CoreAgent (single agent execution)
        ├── SuperAgent (routing + multi-agent)
        ├── ExecutionPlanner (DAG-based plans)
        ├── TeamConfig (multi-agent teams)
        └── PaperTradingBridge (agent → paper trades)
```

#### 9 Panels trong Agent Studio

| Panel | Chức năng |
|---|---|
| **AgentsViewPanel** | Duyệt và chọn agent từ registry |
| **CreateAgentPanel** | Tạo agent mới với custom config |
| **TeamsViewPanel** | Cấu hình multi-agent teams (coordinate/route/collaborate) |
| **WorkflowsViewPanel** | Quản lý agent workflows |
| **PlannerViewPanel** | Xem và thực thi execution plans (DAG) |
| **ToolsViewPanel** | Duyệt 40+ MCP tools available cho agents |
| **AgentChatPanel** | Chat trực tiếp với agent đã chọn |
| **SystemViewPanel** | System info: providers, capabilities, frameworks |
| **AgenticTasksPanel** | Monitor agentic tasks (developer mode) |

#### Danh mục Agents (37+ agents)

**Trader/Investor Personas:**
- Warren Buffett (value investing, moat analysis)
- Benjamin Graham (margin of safety, net-net)
- Peter Lynch (growth at reasonable price)
- Charlie Munger (mental models, quality businesses)
- Seth Klarman (deep value, distressed)
- Howard Marks (risk assessment, market cycles)
- Renaissance Technologies (quant/systematic)
- Và nhiều personas khác

**Economic Agents** (`EconomicAgents/`):
- Macro analysis, inflation forecasting
- Central bank policy analysis
- GDP trajectory, yield curve analysis

**Geopolitics Agents** (`GeopoliticsAgents/`):
- Grand Chessboard framework (Brzezinski)
- Prisoners of Geography framework (Tim Marshall)
- Conflict risk assessment
- Trade restriction/benefit analysis

**Deep Agents** (`deepagents/`):
- Multi-backend orchestrator
- Subagent coordination
- Long-horizon research tasks

**RD Agents** (`rdagents/`):
- Research & Development agent với MCP server
- Task management, loop execution

#### Actions được hỗ trợ (finagent_core/main.py)

```
Core:         run, run_team, run_workflow, run_structured
Discovery:    discover_agents, list_agents, create_agent
SuperAgent:   route_query, execute_query, execute_multi_query
Planner:      create_stock_plan, create_portfolio_plan,
              execute_plan, generate_dynamic_plan
Paper Trade:  paper_execute_trade, paper_get_portfolio, paper_get_positions
Repository:   save_session, get_session, add_message,
              save_memory, search_memories, save_trade_decision
Financial:    stock_analysis, portfolio_rebal, risk_assessment,
              macro_scan, earnings_brief, sector_rotation, options_scan
```

#### LLM Providers được hỗ trợ

OpenAI · Anthropic · Google Gemini · Groq · DeepSeek · MiniMax · OpenRouter · Ollama (local)

#### Streaming Mode

Agent output được stream real-time qua stdout với format:
```
THINKING: <reasoning step>
TOKEN: <response token>
TOOL: <tool call>
TOOL_RESULT: <tool result>
ERROR: <error>
DONE: <final>
```
C++ side nhận qua `QProcess` signals và publish lên DataHub `agent:stream:<run_id>`.

---

---

### 4.3 QUANTLIB SUITE

#### Mô tả tổng quan

QuantLib Suite là bộ 18 module phân tích định lượng chuyên sâu, tích hợp thư viện QuantLib (C++) và FinancePy (Python) để thực hiện pricing, risk management, và stochastic modeling cấp chuyên nghiệp.

#### Screens & Files

- `src/screens/quantlib/QuantLibScreen.cpp` — Main screen
- `src/screens/quantlib/QuantLibScreen_Data.cpp` — Data layer
- `scripts/derivatives_pricing.py` — Python pricing backend
- `scripts/financepy_wrapper.py` — FinancePy integration

#### 18 Modules phân tích

| Nhóm | Module | Mô tả |
|---|---|---|
| **Pricing** | Bond Pricing | Yield, duration, convexity, DV01 |
| | Option Pricing | Black-Scholes, Binomial, Monte Carlo |
| | Swap Pricing | IRS, CDS, FX swaps |
| | Futures Pricing | Cost-of-carry, basis |
| **Risk** | VaR Models | Historical, Parametric, Monte Carlo VaR |
| | Stress Testing | Scenario analysis, tail risk |
| | Greeks Calculator | Full option Greeks suite |
| | Credit Risk | PD, LGD, EAD, CVA |
| **Stochastic** | GBM Simulation | Geometric Brownian Motion paths |
| | Heston Model | Stochastic volatility |
| | Jump Diffusion | Merton jump-diffusion |
| | Hull-White | Interest rate model |
| **Volatility** | Vol Surface | Implied vol surface construction |
| | SABR Model | Stochastic Alpha Beta Rho |
| | Local Vol | Dupire local volatility |
| **Fixed Income** | Yield Curve | Bootstrap, interpolation |
| | Duration/Convexity | Modified, effective, key-rate |
| | Inflation Linked | TIPS, linker pricing |

#### DataHub Topics

- `derivatives:*` — Option chain data
- `option:chain:<broker>:<underlying>:<expiry>` — Live chains
- `option:atm_iv:<broker>:<underlying>` — ATM IV scalar
- `fno:pcr:*`, `fno:max_pain:*` — Derived analytics

---

### 4.4 GLOBAL INTELLIGENCE

#### Mô tả tổng quan

Global Intelligence là tập hợp các module theo dõi và phân tích thông tin địa chính trị, hàng hải, kinh tế vĩ mô toàn cầu — một tính năng hiếm thấy trong bất kỳ terminal tài chính nào.

#### Sub-modules

**Geopolitics Screen** (`src/screens/geopolitics/`):

| Panel | Chức năng |
|---|---|
| `ConflictMonitorPanel` | Theo dõi xung đột toàn cầu real-time (ACLED data) |
| `HDXDataPanel` | Humanitarian Data Exchange — dữ liệu nhân đạo UN |
| `RelationshipPanel` | Corporate relationship mapping (graph visualization) |
| `TradeAnalysisPanel` | Phân tích lợi ích/hạn chế thương mại quốc tế |

**Maritime Screen** (`src/screens/maritime/`):
- Theo dõi vị trí tàu theo IMO number
- Area search (bounding box)
- Vessel route history
- AIS stream data (`aisstream_data.py`)
- MarineTraffic integration (`marinetraffic_data.py`)
- Global Fishing Watch (`global_fishing_watch_data.py`)

**Economics Screen** (`src/screens/economics/`):
- FRED (Federal Reserve Economic Data)
- DBnomics (aggregator 100+ statistical agencies)
- IMF, World Bank, OECD, BIS
- ECB, BOJ, BOE, RBA, Riksbank, SNB, NBP...
- Macro calendar với upcoming events

**Government Data** (`src/screens/gov_data/`):
- US: Census, BLS, BEA, FDIC, IRS, HUD, USDA
- EU: Eurostat, ECB SDMX
- UK: ONS, data.gov.uk
- Germany: govdata.de
- Australia: data.gov.au
- Singapore: data.gov.sg
- Hong Kong: data.gov.hk
- Canada: statcan, canada.ca
- France: french_gov_api

#### DataHub Topics

```
geopolitics:events          — Conflict monitor (ACLED)
geopolitics:countries       — Country list với event counts
geopolitics:hdx:<context>   — HDX humanitarian data
geopolitics:trade:<kind>    — Trade benefits/restrictions
maritime:vessel:<imo>       — Single vessel position
maritime:vessels:area       — Area search results
maritime:history:<imo>      — Vessel route history
econ:<source>:<request_id>  — Economics data (FRED, IMF, etc.)
econ:fincept:upcoming_events — Macro calendar
dbnomics:<provider>:<dataset>:<series>
govdata:<provider>:<request_id>
```

#### Data Sources (250+ scripts)

Satellite & Geo: NASA GIBS, Copernicus, Sentinel Hub, N2YO satellite, Open Meteo, NOAA Climate
Conflict: ACLED (`acled_data.py`), HDX (`hdx_data.py`), ReliefWeb
Trade: UN Comtrade, WTO, WITS, Global Trade Alert
Energy: IEA, EIA (petroleum/gas/electricity), ENTSO-E, IRENA, OPEC
Environment: OWID CO2, Climate TRACE, Paris Agreement, Carbon Price
Social: WHO, UNICEF, UNHCR, UNDP, UNESCO, FAO, ILO

---

---

### 4.5 NODE EDITOR (VISUAL WORKFLOW)

#### Mô tả tổng quan

Node Editor là một **visual workflow automation engine** tương tự n8n/Zapier nhưng được tích hợp sâu vào financial data ecosystem. Người dùng kéo-thả các nodes để xây dựng automation pipelines xử lý dữ liệu tài chính, chạy AI agents, và thực thi trading strategies.

#### Kiến trúc

```
NodeEditorScreen
├── NodeCanvas (QGraphicsScene-based)
│   ├── NodeItem — visual node widget
│   ├── EdgeItem — connection line
│   ├── PortItem — input/output ports
│   ├── TempEdge — drag-to-connect preview
│   └── MiniMap — overview minimap
├── NodePalette — node type browser
├── NodePropertiesPanel — parameter editor
├── ExecutionResultsPanel — run output viewer
└── NodeEditorToolbar
    └── DeployDialog — deploy workflow
```

#### Connection Types (typed ports)

```cpp
enum class ConnectionType {
    Main,           // General data flow
    AiLanguageModel,// LLM connections
    AiMemory,       // Agent memory
    AiTool,         // MCP tool connections
    MarketData,     // Real-time quotes
    PortfolioData,  // Portfolio state
    PriceData,      // Price series
    SignalData,     // Trading signals
    RiskData,       // Risk metrics
    BacktestData,   // Backtest results
    TechnicalData,  // Technical indicators
    FundamentalData,// Fundamental data
    NewsData,       // News feed
    EconomicData,   // Macro data
    OptionsData,    // Options chain
};
```

#### Node Categories

| Category | Ví dụ nodes |
|---|---|
| **Triggers** | Manual Trigger, Schedule, Market Open/Close, Price Alert |
| **Data** | Market Quote, News Feed, Economic Data, Portfolio Data |
| **AI/LLM** | LLM Chain, Agent Runner, Tool Caller, Memory Store |
| **Analytics** | Technical Indicator, Backtest Runner, Risk Calculator |
| **Trading** | Order Placer, Position Manager, Paper Trade |
| **Transform** | Filter, Aggregate, Join, Format |
| **Output** | Notification, Report, Webhook, Email |

#### Workflow Definition (JSON-serializable)

```
WorkflowDef {
    id, name, description
    nodes: [NodeDef{id, type, name, x, y, parameters, credentials}]
    edges: [EdgeDef{source_node, target_node, source_port, target_port}]
    status: Draft | Idle | Running | Completed | Error
    static_data: {}
}
```

#### Tích hợp MCP Tools

Node Editor có thể gọi bất kỳ MCP tool nào trong registry 40+ tools thông qua `AiTool` connection type, cho phép workflows tự động hóa các tác vụ như:
- Lấy quote → phân tích → đặt lệnh
- Đọc news → sentiment → rebalance portfolio
- Chạy agent → lấy signal → execute trade

---

---

### 4.6 AI QUANT LAB

#### Mô tả tổng quan

AI Quant Lab là module nghiên cứu định lượng nâng cao, tích hợp **Microsoft Qlib** (AI-oriented quantitative investment platform) cùng nhiều thư viện ML/quant chuyên biệt. Đây là "phòng thí nghiệm" cho quant researchers và algo traders.

#### Kiến trúc

```
AIQuantLabScreen
└── QuantModulePanel (dynamic — 1 panel per module)
    ├── build_*_panel() — module-specific UI builders
    └── display_*_result() — result renderers
```

Backend: `scripts/ai_quant_lab/qlib_*.py` (16 scripts)

#### 25+ Modules chi tiết

**CORE Category:**

| Module | Script | Chức năng |
|---|---|---|
| **Backtesting** | `qlib_advanced_backtest.py` | Backtest strategies với Qlib, performance metrics |
| **Factor Discovery** | `qlib_feature_engineering.py` | Tự động khám phá alpha factors |
| **Model Library** | `qlib_advanced_models.py` | LSTM, LightGBM, XGBoost, TabNet, TFT |
| **Live Signals** | `qlib_service.py` | Real-time trading signals từ trained models |
| **Portfolio Optimization** | `qlib_portfolio_opt.py` | Mean-variance, risk parity, Black-Litterman |

**AI/ML Category:**

| Module | Script | Chức năng |
|---|---|---|
| **RL Trading** | `qlib_rl.py` | Reinforcement Learning trading agents (PPO, SAC, TD3) |
| **Online Learning** | `qlib_online_learning.py` | Incremental model updates với live data |
| **Meta Learning** | `qlib_meta_learning.py` | Few-shot learning cho new markets |

**ADVANCED Category:**

| Module | Script | Chức năng |
|---|---|---|
| **HFT** | `qlib_high_frequency.py` | High-frequency trading signals, microstructure |
| **Rolling Retraining** | `qlib_rolling_retraining.py` | Scheduled model retraining pipeline |
| **Advanced Models** | `qlib_advanced_models.py` | Ensemble, stacking, neural architectures |
| **Feature Engineering** | `qlib_feature_engineering.py` | Alpha158, Alpha360, custom factors |

**ANALYTICS Category:**

| Module | Script | Chức năng |
|---|---|---|
| **GS Quant** | (Goldman Sachs quant library) | Risk analytics, scenario analysis |
| **Functime** | (time-series ML) | Forecasting, anomaly detection |
| **Statsmodels** | (statistical models) | ARIMA, VAR, GARCH, cointegration |
| **Fortitudo** | (portfolio analytics) | Risk decomposition, factor attribution |
| **GluonTS** | (probabilistic forecasting) | Deep learning time-series (venv-numpy1) |
| **CFA Quant** | — | CFA-level quantitative methods |
| **Deep Agent** | `deepagents/` | LangGraph-based research agent |
| **RD Agent** | `rdagents/` | Research & Development automation |

**REPORTING Category:**

| Module | Script | Chức năng |
|---|---|---|
| **Quant Reporting** | `qlib_reporting.py` | Tearsheet, performance attribution |
| **Strategy Builder** | `qlib_strategy.py` | Visual strategy construction |
| **Factor Evaluation** | `qlib_evaluation.py` | IC, ICIR, factor decay analysis |
| **Data Processors** | `qlib_data_processors.py` | Data cleaning, normalization |

#### RL Trading — Chi tiết

Module RL Trading có UI riêng với:
- Progress bar real-time training
- Stats display (episode, reward, Sharpe)
- Log console (plain text)
- Hỗ trợ PPO, SAC, TD3 algorithms
- Environment: custom Gym-compatible financial env

---

---

### 4.7 CRYPTO CENTER

#### Mô tả tổng quan

Crypto Center là hub quản lý tài sản crypto toàn diện, tích hợp Solana wallet, real-time trading trên Kraken/HyperLiquid, và hệ thống tokenomics $FNCPT (community token của Fincept).

#### Kiến trúc Screen

```
CryptoCenterScreen
├── HoldingsBar — top bar hiển thị SOL + token balances
├── Tabs:
│   ├── HomeTab — overview dashboard
│   ├── MarketsTab — crypto market data
│   ├── TradeTab — trading interface
│   ├── StakeTab — veFNCPT staking
│   ├── ActivityTab — wallet transaction history
│   ├── SettingsTab — wallet/API config
│   └── RoadmapTab — product roadmap
└── Panels:
    ├── HoldingsTable — SPL token holdings
    ├── SwapPanel — Jupiter DEX swap
    ├── LockPanel — veFNCPT lock creation
    ├── ActiveLocksPanel — existing lock positions
    ├── TierPanel — Free/Bronze/Silver/Gold tier
    ├── FeeDiscountPanel — 30% discount với 1,000 $FNCPT
    ├── BuybackBurnPanel — buyback & burn dashboard
    ├── TreasuryPanel — treasury reserves
    ├── SupplyChartPanel — token supply history
    └── MarketsListPanel — crypto market list
```

#### Tính năng chi tiết

**Wallet Integration (Solana):**
- Connect Solana wallet qua pubkey
- Balance tracking: SOL + tất cả SPL tokens
- Hai chế độ: polling (30s) hoặc WebSocket stream
- Token metadata: symbol, name, icon (TokenMetadataService)
- Endpoint priority: SecureStorage override → Helius → public RPC

**Real-time Trading:**
- **Kraken**: WebSocket feeds cho ticker, orderbook, trades, OHLC
- **HyperLiquid**: WebSocket feeds (same sub-families)
- Topics: `ws:kraken:ticker:<pair>`, `ws:hyperliquid:*`
- Coalesced 50ms để tránh UI flooding

**Prediction Markets:**
- **Polymarket**: price + orderbook WebSocket (`prediction:polymarket:*`)
- **Kalshi**: price + orderbook (`prediction:kalshi:price:<ticker>:<side>`)
- Internal Fincept markets (Phase 4 — demo mode hiện tại)

**$FNCPT Tokenomics:**
- Token: `9LUqJ5aQTjQiUCL93gi33LZcscUoSBJNhVCYpPzEpump` (Solana)
- Price feed: Jupiter Lite Price API (`lite-api.jup.ag/price/v3`)
- Staking: veFNCPT lock system (4 durations: 6mo/1yr/2yr/4yr)
- Tier system: Free / Bronze (100) / Silver (1,000) / Gold (10,000) veFNCPT
- Fee discount: 30% off AI reports, deep backtests, premium screens
- Buyback & Burn: 50% revenue → buyback, 25% → stakers, 25% → treasury
- Swap: Jupiter DEX integration (`pumpportal.fun/api/trade-local`)

**DataHub Topics:**
```
wallet:balance:<pubkey>         — SOL + SPL token balances
wallet:activity:<pubkey>        — Last 50 parsed transactions
wallet:locks:<pubkey>           — veFNCPT lock positions
wallet:vefncpt:<pubkey>         — Aggregate weight + yield
wallet:yield:<pubkey>           — Realised USDC yield
market:price:token:<mint>       — Token price (Jupiter)
billing:fncpt_discount:<pubkey> — Fee discount eligibility
billing:tier:<pubkey>           — Tier status
treasury:buyback_epoch          — Current buyback epoch
treasury:burn_total             — All-time burn totals
treasury:supply_history         — 12-month supply chart
treasury:reserves               — SOL + USDC treasury holdings
treasury:runway                 — Months of runway
```

---

---

### 4.8 ALPHA ARENA

#### Mô tả tổng quan

Alpha Arena là một **AI trading competition platform** — nơi nhiều LLM models cạnh tranh nhau trong môi trường trading giả lập hoặc live. Đây là tính năng độc đáo nhất của Fincept Terminal, không có trên bất kỳ terminal tài chính nào khác.

#### Kiến trúc

```
AlphaArenaScreen
├── Header: venue badge, status badge, tick counter, countdown
├── CreatePanel: competition config
│   ├── Competition name, mode (paper/live)
│   ├── Venue: Paper | HyperLiquid | US Equity (stub)
│   ├── Capital, cadence (tick interval)
│   ├── Instruments list
│   └── Model list (LLM entries)
└── Main panels (right stack):
    ├── LeaderboardPanel — P&L ranking, win rate
    ├── ModelChatPanel — per-model reasoning stream
    ├── PositionsPanel — live positions per model
    ├── HitlPanel — Human-in-the-Loop approvals
    ├── RiskPanel — circuit breakers, drawdown
    └── AuditPanel — decision audit trail
```

#### Tính năng chi tiết

**Competition Modes:**
- **Paper mode**: Tất cả models trade trên paper trading engine
- **Live mode** (HyperLiquid): Real money, yêu cầu explicit confirmation + disclaimer
- **US Equity** (stub): Planned cho S2

**Model Configuration:**
- Mỗi model entry: `display_name, provider, model_id, api_key, base_url, profile_id`
- Hỗ trợ tất cả LLM providers (OpenAI, Anthropic, Gemini, Groq, DeepSeek, Ollama...)
- Có thể mix nhiều providers trong cùng một competition

**Engine Lifecycle:**
- `AlphaArenaEngine` chạy độc lập với screen (engine keeps running khi hide screen)
- `ModelDispatcher` phân phối market data tới từng model
- `OrderRouter` route orders tới paper/live venue
- Tick-based: mỗi tick → mỗi model nhận data → ra quyết định → execute

**Human-in-the-Loop (HITL):**
- Models có thể request human approval trước khi execute
- `HitlPanel` hiển thị pending approvals với summary
- User approve/reject từng decision
- Circuit breaker tự động khi model vượt drawdown limit

**Leaderboard:**
- Real-time P&L ranking
- Win rate, Sharpe ratio per model
- Decision history với reasoning

**Geofencing:**
- `Geofence.h` — restrict live mode theo jurisdiction
- Live mode gate dialog với legal disclaimer

**DataHub Integration:**
- Engine signals → DataHub topics
- Screens subscribe để nhận live updates
- Crash recovery: state persist trong SQLite

---

---

## 5. PHÂN TÍCH KHẢ NĂNG API HÓA

### 5.1 Tổng quan đánh giá

Câu hỏi: **Có thể expose các chức năng trên thành API để dự án khác kết nối không?**

**Trả lời: Hoàn toàn có thể — và đây là hướng đi rất khả thi.** Dưới đây là phân tích chi tiết từng module.

### 5.2 Đánh giá từng module

#### Module 1: Multi-Asset Analytics → ✅ API hóa dễ

**Lý do khả thi:**
- Backend đã là Python scripts độc lập (250+ scripts), mỗi script nhận JSON input → trả JSON output
- `PythonRunner` hiện tại đã là một subprocess bridge — chỉ cần thêm HTTP layer
- Data sources đã được abstract hóa tốt

**Cách API hóa:**
```
POST /api/v1/analytics/equity/dcf
POST /api/v1/analytics/portfolio/optimize
POST /api/v1/analytics/derivatives/greeks
POST /api/v1/analytics/risk/var
GET  /api/v1/market/quote/{symbol}
GET  /api/v1/market/history/{symbol}?period=1y&interval=1d
```

**Độ phức tạp:** Thấp — Python scripts đã sẵn sàng, chỉ cần FastAPI wrapper

---

#### Module 2: AI Agents → ✅ API hóa rất dễ

**Lý do khả thi:**
- `finagent_core/main.py` đã có JSON protocol hoàn chỉnh
- Input: `{"action": "...", "api_keys": {...}, "params": {...}}`
- Output: JSON response
- Streaming đã được implement (`--stream` flag)

**Cách API hóa:**
```
POST /api/v1/agents/run
     Body: {agent_id, query, llm_config, session_id}

POST /api/v1/agents/run/stream  (SSE/WebSocket)
     Body: {agent_id, query, llm_config}

POST /api/v1/agents/team/run
     Body: {team_config, query}

GET  /api/v1/agents/list?category=trader
GET  /api/v1/agents/{agent_id}/info

POST /api/v1/agents/plan/create
POST /api/v1/agents/plan/execute

POST /api/v1/agents/paper/trade
GET  /api/v1/agents/paper/portfolio/{portfolio_id}
```

**Độ phức tạp:** Rất thấp — chỉ cần wrap `main.py` trong FastAPI

---

#### Module 3: QuantLib Suite → ✅ API hóa dễ

**Lý do khả thi:**
- `derivatives_pricing.py` và `financepy_wrapper.py` đã là standalone scripts
- Input/output đã là JSON

**Cách API hóa:**
```
POST /api/v1/quant/option/price
     Body: {S, K, T, r, sigma, option_type, model}

POST /api/v1/quant/option/greeks
     Body: {S, K, T, r, sigma, option_type}

POST /api/v1/quant/bond/price
     Body: {face_value, coupon_rate, maturity, yield_rate}

POST /api/v1/quant/risk/var
     Body: {returns, confidence_level, method}

POST /api/v1/quant/stochastic/gbm
     Body: {S0, mu, sigma, T, n_paths, n_steps}
```

**Độ phức tạp:** Thấp

---

#### Module 4: Global Intelligence → ✅ API hóa dễ

**Lý do khả thi:**
- Tất cả data fetchers đã là Python scripts độc lập
- Geopolitics, maritime, economics đều có JSON output chuẩn

**Cách API hóa:**
```
GET  /api/v1/geopolitics/events?country=&category=&limit=
GET  /api/v1/geopolitics/hdx/{context}
GET  /api/v1/maritime/vessel/{imo}
POST /api/v1/maritime/vessels/area
     Body: {lat_min, lat_max, lon_min, lon_max}
GET  /api/v1/economics/fred/{series_id}
GET  /api/v1/economics/worldbank/{indicator}/{country}
GET  /api/v1/economics/imf/{dataset}/{series}
GET  /api/v1/macro/calendar?limit=25
```

**Độ phức tạp:** Thấp — scripts đã sẵn sàng

---

#### Module 5: Node Editor → ⚠️ API hóa trung bình

**Lý do khả thi nhưng phức tạp hơn:**
- Workflow definition đã là JSON-serializable (`WorkflowDef`)
- Execution engine cần được tách ra khỏi Qt UI
- Cần implement workflow executor độc lập (không phụ thuộc Qt)

**Cách API hóa:**
```
POST /api/v1/workflow/create
     Body: WorkflowDef JSON

POST /api/v1/workflow/{id}/execute
GET  /api/v1/workflow/{id}/status
GET  /api/v1/workflow/{id}/results
GET  /api/v1/workflow/nodes/types  — list available node types
```

**Độ phức tạp:** Trung bình — cần tách execution engine

---

#### Module 6: AI Quant Lab → ✅ API hóa dễ

**Lý do khả thi:**
- 16 Qlib scripts đã là standalone với JSON I/O
- `qlib_service.py` đã có service layer

**Cách API hóa:**
```
POST /api/v1/quant-lab/backtest
     Body: {strategy, symbols, start_date, end_date, params}

POST /api/v1/quant-lab/train
     Body: {model_type, symbols, features, params}

POST /api/v1/quant-lab/signals
     Body: {model_id, symbols, date}

POST /api/v1/quant-lab/portfolio/optimize
     Body: {symbols, method, constraints}

POST /api/v1/quant-lab/rl/train
     Body: {algorithm, env_config, training_params}
```

**Độ phức tạp:** Thấp-Trung bình

---

#### Module 7: Crypto Center → ⚠️ API hóa trung bình

**Lý do:**
- Wallet operations cần private key management (security concern)
- WebSocket feeds cần persistent connections
- Swap/trade operations cần careful auth design

**Cách API hóa (read-only phần an toàn):**
```
GET  /api/v1/crypto/wallet/{pubkey}/balance
GET  /api/v1/crypto/wallet/{pubkey}/activity
GET  /api/v1/crypto/market/{pair}/ticker
GET  /api/v1/crypto/market/{pair}/orderbook
GET  /api/v1/crypto/token/{mint}/price
GET  /api/v1/crypto/prediction/polymarket/markets
WS   /api/v1/crypto/stream/{exchange}/{pair}
```

**Độ phức tạp:** Trung bình (read) / Cao (write/trade)

---

#### Module 8: Alpha Arena → ⚠️ API hóa phức tạp

**Lý do:**
- Engine state management phức tạp
- HITL flow cần real-time bidirectional communication
- Live trading mode có risk cao

**Cách API hóa:**
```
POST /api/v1/arena/competition/create
POST /api/v1/arena/competition/{id}/start
GET  /api/v1/arena/competition/{id}/leaderboard
GET  /api/v1/arena/competition/{id}/positions
WS   /api/v1/arena/competition/{id}/stream
POST /api/v1/arena/hitl/{approval_id}/resolve
```

**Độ phức tạp:** Cao

---

---

## 6. ĐỀ XUẤT KIẾN TRÚC API GATEWAY

### 6.1 Kiến trúc tổng thể đề xuất

```
┌─────────────────────────────────────────────────────────────┐
│                    External Clients                         │
│         (Web Apps, Mobile, Other Services, Scripts)         │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTPS / WebSocket
┌──────────────────────▼──────────────────────────────────────┐
│              Fincept API Gateway (FastAPI)                  │
│  Auth (JWT/API Key) · Rate Limiting · Request Validation    │
│  OpenAPI 3.0 Docs · Versioning (/api/v1/)                  │
└──────┬──────────┬──────────┬──────────┬──────────┬──────────┘
       │          │          │          │          │
┌──────▼──┐ ┌────▼────┐ ┌───▼───┐ ┌───▼───┐ ┌───▼────────┐
│ Agent   │ │Analytics│ │ Quant │ │ Geo/  │ │  Crypto    │
│ Service │ │ Service │ │  Lab  │ │ Mari- │ │  Service   │
│(Python) │ │(Python) │ │(Qlib) │ │ time  │ │ (Solana)   │
└─────────┘ └─────────┘ └───────┘ └───────┘ └────────────┘
       │          │          │          │          │
       └──────────┴──────────┴──────────┴──────────┘
                             │
              ┌──────────────▼──────────────┐
              │    Fincept Terminal Core     │
              │  (C++/Qt — optional bridge)  │
              └─────────────────────────────┘
```

### 6.2 Stack đề xuất cho API Server

```python
# Recommended stack
fastapi          # HTTP framework
uvicorn          # ASGI server
pydantic v2      # Request/response validation
redis            # Caching + rate limiting
celery           # Async task queue (cho long-running analytics)
websockets       # Real-time streaming
sqlalchemy       # Session/API key management
```

### 6.3 Ví dụ implementation — Agent API

```python
# api/routes/agents.py
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
import subprocess, json, asyncio

router = APIRouter(prefix="/api/v1/agents")

@router.post("/run")
async def run_agent(request: AgentRunRequest, user=Depends(auth)):
    payload = {
        "action": "run",
        "api_keys": user.api_keys,
        "params": {"query": request.query, "session_id": request.session_id},
        "config": {"agent_id": request.agent_id},
        "active_llm": request.llm_config
    }
    result = await run_python_script(
        "scripts/agents/finagent_core/main.py",
        json.dumps(payload)
    )
    return result

@router.post("/run/stream")
async def run_agent_stream(request: AgentRunRequest, user=Depends(auth)):
    async def event_generator():
        payload = {..., "params": {"stream": True}}
        async for line in stream_python_script("main.py", payload):
            yield f"data: {line}\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

### 6.4 Ví dụ implementation — Analytics API

```python
# api/routes/analytics.py
@router.post("/equity/dcf")
async def dcf_valuation(request: DCFRequest):
    # Gọi trực tiếp Python script
    result = await run_script("scripts/yfinance_data.py", {
        "action": "dcf",
        "symbol": request.symbol,
        "params": request.model_dump()
    })
    return result

@router.get("/market/quote/{symbol}")
async def get_quote(symbol: str, cache: Redis = Depends(get_cache)):
    cached = await cache.get(f"quote:{symbol}")
    if cached:
        return json.loads(cached)
    result = await run_script("scripts/yfinance_data.py", {
        "action": "quote", "symbol": symbol
    })
    await cache.setex(f"quote:{symbol}", 5, json.dumps(result))
    return result
```

### 6.5 Roadmap API hóa theo độ ưu tiên

| Ưu tiên | Module | Effort | Business Value |
|---|---|---|---|
| 🔴 **P1** | AI Agents API | 1-2 tuần | Rất cao — unique feature |
| 🔴 **P1** | Analytics API (quotes, history) | 1 tuần | Cao — core data |
| 🟡 **P2** | QuantLib / Derivatives API | 2 tuần | Cao — niche market |
| 🟡 **P2** | AI Quant Lab API | 2-3 tuần | Cao — ML/quant users |
| 🟢 **P3** | Global Intelligence API | 2 tuần | Trung bình |
| 🟢 **P3** | Crypto read-only API | 1 tuần | Trung bình |
| ⚪ **P4** | Node Editor API | 3-4 tuần | Thấp-Trung bình |
| ⚪ **P4** | Alpha Arena API | 4-6 tuần | Thấp (niche) |

---

---

## 7. RỦI RO & LƯU Ý

### 7.1 License — Quan trọng nhất

> ⚠️ **CẢNH BÁO NGHIÊM TRỌNG**

Fincept Terminal có **dual license** với điều khoản rất chặt:

- **AGPL-3.0**: Chỉ cho cá nhân, học thuật, open-source contributions
- **Commercial License**: Bắt buộc cho **mọi** mục đích thương mại

**Nếu bạn build API từ codebase này để expose cho dự án khác:**
- Nếu dự án đó có mục đích thương mại → **phải mua Commercial License**
- Nếu fork và thay thế Fincept APIs bằng nguồn khác → **vẫn phải có license**
- Vi phạm: liquidated damages **$50,000 USD/tổ chức/năm** + backdated fees

**Khuyến nghị:** Liên hệ `support@fincept.in` trước khi build bất kỳ API nào.

### 7.2 Rủi ro kỹ thuật

| Rủi ro | Mức độ | Giải pháp |
|---|---|---|
| Python cold-start 0.5-1.5s/call | Cao | Persistent worker pool (đang plan) |
| 40+ singletons khó test | Trung bình | Dependency injection (Phase 9) |
| Monolithic CMakeLists.txt 3,300 LOC | Thấp | Per-module CMake (Phase 8) |
| Screens không unload (100-250MB/window) | Trung bình | Lazy unload (Phase 12) |
| EventBus stringly-typed, O(n) | Thấp | Typed event manifest (Phase 10) |
| 13 shallow Python-wrapper services | Thấp | Consolidation (Phase 5) |

### 7.3 Rủi ro bảo mật khi API hóa

| Surface | Rủi ro | Mitigation |
|---|---|---|
| API keys (broker, LLM) | Leak qua logs/responses | Không log keys, mask trong responses |
| SecureStorage (AES-256-GCM) | Key từ machineUniqueId | Không expose SecureStorage qua API |
| Broker credentials | Unauthorized trading | Auth + rate limiting + HITL |
| Python subprocess | Code injection | Validate all inputs, sandbox |
| Live trading API | Financial loss | Explicit confirmation, limits |

### 7.4 Phụ thuộc bên ngoài

Nhiều data sources yêu cầu API keys riêng:
- Polygon.io, Alpha Vantage, Finnhub, EODHD, Tiingo
- Helius (Solana RPC), MarineTraffic
- LLM providers (OpenAI, Anthropic, Gemini, Groq...)
- Databento (institutional market data)

Một số sources miễn phí nhưng có rate limits:
- Yahoo Finance (yfinance) — không chính thức, có thể bị block
- FRED, World Bank, IMF, OECD — free với registration

---

## 8. KẾT LUẬN

### 8.1 Đánh giá tổng thể

Fincept Terminal là một dự án **cực kỳ tham vọng và ấn tượng về mặt kỹ thuật**:

| Điểm mạnh | Điểm yếu |
|---|---|
| Native C++20 performance, không Electron | Python cold-start latency |
| Kiến trúc layered rõ ràng, DataHub pub/sub | 40+ singletons khó test |
| 250+ data connectors đã implement | License thương mại nghiêm ngặt |
| AI Agents framework hoàn chỉnh | Một số screens vi phạm architecture rules |
| Alpha Arena — unique feature | Screens không unload (memory) |
| Qlib ML lab tích hợp sâu | Monolithic CMakeLists.txt |
| Crypto + DeFi integration | Python subprocess bridge có latency |

### 8.2 Khả năng API hóa — Tóm tắt

| Module | Khả năng | Effort | Ghi chú |
|---|---|---|---|
| Multi-Asset Analytics | ✅ Cao | Thấp | Scripts đã sẵn sàng |
| AI Agents | ✅ Rất cao | Rất thấp | JSON protocol đã có |
| QuantLib Suite | ✅ Cao | Thấp | Scripts standalone |
| Global Intelligence | ✅ Cao | Thấp | Scripts standalone |
| Node Editor | ⚠️ Trung bình | Trung bình | Cần tách execution engine |
| AI Quant Lab | ✅ Cao | Thấp-TB | Qlib scripts sẵn sàng |
| Crypto Center | ⚠️ Trung bình | Trung bình | Read-only dễ, write phức tạp |
| Alpha Arena | ⚠️ Thấp-TB | Cao | Engine phức tạp |

### 8.3 Khuyến nghị hành động

1. **Ngay lập tức**: Kiểm tra license với Fincept Corporation trước khi build bất kỳ thứ gì
2. **Quick win**: Wrap `finagent_core/main.py` trong FastAPI → có Agent API trong 1-2 tuần
3. **Trung hạn**: Build Analytics API từ Python scripts → data platform cho internal use
4. **Dài hạn**: Nếu muốn production API, cần giải quyết Python cold-start bằng persistent worker pool

---

*Báo cáo được tạo bởi phân tích source code tại `g:\Code\AI-APP\FinceptTerminal`*
*Kiến trúc tham chiếu: `docs/ARCHITECTURE.md` v5.0.0-draft (2026-05-15)*
*Ngày phân tích: 18/05/2026*

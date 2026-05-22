# Implementation Plan — Fincept × QuantDinger Integration

## Overview

Tích hợp Fincept Analytics (FastAPI, port 8081) vào QuantDinger (Flask + Vue 2, port 5005/8888).

- **Nguyên tắc bất biến:** Không phá vỡ QuantDinger hiện tại. Không sửa DB schema QD. Analytics chạy độc lập.
- **Approach:** JWT Bridge → Proxy Layer → UI Components (từng phase)
- **Trạng thái:** 🔄 Đang lên kế hoạch

## Tổng quan tiến độ

| Phase | Tên | Mô tả | Trạng thái |
|---|---|---|---|
| 1 | JWT Bridge + Proxy | Hạ tầng kết nối, auth chéo, shared DB/Redis | ⬜ |
| 2 | Chat với Memory | Thay stub ai_chat.py + UI chat (Vue 2) | ⬜ |
| 3 | AI Agents UI | Gallery personas + run console (Vue 2) | ⬜ |
| 4 | News Feed UI | Realtime news + WebSocket (Vue 2) | ⬜ |
| 5 | Stock Analysis UI | 7-tab comprehensive analysis (Vue 2) | ⬜ |
| 6 | Polish | i18n, health banner, monitoring | ⬜ |

**Legend:** ⬜ chưa bắt đầu · 🔄 đang làm · ✅ xong · ❌ blocked · ⏸ tạm dừng

---

## Phase 1 — JWT Bridge + Reverse Proxy

> **Mục tiêu:** QD JWT được Analytics chấp nhận. Request từ QD_Frontend đến `/analytics/*` được route đúng đến Analytics:8081. Không có tính năng UI nào, chỉ hạ tầng.

### Backend — Analytics side

- [x] 1.1 Đồng bộ DATABASE_URL và Redis giữa QD và Analytics
  - Sửa `analytics/.env`: `DATABASE_URL=postgresql+asyncpg://quantdinger:quantdinger123@localhost:5435/quantdinger`
  - Verify Redis: cả hai dùng `localhost:6379/0` — QD không có prefix, Analytics dùng `analytics:` → không conflict
  - Verify: `SELECT schema_name FROM information_schema.schemata` → phải có `analytics` sau migration
  - _Validates: Req 8.3, 8.4_

- [x] 1.2 Chạy Alembic migration tạo schema `analytics.*` trên DB QD
  - `cd analytics && alembic upgrade head`
  - Verify: 6 tables tạo trong schema `analytics` (news_sources, news_articles, chat_sessions, chat_messages, agent_runs, audit_log)
  - Không ảnh hưởng schema `public` (nơi QD lưu `qd_users`, `qd_strategies`, v.v.)
  - _Validates: Req 8.3, 8.4_

- [x] 1.3 Cấu hình `QUANTDINGER_JWT_SECRET` trong `analytics/.env`
  - Đặt `QUANTDINGER_JWT_SECRET` = giá trị `SECRET_KEY` trong `quant-dinger/backend_api_python/.env`
  - Giá trị hiện tại: `0cf13f1ff25b73a6c682a5d82818a99b4b428206d6c5176bbf69fb4968de374f`
  - Verify `analytics/core/auth.py` đã có `verify_quantdinger_jwt()` function
  - _Validates: Req 1.1, 1.2, 1.3_

- [x] 1.4 Fix User ID mapping — QD dùng integer, Analytics cần string
  - Sửa `analytics/core/auth.py` → `verify_quantdinger_jwt()`: convert `user_id` (int) thành `str(user_id)` cho internal use
  - Sửa `analytics/models/db/chat.py`: `user_id` column type từ `UUID` → `Text` (hoặc giữ UUID nhưng generate deterministic UUID từ int: `uuid5(NAMESPACE_URL, str(user_id))`)
  - **Quyết định:** Dùng `str(user_id)` trực tiếp — đơn giản nhất, không cần sửa DB schema
  - Sửa `_get_session_owned()` trong `chat.py` để so sánh string thay vì UUID
  - _Validates: Req 1.5_

- [x] 1.5 Chuẩn hóa QD JWT claims trong Analytics
  - Map `{sub: username, user_id: int, role}` → internal User dict `{sub: str(user_id), role, email: null, source: "quantdinger"}`
  - Cache kết quả verify trong Redis TTL 300s
  - _Validates: Req 1.5, 1.6_

- [x] 1.6 Test JWT Bridge end-to-end
  - Tạo `analytics/tests/test_jwt_bridge_qd.py`
  - Test: QD JWT hợp lệ (tạo bằng QD SECRET_KEY) → 200
  - Test: QD JWT expired → 401
  - Test: QD JWT sai signature → 401
  - Test: `QUANTDINGER_JWT_SECRET` trống → JWT bridge disabled
  - _Validates: Req 1.1–1.7_

### Backend — QD side

- [x] 1.4 Thêm `ANALYTICS_BASE_URL` vào QD `.env`
  - Thêm `ANALYTICS_BASE_URL=http://localhost:8081` vào `quant-dinger/backend_api_python/.env`
  - Thêm vào `quant-dinger/backend_api_python/env.example`
  - _Validates: Req 8.1_

- [x] 1.5 Tạo `analytics_proxy.py` helper trong QD_Backend
  - Tạo `quant-dinger/backend_api_python/app/utils/analytics_proxy.py`
  - Function `proxy_to_analytics(path, method, headers, body, stream=False)` — forward request đến Analytics, đính kèm JWT của user hiện tại
  - Handle timeout, connection error → raise `AnalyticsUnavailableError`
  - Handle streaming response (SSE) — yield chunks
  - _Validates: Req 3.1, 3.2, 8.2, 8.7_

- [x] 1.6 Tạo health check endpoint trong QD_Backend
  - Thêm `GET /api/health/analytics` vào `quant-dinger/backend_api_python/app/routes/health.py`
  - Gọi `GET {ANALYTICS_BASE_URL}/health`, đo latency_ms
  - Trả về `{status: "ok"|"unavailable", latency_ms, error?}` với HTTP 200 luôn
  - _Validates: Req 10.1, 10.2, 10.3_

### Reverse Proxy

- [x] 1.9 Cấu hình webpack devServer proxy cho development
  - Sửa `quant-dinger/frontend/vue.config.js` thêm proxy rule:
    ```js
    '/analytics': { target: 'http://localhost:8081', changeOrigin: true, pathRewrite: {'^/analytics': ''} }
    ```
  - Thêm WebSocket proxy: `ws: true`
  - _Validates: Req 2.1 (dev mode)_

- [x] 1.10 Cấu hình Caddy reverse proxy (production)
  - Tạo/cập nhật `quant-dinger/frontend/deploy/caddy.conf` (đã có file này)
  - Thêm block: `handle /analytics/* { uri strip_prefix /analytics; reverse_proxy localhost:8081 { flush_interval -1 } }`
  - Thêm WebSocket support: `transport http { versions h1 h1c }`
  - _Validates: Req 2.1–2.6_

- [x] 1.11 Cấu hình Nginx reverse proxy (alternative)
  - Cập nhật `quant-dinger/frontend/deploy/nginx.conf` hoặc `nginx-docker.conf`
  - Thêm `location /analytics/ { proxy_pass http://localhost:8081/; proxy_buffering off; }`
  - Thêm WebSocket headers: `proxy_http_version 1.1; proxy_set_header Upgrade $http_upgrade;`
  - _Validates: Req 2.1–2.6_

**Test Gate Phase 1:**
- [x] QD JWT được Analytics verify thành công
- [x] `GET /api/health/analytics` trả về `{status: "ok"}`
- [x] `curl -H "Authorization: Bearer <QD_JWT>" http://localhost:8081/api/v1/health` → 200
- [x] Analytics không khả dụng → QD vẫn khởi động, health check trả về `{status: "unavailable"}`

---

## Phase 2 — Chat với Memory

> **Mục tiêu:** Thay thế stub `ai_chat.py` trong QD_Backend bằng proxy thực đến Analytics. Thêm UI chat đầy đủ vào QD_Frontend với server-side memory.

### Backend — QD side

- [x] 2.1 Thay thế `ai_chat.py` bằng proxy thực
  - Sửa `quant-dinger/backend_api_python/app/routes/ai_chat.py`
  - `POST /api/ai-chat/chat/message` → proxy đến `POST /analytics/api/v1/chat/completions` với streaming
  - `POST /api/ai-chat/sessions` → proxy đến `POST /analytics/api/v1/chat/sessions`
  - `GET /api/ai-chat/sessions` → proxy đến `GET /analytics/api/v1/chat/sessions`
  - `DELETE /api/ai-chat/sessions/{id}` → proxy đến `DELETE /analytics/api/v1/chat/sessions/{id}`
  - `GET /api/ai-chat/presets` → proxy đến `GET /analytics/api/v1/chat/presets`
  - Tất cả endpoints đều require `@login_required`
  - _Validates: Req 3.1–3.10_

- [x] 2.2 Implement streaming proxy trong QD_Backend
  - Sửa `POST /api/ai-chat/chat/message` để stream SSE response từ Analytics về client
  - Dùng Flask `Response(stream_with_context(...))` với `mimetype='text/event-stream'`
  - Request body: `{message, session_id?, llm_config?}` → transform thành Analytics format `{messages: [{role: "user", content: message}], session_id, history_limit: 20, llm_config, stream: true}`
  - _Validates: Req 3.2, 3.7_

- [x] 2.3 Error handling cho Analytics unavailable
  - Wrap tất cả proxy calls với try/except `AnalyticsUnavailableError`
  - Trả về HTTP 503 với `{code: 503, msg: "Analytics service unavailable"}` khi Analytics down
  - _Validates: Req 3.8_

### Frontend — QD side

- [x] 2.4 Tạo API client `ai-chat.js` trong QD_Frontend
  - Tạo `quant-dinger/frontend/src/api/ai-chat.js`
  - Functions: `createSession(title, presetId)`, `listSessions()`, `deleteSession(id)`, `sendMessage(sessionId, message, llmConfig)`, `listPresets()`
  - `sendMessage` dùng `fetch` với `ReadableStream` để handle SSE streaming
  - _Validates: Req 4.3, 4.4_

- [x] 2.5 Tạo component `AiChat.vue` (Vue 2 Options API)
  - Tạo `quant-dinger/frontend/src/views/ai-chat/index.vue`
  - **PHẢI dùng Vue 2 Options API** — không dùng `<script setup>` hay Composition API
  - Layout 2 cột: sidebar sessions (trái) + khung chat (phải)
  - Sidebar: danh sách sessions, nút "New Chat", nút xóa session
  - Khung chat: message list, input box, nút gửi
  - Streaming: render từng token khi nhận SSE (dùng `fetch` + `ReadableStream`)
  - Loading indicator khi đang stream
  - Tham khảo style: `views/ai-analysis/index.vue` (Vue 2 component hiện có)
  - _Validates: Req 4.1–4.9_

- [x] 2.6 Tạo component `NewSessionModal.vue`
  - Modal tạo session mới với dropdown chọn preset
  - Presets: stock_analysis, macro_outlook, options_strategy, portfolio_review, news_summary
  - Gọi `GET /api/ai-chat/presets` để load danh sách
  - _Validates: Req 4.5_

- [x] 2.7 Thêm route `/ai-chat` vào router config
  - Sửa `quant-dinger/frontend/src/config/router.config.js`
  - Thêm route `/ai-chat` với component `AiChat`, icon `message`, permission `['dashboard']`
  - Thêm vào sidebar menu (sau AI Asset Analysis)
  - _Validates: Req 4.1_

- [x] 2.8 Thêm i18n keys cho Chat UI
  - Thêm keys vào `quant-dinger/frontend/src/locales/lang/en-US.js`
  - Thêm keys vào `quant-dinger/frontend/src/locales/lang/zh-CN.js`
  - Keys: `menu.dashboard.aiChat`, `aiChat.newChat`, `aiChat.sendMessage`, `aiChat.selectPreset`, v.v.
  - _Validates: Req 12.1–12.3_

**Test Gate Phase 2:**
- [x] Tạo session mới với preset → session được lưu trong Analytics DB
- [x] Gửi tin nhắn → nhận streaming response từng token
- [x] Gửi tin nhắn thứ 2 trong cùng session → AI nhớ context từ tin nhắn trước (server-side memory)
- [x] Xóa session → session biến mất khỏi danh sách
- [x] Analytics down → hiển thị "Analytics service unavailable" thay vì crash

---

## Phase 3 — AI Agents UI

> **Mục tiêu:** Thêm trang AI Agents vào QD_Frontend, cho phép user chọn persona và chạy agent với SSE streaming.

### Frontend — QD side

- [x] 3.1 Tạo API client `ai-agents.js` trong QD_Frontend
  - Tạo `quant-dinger/frontend/src/api/ai-agents.js`
  - Functions: `listAgents(category?)`, `runAgent(agentId, query, llmConfig)`, `runAgentStream(agentId, query, llmConfig)`, `getRunHistory(params)`
  - `runAgentStream` dùng `fetch` với `ReadableStream` để handle SSE
  - _Validates: Req 5.3, 5.4_

- [x] 3.2 Tạo component `AgentGallery.vue`
  - Grid layout hiển thị 37+ personas
  - Mỗi card: avatar (SVG initials), tên, mô tả ngắn, category badge
  - Filter theo category: trader, economic, geopolitics, analyst, quant
  - Search box lọc theo tên/mô tả
  - Click card → mở `AgentRunConsole`
  - _Validates: Req 5.2_

- [ ] 3.3 Tạo component `AgentRunConsole.vue`
  - Top: persona info + LLM config form (model, api_key, base_url)
  - Middle: stream area với event types:
    - `thinking` → italic, màu xám
    - `token` → text bình thường
    - `tool` → code block với tool name
    - `done` → success badge xanh
    - `error` → alert đỏ
  - Bottom: textarea input + nút Run/Stop
  - SSE via `fetch` POST (không dùng EventSource vì cần POST body)
  - _Validates: Req 5.3, 5.4, 5.7, 5.8_

- [~] 3.4 Tạo component `AgentRunHistory.vue`
  - List các lần chạy trước của user
  - Columns: persona, query (truncated), status badge, duration, date
  - Click row → expand chi tiết
  - Cursor pagination với "Load more"
  - _Validates: Req 5.5, 5.6_

- [~] 3.5 Tạo page `AiAgents.vue` và thêm route
  - Tạo `quant-dinger/frontend/src/views/ai-agents/index.vue`
  - Tabs: "Agent Gallery" + "Run History"
  - Thêm route `/ai-agents` vào router config với icon `robot`
  - _Validates: Req 5.1_

- [~] 3.6 Thêm i18n keys cho Agents UI
  - Thêm vào `en-US.js` và `zh-CN.js`
  - Keys: `menu.dashboard.aiAgents`, `aiAgents.gallery`, `aiAgents.runHistory`, v.v.
  - _Validates: Req 12.1–12.3_

**Test Gate Phase 3:**
- [~] Trang `/ai-agents` hiển thị ≥ 30 personas
- [~] Chọn persona, nhập query, nhấn Run → nhận SSE stream với thinking/token/done events
- [~] Run history hiển thị các lần chạy trước
- [~] Filter theo category hoạt động đúng

---

## Phase 4 — News Feed UI

> **Mục tiêu:** Thêm trang News Feed vào QD_Frontend với realtime WebSocket và filter theo ticker.

### Frontend — QD side

- [~] 4.1 Tạo API client `news.js` trong QD_Frontend
  - Tạo `quant-dinger/frontend/src/api/news.js`
  - Functions: `listNews(params)`, `searchNews(query)`, `getNewsById(id)`
  - `params`: `{ticker, source, sentiment_min, sentiment_max, from, to, limit, cursor}`
  - _Validates: Req 6.2, 6.6_

- [~] 4.2 Tạo component `NewsCard.vue`
  - Hiển thị: tiêu đề (link), nguồn, thời gian, tóm tắt (truncated)
  - Sentiment badge: xanh (> 0.1), đỏ (< -0.1), xám (neutral)
  - Tickers tags
  - Click → mở detail modal hoặc link gốc
  - _Validates: Req 6.2_

- [~] 4.3 Tạo component `NewsFilter.vue`
  - Filter sidebar: ticker input, sentiment range, source, date range
  - Search box cho full-text search
  - Emit filter change events
  - _Validates: Req 6.5, 6.6_

- [~] 4.4 Tạo component `NewsLive.vue` (WebSocket)
  - Connect đến `ws://{host}/analytics/ws/news?ticker={ticker}`
  - Auto reconnect sau 3 giây khi disconnect
  - Backfill: gửi `since` timestamp khi reconnect
  - Fallback về polling 30s nếu WebSocket không khả dụng
  - Push bài viết mới lên đầu danh sách
  - _Validates: Req 6.3, 6.4, 6.8_

- [~] 4.5 Tạo page `NewsFeed.vue` và thêm route
  - Tạo `quant-dinger/frontend/src/views/news/index.vue`
  - Layout: filter sidebar (trái) + news list (phải)
  - Infinite scroll hoặc "Load more" với cursor pagination
  - Tích hợp `NewsLive` cho realtime updates
  - _Validates: Req 6.1, 6.7_

- [~] 4.6 Thêm i18n keys cho News UI
  - Thêm vào `en-US.js` và `zh-CN.js`
  - Keys: `menu.dashboard.news`, `news.filter`, `news.sentiment`, v.v.
  - _Validates: Req 12.1–12.3_

**Test Gate Phase 4:**
- [~] Trang `/news` hiển thị danh sách bài viết với sentiment badges
- [~] Filter theo ticker "AAPL" → chỉ hiển thị bài viết có AAPL
- [~] WebSocket connect → bài viết mới xuất hiện realtime
- [~] WebSocket disconnect → tự reconnect sau 3s
- [~] Search "federal reserve" → hiển thị kết quả FTS

---

## Phase 5 — Stock Analysis Page

> **Mục tiêu:** Thêm trang Stock Analysis 7-tab vào QD_Frontend, tích hợp comprehensive endpoint của Analytics.

### Frontend — QD side

- [~] 5.1 Tạo API client `stock-analysis.js` trong QD_Frontend
  - Tạo `quant-dinger/frontend/src/api/stock-analysis.js`
  - Functions: `comprehensiveAnalysis(symbol, params)`, `getDcf(symbol, params)`, `getHistory(symbol, params)`
  - _Validates: Req 7.2_

- [~] 5.2 Tạo component `StockOverview.vue`
  - KPI cards: price, change%, market cap, P/E, sentiment score
  - Company info: sector, industry, description
  - _Validates: Req 7.3 (tab Overview)_

- [~] 5.3 Tạo component `StockChart.vue`
  - Candlestick hoặc line chart từ historical data
  - Dùng lightweight-charts (Apache 2.0) hoặc ECharts
  - Zoom, tooltip, period selector (1D, 1W, 1M, 3M, 1Y)
  - _Validates: Req 7.3 (tab Chart), 7.6_

- [~] 5.4 Tạo component `StockFundamentals.vue`
  - Bảng IS/BS/CF với toggle annual/quarterly
  - Format số: B/M/K suffix
  - _Validates: Req 7.3 (tab Fundamentals)_

- [~] 5.5 Tạo component `StockDcf.vue`
  - Form inputs: growth rate, discount rate, terminal growth, projection years (sliders)
  - Intrinsic value display với margin of safety
  - Nút "Recalculate" gọi lại DCF endpoint với params mới
  - _Validates: Req 7.3 (tab DCF), 7.7_

- [~] 5.6 Tạo component `StockTechnicals.vue`
  - Cards cho RSI, MACD, Bollinger Bands, SMA, EMA
  - Signal badge: Buy/Sell/Neutral
  - _Validates: Req 7.3 (tab Technicals)_

- [~] 5.7 Tạo page `StockAnalysis.vue` và thêm route
  - Tạo `quant-dinger/frontend/src/views/stock-analysis/index.vue`
  - Symbol search bar ở top
  - 7 tabs: Overview, Chart, Fundamentals, DCF, Technicals, News, AI Analysis
  - Load data một lần từ comprehensive endpoint, chia cho các tabs
  - Recent symbols trong localStorage
  - Thêm route `/stock-analysis` vào router config
  - _Validates: Req 7.1–7.9_

- [~] 5.8 Thêm i18n keys cho Stock Analysis UI
  - Thêm vào `en-US.js` và `zh-CN.js`
  - Keys: `menu.dashboard.stockAnalysis`, `stock.tabs.*`, v.v.
  - _Validates: Req 12.1–12.3_

**Test Gate Phase 5:**
- [~] Nhập "AAPL" → comprehensive endpoint trả về data trong < 8s
- [~] 7 tabs hiển thị đúng dữ liệu tương ứng
- [~] Tab DCF: thay đổi growth rate → recalculate intrinsic value
- [~] Tab Chart: zoom, tooltip hoạt động
- [~] Symbol không tồn tại → hiển thị error message rõ ràng

---

## Phase 6 — Polish & Monitoring

> **Mục tiêu:** i18n đầy đủ, health check banner, monitoring. (Bỏ LLM config UI — dùng server-side default)

### Frontend — QD side

- [~] 6.1 Thêm Analytics health banner
  - Tạo component `AnalyticsStatusBanner.vue` (Vue 2 Options API)
  - Gọi `GET /api/health/analytics` khi load trang có Analytics features
  - Hiển thị banner cảnh báo nếu Analytics unavailable
  - _Validates: Req 10.5_

- [~] 6.2 Hoàn thiện i18n cho tất cả tính năng mới
  - Review và bổ sung keys còn thiếu trong `en-US.js` và `zh-CN.js`
  - Thêm `vi-VN.js` (tiếng Việt) cho các keys mới
  - _Validates: Req 12.1–12.3_

- [~] 6.3 Thêm menu labels vào router config
  - Đảm bảo tất cả routes mới có `meta.title` dùng i18n key
  - Thêm menu keys vào tất cả locale files
  - _Validates: Req 12.3_

### Backend — QD side

- [~] 6.6 Thêm `ANALYTICS_BASE_URL` vào `env.example`
  - Cập nhật `quant-dinger/backend_api_python/env.example` với comment giải thích
  - _Validates: Req 8.1_

- [~] 6.7 Logging và security hardening
  - Đảm bảo QD_Backend không log nội dung chat (chỉ log metadata)
  - Đảm bảo `llm_config.api_key` không xuất hiện trong logs
  - _Validates: Req 11.4, 11.6_

**Test Gate Phase 6 (Final):**
- [~] Settings page có section Analytics với LLM config
- [~] LLM config được dùng trong chat và agents requests
- [~] Analytics down → banner cảnh báo hiển thị trên tất cả trang Analytics
- [~] Tất cả string UI có i18n key, không có hardcoded text
- [~] Không có API key nào xuất hiện trong logs

---

## Task Dependency Graph

```mermaid
flowchart LR
  P1[Phase 1<br/>JWT Bridge + Proxy]
  P2[Phase 2<br/>Chat + Memory]
  P3[Phase 3<br/>AI Agents UI]
  P4[Phase 4<br/>News Feed UI]
  P5[Phase 5<br/>Stock Analysis UI]
  P6[Phase 6<br/>Polish]

  P1 --> P2
  P1 --> P3
  P1 --> P4
  P1 --> P5
  P2 --> P6
  P3 --> P6
  P4 --> P6
  P5 --> P6
```

**Critical path:** Phase 1 → Phases 2/3/4/5 (parallel) → Phase 6

---

## Ghi chú kỹ thuật quan trọng

### Shared DB + Redis — Cùng instance, khác namespace
- **Postgres:** Cùng DB `quantdinger` trên `localhost:5435`. QD dùng schema `public` (tables: `qd_users`, `qd_strategies`, `qd_analysis_memory`, ...). Analytics dùng schema `analytics` (tables: `chat_sessions`, `chat_messages`, `agent_runs`, ...). Không conflict.
- **Redis:** Cùng `localhost:6379/0`. QD dùng keys trực tiếp (vd: `kline:BTCUSDT:1H`, `cache:market:...`). Analytics dùng prefix `analytics:` (vd: `analytics:cache:...`, `analytics:rate:...`). Không conflict.
- **Quan trọng:** Analytics `.env` phải dùng cùng credentials/port với QD: `postgresql+asyncpg://quantdinger:quantdinger123@localhost:5435/quantdinger`

### Vue 2 — QD_Frontend là frontend DUY NHẤT
- **`fincept-web/` đã bị xóa** — không dùng, không tham khảo
- QD_Frontend dùng **Vue 2.6** + **Ant Design Vue 1.x** + **Options API**
- Tất cả components mới viết trực tiếp trong `quant-dinger/frontend/src/`
- Syntax bắt buộc:
  - Options API (`data()`, `methods`, `computed`, `mounted`)
  - Ant Design Vue 1.x components (`a-card`, `a-button`, `a-table`, `a-tabs`)
  - Không dùng `<script setup>`, `ref()`, `computed()` từ Vue 3
  - Không dùng `useI18n()` — dùng `this.$t('key')` thay thế
- Tham khảo style từ `quant-dinger/frontend/src/views/ai-analysis/index.vue` (Vue 2 component hiện có)

### LLM Config — Server-side default, không cần UI config
- QD và Analytics đều dùng chung **chainhub.tech** (`https://api.chainhub.tech/v1`)
- Analytics đọc LLM config từ `.env` (`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`)
- QD_Backend khi proxy chat/agents → **KHÔNG gửi `llm_config` trong body** — Analytics tự dùng server default
- **Bỏ Requirement 9** (LLM config trong Settings UI) — không cần
- User không cần cấu hình gì — chỉ cần chat/run agent là xong

### Nguyên tắc tối thiểu sửa QD (đang chạy prod)
- **QD_Backend:** Chỉ thêm file mới (`analytics_proxy.py`), sửa `ai_chat.py` (hiện là stub). KHÔNG sửa auth, DB, services hiện có
- **QD_Frontend:** Chỉ thêm views/components/routes mới. KHÔNG sửa components hiện có
- **DB:** KHÔNG sửa schema `public`. Chỉ thêm schema `analytics.*` (Alembic migration)
- **Redis:** KHÔNG sửa keys hiện có. Analytics dùng prefix `analytics:` riêng

### JWT Bridge — Vấn đề `user_id` type
- QD JWT payload: `{sub: "quantdinger", user_id: 1, role: "admin", token_version: 1}`
- `user_id` là **integer** (auto-increment từ `qd_users.id`)
- Analytics `chat_sessions.user_id` hiện là **UUID** type
- **Giải pháp:** Sửa Analytics để dùng `Text` type cho `user_id` column, hoặc convert `int → str` khi compare
- Đơn giản nhất: dùng `str(user_id)` làm identifier trong Analytics, so sánh bằng string

### Server-Side Memory — Cách hoạt động
QD_Frontend chỉ gửi tin nhắn mới nhất. Analytics tự inject history:
```
Request từ QD_Frontend: {messages: [{role: "user", content: "Hôm nay AAPL thế nào?"}], session_id: "abc", history_limit: 20}
Analytics inject: [system prompt] + [20 messages gần nhất từ DB] + [tin nhắn mới]
```

### Streaming SSE qua Flask proxy
Flask cần dùng `stream_with_context` để proxy SSE:
```python
from flask import Response, stream_with_context
import requests

def proxy_sse(analytics_url, headers, body):
    r = requests.post(analytics_url, json=body, headers=headers, stream=True)
    return Response(stream_with_context(r.iter_content(chunk_size=None)),
                    content_type='text/event-stream')
```

### WebSocket qua Nginx/Caddy
WebSocket cần HTTP/1.1 và Upgrade header. Caddy config:
```
handle /analytics/ws/* {
    reverse_proxy localhost:8081 {
        transport http { versions h1 h1c }
    }
}
```

### LLM Config trong QD_Frontend
Lưu vào localStorage với key `analytics_llm_config`:
```json
{
  "base_url": "https://api.chainhub.tech/v1",
  "model": "gpt-4o-mini",
  "api_key": "sk-...xxxx"  // masked khi hiển thị
}
```

---

## Notes

### Quy tắc track tiến độ
1. Mỗi task hoàn thành → đánh `[x]` ở đây
2. Phase hoàn thành → chạy Test Gate + update bảng Tổng quan tiến độ
3. Không bắt đầu Phase tiếp theo khi Phase hiện tại chưa pass Test Gate

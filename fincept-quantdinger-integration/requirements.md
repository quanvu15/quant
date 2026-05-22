# Requirements Document

## Introduction

Tích hợp Fincept Analytics (FastAPI, port 8081) vào QuantDinger (Flask + Vue 2, port 5005/8888) theo mô hình microservice. QuantDinger đóng vai trò frontend/orchestrator; Analytics chạy độc lập và cung cấp các tính năng AI nâng cao: chat với server-side memory, 37+ AI personas, news feed realtime, và phân tích cổ phiếu toàn diện.

Tích hợp được thực hiện theo 6 phase:
- **Phase 1**: JWT Bridge + Reverse Proxy (hạ tầng)
- **Phase 2**: Chat với Memory (thay thế stub `ai_chat.py` + UI chat trong QD)
- **Phase 3**: AI Agents UI trong QD frontend
- **Phase 4**: News Feed trong QD frontend
- **Phase 5**: Stock Analysis page trong QD frontend
- **Phase 6**: Polish (i18n, settings, monitoring)

Nguyên tắc bất biến: không phá vỡ QuantDinger hiện tại — không xóa/sửa DB schema QD, không thay đổi auth flow QD, Analytics chạy như microservice độc lập.

---

## Glossary

- **QD_Backend**: Flask Python backend của QuantDinger, port 5005
- **QD_Frontend**: Vue 2 + Ant Design Vue frontend của QuantDinger, port 8888
- **Analytics**: FastAPI backend của Fincept Analytics, port 8081
- **JWT_Bridge**: Cơ chế cho phép JWT do QD_Backend cấp được Analytics xác thực, dùng shared secret `QUANTDINGER_JWT_SECRET`
- **Proxy_Layer**: Tầng proxy trong QD_Backend chuyển tiếp request đến Analytics, đính kèm JWT của user hiện tại
- **Reverse_Proxy**: Caddy hoặc Nginx route `/analytics/*` → Analytics:8081
- **Chat_Session**: Phiên chat được lưu trong DB của Analytics (`analytics.chat_sessions`), gắn với `user_id` từ JWT
- **Server_Side_Memory**: Tính năng Analytics tự inject lịch sử hội thoại từ DB vào LLM call — client chỉ gửi tin nhắn mới nhất
- **AI_Persona**: Một trong 37+ nhân vật AI (Buffett, Lynch, Munger...) được định nghĩa trong Analytics agents module
- **SSE**: Server-Sent Events — cơ chế streaming một chiều từ server đến client
- **Analysis_Memory**: Bảng `qd_analysis_memory` trong DB của QD, lưu kết quả AI analysis — KHÔNG liên quan đến Chat_Session
- **QD_JWT_Payload**: Payload của JWT do QD_Backend cấp: `{sub: username, user_id, role, token_version}`

---

## Requirements

---

### Requirement 1: JWT Bridge — Xác thực chéo giữa QuantDinger và Analytics

**User Story:** Là một người dùng đã đăng nhập vào QuantDinger, tôi muốn truy cập các tính năng của Analytics mà không cần đăng nhập lại, để trải nghiệm liền mạch trong một ứng dụng duy nhất.

#### Acceptance Criteria

1. WHEN `QUANTDINGER_JWT_SECRET` trong `.env` của Analytics được đặt bằng giá trị `SECRET_KEY` của QD_Backend, THE Analytics SHALL xác thực JWT do QD_Backend cấp mà không yêu cầu đăng nhập riêng.
2. WHEN Analytics nhận một Bearer token hợp lệ do QD_Backend cấp (HS256, payload chứa `sub`, `user_id`, `role`), THE Analytics SHALL trả về HTTP 200 và xử lý request bình thường.
3. WHEN Analytics nhận một Bearer token không hợp lệ hoặc đã hết hạn, THE Analytics SHALL trả về HTTP 401 với `code: AUTH_REQUIRED`.
4. WHEN `QUANTDINGER_JWT_SECRET` để trống trong `.env` của Analytics, THE Analytics SHALL bỏ qua JWT bridge và chỉ chấp nhận JWT native của Analytics.
5. THE Analytics SHALL chuẩn hóa claims từ QD JWT (`sub`, `user_id`, `role`) thành User dict nội bộ với shape nhất quán `{sub, role, email, source: "quantdinger"}`.
6. WHEN Analytics xác thực thành công một QD JWT, THE Analytics SHALL cache kết quả trong Redis với TTL 300 giây để tránh verify lại mỗi request.
7. IF `QUANTDINGER_JWT_SECRET` khớp với `SECRET_KEY` của QD_Backend nhưng token đã hết hạn (`exp` trong quá khứ), THEN THE Analytics SHALL trả về HTTP 401 và không cache kết quả.

---

### Requirement 2: Reverse Proxy — Định tuyến `/analytics/*` đến Analytics

**User Story:** Là một developer, tôi muốn QD_Frontend có thể gọi Analytics API qua cùng một domain/port với QD, để tránh CORS issues và đơn giản hóa cấu hình client.

#### Acceptance Criteria

1. THE Reverse_Proxy SHALL định tuyến tất cả request có path prefix `/analytics/` đến Analytics tại `http://localhost:8081/`, loại bỏ prefix `/analytics` trước khi forward.
2. WHEN Reverse_Proxy forward request, THE Reverse_Proxy SHALL giữ nguyên header `Authorization`, `Content-Type`, và tất cả custom headers của client.
3. WHEN Analytics trả về response dạng SSE (`Content-Type: text/event-stream`), THE Reverse_Proxy SHALL disable buffering (`X-Accel-Buffering: no`) để đảm bảo streaming hoạt động real-time.
4. WHEN Analytics trả về response dạng WebSocket upgrade, THE Reverse_Proxy SHALL forward WebSocket connection đến Analytics.
5. IF Analytics không khả dụng (connection refused hoặc timeout), THEN THE Reverse_Proxy SHALL trả về HTTP 502 với message rõ ràng cho client.
6. THE Reverse_Proxy SHALL được cấu hình bằng file config (Caddyfile hoặc nginx.conf) được commit vào repository, không hardcode.

---

### Requirement 3: Chat Proxy — Thay thế stub `ai_chat.py` bằng proxy đến Analytics

**User Story:** Là một người dùng QuantDinger, tôi muốn chat với AI trong giao diện QD và nhận phản hồi có ngữ cảnh từ lịch sử hội thoại, để không phải lặp lại thông tin mỗi lần chat.

#### Acceptance Criteria

1. WHEN QD_Backend nhận `POST /api/ai-chat/chat/message` với JWT hợp lệ, THE QD_Backend SHALL forward request đến `POST /api/v1/chat/completions` của Analytics, đính kèm JWT của user hiện tại trong header `Authorization`.
2. WHEN Analytics trả về response dạng SSE streaming, THE QD_Backend SHALL stream response đó trực tiếp đến QD_Frontend mà không buffer toàn bộ nội dung.
3. WHEN QD_Backend nhận `POST /api/ai-chat/sessions` (tạo session mới), THE QD_Backend SHALL proxy đến `POST /api/v1/chat/sessions` của Analytics và trả về `session_id` cho client.
4. WHEN QD_Backend nhận `GET /api/ai-chat/sessions` (danh sách sessions), THE QD_Backend SHALL proxy đến `GET /api/v1/chat/sessions` của Analytics và trả về danh sách sessions thuộc user hiện tại.
5. WHEN QD_Backend nhận `DELETE /api/ai-chat/sessions/{id}`, THE QD_Backend SHALL proxy đến `DELETE /api/v1/chat/sessions/{id}` của Analytics.
6. THE Chat_Session trong Analytics SHALL được gắn với `user_id` từ QD JWT, đảm bảo mỗi user chỉ thấy sessions của mình.
7. THE Server_Side_Memory SHALL hoạt động tự động: client QD_Frontend chỉ gửi tin nhắn mới nhất, Analytics tự inject lịch sử từ DB vào LLM call với `history_limit` mặc định là 20.
8. IF Analytics không khả dụng khi QD_Backend proxy request, THEN THE QD_Backend SHALL trả về HTTP 503 với message `"Analytics service unavailable"` thay vì crash.
9. THE QD_Backend SHALL không lưu nội dung chat vào bảng `qd_analysis_memory` — bảng này chỉ dùng cho AI analysis results, không phải chat sessions.
10. WHEN QD_Backend nhận `GET /api/ai-chat/presets` (danh sách system prompt presets), THE QD_Backend SHALL proxy đến `GET /api/v1/chat/presets` của Analytics.

---

### Requirement 4: Chat UI trong QD_Frontend

**User Story:** Là một người dùng QuantDinger, tôi muốn có giao diện chat AI trong ứng dụng, để tôi có thể hỏi về thị trường và nhận phân tích từ AI mà không cần rời khỏi ứng dụng.

#### Acceptance Criteria

1. THE QD_Frontend SHALL thêm route `/ai-chat` với component `AiChat` vào router config, hiển thị trong sidebar với icon phù hợp.
2. WHEN người dùng mở trang `/ai-chat`, THE QD_Frontend SHALL hiển thị danh sách sessions bên trái và khung chat bên phải (layout 2 cột).
3. WHEN người dùng gõ tin nhắn và nhấn Enter hoặc nút gửi, THE QD_Frontend SHALL gửi `POST /api/ai-chat/chat/message` với `{message, session_id}` và hiển thị phản hồi streaming từng token.
4. WHEN Analytics trả về SSE streaming, THE QD_Frontend SHALL render từng token ngay khi nhận được, không chờ response hoàn chỉnh.
5. WHEN người dùng tạo session mới, THE QD_Frontend SHALL cho phép chọn preset (stock_analysis, macro_outlook, options_strategy, portfolio_review, news_summary) từ dropdown.
6. WHEN người dùng chọn một session từ danh sách, THE QD_Frontend SHALL load lịch sử tin nhắn của session đó và hiển thị trong khung chat.
7. WHEN người dùng xóa một session, THE QD_Frontend SHALL hiển thị confirm dialog trước khi gọi API xóa.
8. IF request chat thất bại (network error hoặc 5xx), THEN THE QD_Frontend SHALL hiển thị thông báo lỗi rõ ràng và cho phép retry.
9. WHILE streaming đang diễn ra, THE QD_Frontend SHALL hiển thị loading indicator và disable nút gửi để tránh gửi trùng.

---

### Requirement 5: AI Agents UI trong QD_Frontend

**User Story:** Là một nhà đầu tư sử dụng QuantDinger, tôi muốn tương tác với các AI personas chuyên biệt (Buffett, Lynch, Munger...) để nhận phân tích đầu tư theo phong cách của từng nhà đầu tư huyền thoại.

#### Acceptance Criteria

1. THE QD_Frontend SHALL thêm route `/ai-agents` với component `AiAgents` vào router config, hiển thị trong sidebar.
2. WHEN người dùng mở trang `/ai-agents`, THE QD_Frontend SHALL gọi `GET /analytics/api/v1/agents` và hiển thị danh sách 37+ personas dưới dạng card grid, mỗi card gồm tên, mô tả ngắn, và avatar/icon.
3. WHEN người dùng chọn một persona và nhập câu hỏi rồi nhấn "Run", THE QD_Frontend SHALL gọi `POST /analytics/api/v1/agents/run` với `{persona_id, query}` và hiển thị kết quả streaming.
4. WHEN Analytics trả về SSE với event types `thinking`, `token`, `tool`, `done`, THE QD_Frontend SHALL render từng event type với style khác nhau: `thinking` hiển thị italic/mờ, `token` hiển thị nội dung chính, `tool` hiển thị badge công cụ đang dùng, `done` kết thúc stream.
5. WHEN agent run hoàn thành, THE QD_Frontend SHALL hiển thị nút "Xem lịch sử" để truy cập run history của persona đó.
6. WHEN người dùng xem run history, THE QD_Frontend SHALL gọi `GET /analytics/api/v1/agents/runs` với cursor pagination và hiển thị danh sách các lần chạy trước.
7. IF agent run thất bại (timeout hoặc lỗi từ Analytics), THEN THE QD_Frontend SHALL hiển thị thông báo lỗi và cho phép retry với cùng input.
8. WHILE agent đang chạy, THE QD_Frontend SHALL hiển thị progress indicator và disable nút "Run" để tránh chạy trùng.

---

### Requirement 6: News Feed UI trong QD_Frontend

**User Story:** Là một trader sử dụng QuantDinger, tôi muốn xem tin tức tài chính realtime được phân tích sentiment, để nắm bắt thông tin thị trường kịp thời ngay trong ứng dụng.

#### Acceptance Criteria

1. THE QD_Frontend SHALL thêm route `/news` với component `NewsFeed` vào router config, hiển thị trong sidebar.
2. WHEN người dùng mở trang `/news`, THE QD_Frontend SHALL gọi `GET /analytics/api/v1/news` và hiển thị danh sách bài viết với: tiêu đề, nguồn, thời gian, tóm tắt, sentiment score (màu xanh/đỏ/xám), và danh sách tickers liên quan.
3. WHEN người dùng kết nối WebSocket tại `/ws/news`, THE QD_Frontend SHALL nhận và hiển thị bài viết mới realtime mà không cần refresh trang.
4. WHEN WebSocket bị ngắt kết nối, THE QD_Frontend SHALL tự động reconnect sau 3 giây và backfill các bài viết bị bỏ lỡ trong thời gian mất kết nối.
5. WHEN người dùng nhập ticker vào ô lọc (ví dụ: "AAPL", "TSLA"), THE QD_Frontend SHALL lọc danh sách chỉ hiển thị bài viết có ticker đó trong trường `tickers`.
6. WHEN người dùng nhập từ khóa vào ô tìm kiếm, THE QD_Frontend SHALL gọi `GET /analytics/api/v1/news/search?q={keyword}` và hiển thị kết quả.
7. THE QD_Frontend SHALL hỗ trợ infinite scroll hoặc "Load more" button để tải thêm bài viết cũ qua cursor pagination.
8. IF WebSocket không được hỗ trợ bởi browser hoặc bị block bởi proxy, THEN THE QD_Frontend SHALL fallback về polling `GET /analytics/api/v1/news` mỗi 30 giây.

---

### Requirement 7: Stock Analysis Page trong QD_Frontend

**User Story:** Là một nhà phân tích sử dụng QuantDinger, tôi muốn xem phân tích toàn diện của một cổ phiếu bao gồm dữ liệu cơ bản, kỹ thuật, DCF, và ý kiến AI, để đưa ra quyết định đầu tư có căn cứ.

#### Acceptance Criteria

1. THE QD_Frontend SHALL thêm route `/stock-analysis` với component `StockAnalysis` vào router config, hiển thị trong sidebar.
2. WHEN người dùng nhập mã cổ phiếu (ví dụ: "AAPL") và nhấn "Phân tích", THE QD_Frontend SHALL gọi `POST /analytics/api/v1/analytics/comprehensive/{symbol}` và hiển thị kết quả trong 7 tabs.
3. THE QD_Frontend SHALL hiển thị 7 tabs: **Overview** (thông tin tổng quan, giá hiện tại, market cap), **Chart** (biểu đồ giá lịch sử), **Fundamentals** (P/E, EPS, revenue, margins), **DCF** (định giá DCF với intrinsic value), **Technicals** (RSI, MACD, Bollinger Bands), **News** (tin tức liên quan đến cổ phiếu), **AI Analysis** (ý kiến từ AI persona).
4. WHEN người dùng chuyển tab, THE QD_Frontend SHALL không gọi lại API — dữ liệu đã được load một lần từ comprehensive endpoint và chia cho các tab.
5. WHEN comprehensive endpoint trả về dữ liệu, THE QD_Frontend SHALL hiển thị loading skeleton trong khi chờ và render kết quả ngay khi nhận được.
6. WHEN tab **Chart** được hiển thị, THE QD_Frontend SHALL render biểu đồ candlestick hoặc line chart từ dữ liệu lịch sử giá, hỗ trợ zoom và tooltip.
7. WHEN tab **DCF** được hiển thị, THE QD_Frontend SHALL cho phép người dùng điều chỉnh các tham số DCF (growth rate, discount rate, terminal growth, projection years) và gọi lại `POST /analytics/api/v1/analytics/dcf/{symbol}` với tham số mới.
8. IF comprehensive endpoint trả về lỗi (symbol không tồn tại hoặc data không khả dụng), THEN THE QD_Frontend SHALL hiển thị thông báo lỗi cụ thể và cho phép thử lại với symbol khác.
9. THE QD_Frontend SHALL lưu symbol đã tìm kiếm gần đây vào localStorage và hiển thị gợi ý khi người dùng bắt đầu nhập.

---

### Requirement 8: Cấu hình môi trường và không phá vỡ hệ thống hiện tại

**User Story:** Là một system administrator, tôi muốn tích hợp được cấu hình qua biến môi trường và không ảnh hưởng đến các tính năng hiện có của QuantDinger, để triển khai an toàn và rollback dễ dàng.

#### Acceptance Criteria

1. THE QD_Backend SHALL đọc URL của Analytics từ biến môi trường `ANALYTICS_BASE_URL` (mặc định: `http://localhost:8081`), không hardcode URL trong code.
2. WHEN `ANALYTICS_BASE_URL` không được đặt hoặc Analytics không khả dụng, THE QD_Backend SHALL tiếp tục hoạt động bình thường với tất cả các tính năng hiện có (strategy, backtest, portfolio, market data).
3. THE Analytics SHALL chỉ đọc/ghi vào schema `analytics.*` của PostgreSQL, không truy cập schema `public` (nơi QD lưu dữ liệu). Cả hai dùng chung database `quantdinger` trên cùng Postgres instance.
4. THE Analytics SHALL dùng chung Redis instance với QD nhưng tất cả keys phải có prefix `analytics:` để tránh collision với keys của QD (không có prefix).
5. WHEN `QUANTDINGER_JWT_SECRET` trong Analytics `.env` được đặt bằng `SECRET_KEY` của QD_Backend, THE JWT_Bridge SHALL hoạt động; WHEN để trống, THE JWT_Bridge SHALL bị tắt mà không gây lỗi.
6. THE QD_Frontend SHALL không thay đổi bất kỳ route, component, hoặc API call nào hiện có — chỉ thêm routes và components mới.
7. IF `ANALYTICS_BASE_URL` không thể kết nối được khi QD_Backend khởi động, THEN THE QD_Backend SHALL log warning nhưng vẫn khởi động thành công.
8. THE Analytics `.env` SHALL dùng cùng `DATABASE_URL` (host, port, credentials, database name) với QD_Backend, chỉ khác ở driver prefix (`postgresql+asyncpg://` thay vì `postgresql://`) và schema isolation (`DB_SCHEMA=analytics`).
9. THE Analytics `.env` SHALL dùng cùng Redis host/port với QD_Backend (`REDIS_HOST`, `REDIS_PORT`), phân biệt bằng `REDIS_KEY_PREFIX=analytics:`.

---

### Requirement 9: LLM Config — Server-side default (không cần UI)

**User Story:** ~~Là một người dùng QuantDinger, tôi muốn cấu hình LLM provider...~~

> **ĐÃ BỎ** — Cả QD và Analytics đều dùng chung chainhub.tech. Analytics đọc LLM config từ `.env` server-side. User không cần cấu hình gì trong UI.

#### Acceptance Criteria

1. THE Analytics SHALL đọc LLM config từ biến môi trường (`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`) và dùng làm default cho tất cả chat/agent requests.
2. WHEN QD_Backend proxy chat/agent request đến Analytics, THE QD_Backend SHALL KHÔNG đính kèm `llm_config` trong body — Analytics tự dùng server default.
3. IF cần thay đổi LLM provider, THE admin SHALL sửa `analytics/.env` và restart Analytics — không cần UI.

---

### Requirement 10: Monitoring và Health Check

**User Story:** Là một system administrator, tôi muốn biết trạng thái kết nối giữa QD và Analytics, để phát hiện và xử lý sự cố kịp thời.

#### Acceptance Criteria

1. THE QD_Backend SHALL expose endpoint `GET /api/health/analytics` trả về trạng thái kết nối đến Analytics (reachable/unreachable, latency_ms).
2. WHEN Analytics khả dụng, THE `GET /api/health/analytics` SHALL trả về `{status: "ok", latency_ms: <số>}`.
3. WHEN Analytics không khả dụng, THE `GET /api/health/analytics` SHALL trả về `{status: "unavailable", error: <message>}` với HTTP 200 (không phải 5xx — đây là health check, không phải lỗi của QD).
4. THE Analytics SHALL expose endpoint `GET /api/v1/health` trả về `{status: "ok", version, uptime_seconds}`.
5. WHEN QD_Frontend load trang có tính năng Analytics (chat, agents, news, stock analysis), THE QD_Frontend SHALL kiểm tra `GET /api/health/analytics` và hiển thị banner cảnh báo nếu Analytics không khả dụng.

---

### Requirement 11: Bảo mật và phân quyền

**User Story:** Là một system administrator, tôi muốn đảm bảo người dùng chỉ truy cập được dữ liệu của mình trong Analytics, để bảo vệ tính riêng tư và bảo mật dữ liệu.

#### Acceptance Criteria

1. WHEN QD_Backend proxy request đến Analytics, THE QD_Backend SHALL luôn đính kèm JWT của user hiện tại — không bao giờ dùng master API key hoặc service account chung cho tất cả users.
2. THE Analytics SHALL enforce ownership check trên mọi Chat_Session operation: user chỉ có thể đọc/xóa sessions có `user_id` khớp với `sub` trong JWT.
3. WHEN một user cố truy cập session của user khác, THE Analytics SHALL trả về HTTP 404 (không phải 403, để tránh information disclosure).
4. THE QD_Backend SHALL không log nội dung tin nhắn chat vào application log — chỉ log metadata (session_id, user_id, latency_ms).
5. THE Analytics SHALL không trả về `api_key` hoặc `llm_config.api_key` trong bất kỳ response nào — chỉ dùng để forward đến LLM provider.
6. WHEN QD_Frontend gửi `llm_config.api_key` trong request body, THE QD_Backend SHALL forward nguyên vẹn đến Analytics mà không log giá trị key.

---

### Requirement 12: Internationalisation (i18n) cho các tính năng mới

**User Story:** Là một người dùng QuantDinger, tôi muốn giao diện các tính năng mới (chat, agents, news, stock analysis) hỗ trợ đa ngôn ngữ như phần còn lại của ứng dụng, để trải nghiệm nhất quán.

#### Acceptance Criteria

1. THE QD_Frontend SHALL thêm tất cả string UI của các tính năng mới vào file i18n (`src/locales/`) với ít nhất 2 ngôn ngữ: tiếng Anh (`en-US`) và tiếng Trung (`zh-CN`).
2. WHEN người dùng thay đổi ngôn ngữ trong Settings, THE QD_Frontend SHALL cập nhật tất cả label, placeholder, và thông báo của các tính năng mới ngay lập tức mà không cần reload trang.
3. THE QD_Frontend SHALL thêm menu keys mới vào `src/config/router.config.js` với `meta.title` dùng i18n key (ví dụ: `menu.dashboard.aiChat`, `menu.dashboard.aiAgents`).

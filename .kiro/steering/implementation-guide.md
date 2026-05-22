---
inclusion: auto
---

# Hướng dẫn triển khai — Fincept API Project

Đây là bộ quy tắc **bắt buộc** cho mọi agent làm việc trong dự án này.
Đọc kỹ toàn bộ file này trước khi bắt đầu bất kỳ task nào.

---

## 1. TÀI LIỆU THAM CHIẾU BẮT BUỘC

Trước khi làm bất cứ việc gì, agent phải nắm rõ 3 file sau:

| File | Vai trò | Đọc khi nào |
|---|---|---|
| `PLAN.md` | **Nguồn sự thật duy nhất** về roadmap, tasks, endpoints, tech stack | Đầu mỗi phiên làm việc |
| `WORKLOGS.md` | Lịch sử công việc đã làm, quyết định kỹ thuật | Đầu mỗi phiên để biết đang ở đâu |
| `BAOCAT_DUAN.md` | Phân tích kiến trúc Fincept Terminal gốc, source scripts | Khi cần hiểu sâu về module |

**Quy tắc vàng:** Nếu PLAN.md nói làm X, hãy làm X. Không tự ý thay đổi scope, tech stack, hay thứ tự phases mà không hỏi lại.

---

## 2. QUY TRÌNH LÀM VIỆC CHUẨN

### Bước 1 — Định hướng trước khi làm (LUÔN LUÔN)

Trước khi bắt đầu bất kỳ task nào, agent phải:

1. **Đọc PLAN.md** — xác định task cần làm thuộc Phase nào, Task ID là gì
2. **Đọc WORKLOGS.md** — xem các task trước đã làm gì, có quyết định kỹ thuật nào ảnh hưởng không
3. **Xác nhận dependency** — task này có phụ thuộc task nào chưa xong không?
   - Phase 0 phải xong trước khi làm Phase 1–5
   - Phase 6 phải sau khi tất cả Phase 1–5 xong
4. **Xác nhận scope** — đọc kỹ mô tả task, sub-tasks, và Deliverables của Phase đó

### Bước 2 — Làm đúng theo PLAN.md

- Làm **đúng task được giao**, không làm thêm task khác trong cùng phiên trừ khi được yêu cầu
- Tuân thủ **tech stack đã định** trong PLAN.md (FastAPI, Pydantic v2, Redis, Celery cho Phase 5)
- Tuân thủ **cấu trúc thư mục** đã định:
  ```
  fincept-api/app/routers/    ← router files
  fincept-api/core/           ← shared infrastructure
  fincept-api/models/         ← Pydantic models
  fincept-api/tests/          ← test files
  ```
- Tuân thủ **endpoint URL pattern**: `/api/v1/{module}/{resource}`
- Tuân thủ **error response schema** đã định trong PLAN.md

### Bước 3 — Cập nhật tiến độ (xem steering/progress-tracking.md)

Sau khi hoàn thành task: cập nhật WORKLOGS.md và đánh `[x]` trong PLAN.md.

---

## 3. NGUYÊN TẮC KỸ THUẬT BẮT BUỘC

### 3.1 Python Runner — Cách gọi scripts

Scripts Fincept nằm tại `fincept-qt/scripts/`. Cách gọi đúng:

```python
# ĐÚNG — dùng async subprocess với stdin
payload = {"action": "...", "params": {...}}
result = await python_runner.run("scripts/yfinance_data.py", payload)

# SAI — KHÔNG gọi script trực tiếp bằng import trong FastAPI process
# (trừ derivatives_pricing.py và các pure-math functions — xem Phase 3)
```

Với **Phase 3 QuantLib** — các hàm pure math (`black_scholes_price`, `black_scholes_greeks`) được **import trực tiếp** vào FastAPI process để đạt latency < 10ms. Đây là ngoại lệ có chủ đích, không áp dụng cho các scripts khác.

### 3.2 Output format chuẩn

Tất cả scripts đã dùng `fincept_output_standard.py`. Response từ script có dạng:
```json
{
  "success": true,
  "data": {"type": "dict|table|array|timeseries", "value": {...}},
  "metadata": {"script": "...", "execution_time_ms": 123}
}
```
API layer phải **unwrap** `data.value` trước khi trả về client, không trả raw script output.

### 3.3 Cache — Tuân thủ TTL đã định

Không tự ý đặt TTL khác với PLAN.md. Bảng TTL chuẩn:

| Data type | TTL |
|---|---|
| Market quote (real-time) | 5s |
| Market history (daily) | 300s |
| Equity info/fundamentals | 3600s |
| DCF valuation | 1800s |
| Agent list | 300s |
| FRED/economics series | 3600s |
| Geopolitics events | 120s |
| Maritime vessel | 60s |
| Option price | 60s |

### 3.4 Authentication — Không bao giờ log API keys

```python
# ĐÚNG
env = {**os.environ, "OPENAI_API_KEY": request.llm_config.api_key}
# SAI — KHÔNG log, KHÔNG include trong error messages
logger.info(f"Running with key: {request.llm_config.api_key}")  # CẤM
```

### 3.5 Async Jobs (Phase 5) — Dùng Celery

Phase 5 có long-running tasks (training ML models 5–60 phút). **Bắt buộc** dùng Celery + Redis, không dùng `asyncio.create_task` hay `BackgroundTasks` của FastAPI cho training jobs.

---

## 4. KHI NÀO PHẢI HỎI LẠI (KHÔNG TỰ Ý QUYẾT ĐỊNH)

Agent **PHẢI dừng lại và hỏi người dùng** trong các tình huống sau:

### 4.1 Scope thay đổi
- Khi task trong PLAN.md không đủ rõ để implement
- Khi cần thêm endpoint/feature không có trong PLAN.md
- Khi muốn bỏ bớt endpoint/feature đã có trong PLAN.md

### 4.2 Tech stack conflict
- Khi thư viện trong PLAN.md có conflict với thư viện khác
- Khi phiên bản Python/FastAPI/Pydantic không tương thích
- Khi muốn dùng thư viện khác thay thế (ví dụ: dùng aioredis thay redis-py)

### 4.3 Architecture decision
- Khi cần thay đổi cấu trúc thư mục so với PLAN.md
- Khi cần thêm service/component mới không có trong plan
- Khi phát hiện dependency giữa các Phase chưa được plan tính đến

### 4.4 External API issues
- Khi một external API (FRED, MarineTraffic, ACLED...) không hoạt động như mô tả
- Khi cần API key mà chưa có
- Khi rate limit của free tier quá thấp để test

### 4.5 Ambiguity trong PLAN.md
- Khi một task có thể hiểu theo nhiều cách khác nhau
- Khi Deliverable của Phase không rõ tiêu chí "hoàn thành"
- Khi không chắc task này thuộc Phase nào

**Cách hỏi đúng:** Mô tả rõ vấn đề, đưa ra 2–3 phương án, hỏi người dùng chọn phương án nào. Không hỏi chung chung "tôi nên làm gì?".

---

## 5. CÁC LỖI PHỔ BIẾN CẦN TRÁNH

### ❌ Làm sai thứ tự Phase

```
SAI: Bắt đầu Phase 1 (AI Agents) khi Phase 0 chưa xong
     → python_runner.py chưa có → agent run sẽ fail

ĐÚNG: Hoàn thành tất cả Deliverables của Phase 0 trước
```

### ❌ Tự ý thêm dependency mới

```
SAI: Thêm SQLAlchemy vào Phase 0 vì "có thể cần sau"
     → Không có trong PLAN.md → tăng complexity không cần thiết

ĐÚNG: Chỉ dùng những gì PLAN.md đã liệt kê trong Tech Stack
```

### ❌ Implement endpoint không đúng URL pattern

```
SAI:  POST /agents/run          (thiếu /api/v1/)
SAI:  POST /api/v1/agent/run    (thiếu 's')
ĐÚNG: POST /api/v1/agents/run
```

### ❌ Trả raw script output cho client

```python
# SAI
return subprocess_result  # {"success": true, "data": {"type": "dict", "value": {...}}, "metadata": {...}}

# ĐÚNG — unwrap data.value
raw = subprocess_result
if raw.get("success"):
    return raw["data"]["value"]
else:
    raise HTTPException(...)
```

### ❌ Blocking call trong async endpoint

```python
# SAI — blocking subprocess trong async handler
@router.get("/quote/{symbol}")
async def get_quote(symbol: str):
    result = subprocess.run(...)  # BLOCKS event loop!

# ĐÚNG — async subprocess
@router.get("/quote/{symbol}")
async def get_quote(symbol: str):
    result = await python_runner.run(...)  # non-blocking
```

### ❌ Đánh [x] task chưa xong

```
SAI: Đánh [x] P1-T4 (SSE streaming) khi chỉ mới tạo file, chưa test
ĐÚNG: Chỉ đánh [x] khi endpoint đã chạy được và test pass
```

---

## 6. CHECKLIST TRƯỚC KHI BẮT ĐẦU MỖI PHIÊN

Trả lời 5 câu hỏi này trước khi viết bất kỳ dòng code nào:

- [ ] Tôi đang làm task **nào** trong PLAN.md? (Task ID: ___)
- [ ] Task này thuộc **Phase nào**? Phase đó đã đủ điều kiện bắt đầu chưa?
- [ ] Các task **trước đó** trong cùng Phase đã xong chưa? (đọc WORKLOGS.md)
- [ ] Tôi có **hiểu rõ** tất cả sub-tasks và Deliverables của task này không?
- [ ] Có điều gì **chưa rõ** cần hỏi lại trước khi làm không?

Nếu câu trả lời cho câu 4 hoặc 5 là "Không/Có" → **dừng lại và hỏi người dùng trước**.

---

## 7. THÔNG TIN NHANH VỀ DỰ ÁN

### Mục tiêu
Xây dựng REST/WebSocket API gateway để expose 5 module của Fincept Terminal ra ngoài cho các dự án khác kết nối.

### Source code gốc
- Scripts Python: `fincept-qt/scripts/` (~250+ scripts, mỗi script nhận JSON → trả JSON)
- Agent core: `fincept-qt/scripts/agents/finagent_core/main.py`
- Output standard: `fincept-qt/scripts/fincept_output_standard.py`

### Tech stack (KHÔNG thay đổi trừ khi được phép)
```
FastAPI 0.115+  |  Pydantic v2  |  Python 3.11.9
Redis 7+        |  Celery 5+ (Phase 5 only)
Uvicorn + Gunicorn  |  pytest + httpx
```

### Thứ tự ưu tiên
```
Phase 0 → (Phase 1 + Phase 2 + Phase 3 + Phase 4 song song) → Phase 5 → Phase 6
```
Phase 1 (AI Agents) là ưu tiên cao nhất sau Phase 0 vì có business value cao nhất.

### Thư mục output
Tất cả code mới tạo trong: `fincept-api/` (cùng cấp với `fincept-qt/`)

---

## 8. QUY TRÌNH TEST & REVIEW TRƯỚC KHI CHUYỂN PHASE

> **Quy tắc cứng:** Không được bắt đầu Phase tiếp theo khi Phase hiện tại chưa qua đủ 3 cổng kiểm tra: Test Gate → Code Review Gate → Sign-off Gate.

### 8.1 Tổng quan 3 cổng kiểm tra

```
[Phase N hoàn thành tasks]
         │
         ▼
  ┌─────────────┐     FAIL → sửa → chạy lại
  │  TEST GATE  │ ──────────────────────────►
  └──────┬──────┘
         │ PASS
         ▼
  ┌──────────────────┐     FAIL → sửa → chạy lại
  │ CODE REVIEW GATE │ ──────────────────────────►
  └────────┬─────────┘
           │ PASS
           ▼
  ┌──────────────────┐     FAIL → hỏi người dùng
  │  SIGN-OFF GATE   │ ──────────────────────────►
  └────────┬─────────┘
           │ APPROVED
           ▼
  [Bắt đầu Phase N+1]
```

---

### 8.2 TEST GATE — Tiêu chí bắt buộc theo từng Phase

#### Phase 0 — Foundation

Chạy toàn bộ, tất cả phải PASS:

```bash
# 1. Health check
curl http://localhost:8000/health
# Expected: {"status": "ok", "version": "1.0.0"}

# 2. Auth middleware
curl http://localhost:8000/api/v1/agents -H "X-API-Key: invalid"
# Expected: 401 {"error": {"code": "AUTH_REQUIRED", ...}}

# 3. Python subprocess bridge
pytest tests/core/test_python_runner.py -v
# Expected: tất cả tests PASS, không có timeout

# 4. Redis cache
pytest tests/core/test_cache.py -v
# Expected: set/get/ttl/invalidate đều PASS

# 5. Docker
docker compose up -d && sleep 5 && curl http://localhost:8000/health
# Expected: {"status": "ok"}
```

**Tiêu chí PASS Phase 0:**
- [ ] `GET /health` trả 200 trong < 50ms
- [ ] Auth reject request không có API key (401)
- [ ] Auth accept request có API key hợp lệ (200)
- [ ] `python_runner.run()` chạy được script test, trả JSON đúng format
- [ ] Redis set/get/expire hoạt động
- [ ] `docker compose up` không có error, health check pass
- [ ] `pytest tests/` — 0 failures, 0 errors

---

#### Phase 1 — AI Agents

```bash
pytest tests/test_agents.py -v --tb=short

# Integration tests (cần OpenAI key)
pytest tests/integration/test_agents_integration.py -v -m "not slow"
```

**Tiêu chí PASS Phase 1:**
- [ ] `GET /api/v1/agents` trả danh sách agents (ít nhất 5 agents)
- [ ] `POST /api/v1/agents/run` với Warren Buffett agent trả response hợp lệ
- [ ] `POST /api/v1/agents/run/stream` stream SSE events đúng format (`data: {...}\n\n`)
- [ ] SSE stream kết thúc bằng event `{"type": "done"}`
- [ ] Client disconnect → subprocess bị kill trong < 2s
- [ ] `POST /api/v1/agents/paper/trade` tạo trade thành công
- [ ] Session create → add message → get session hoạt động
- [ ] Rate limit: request thứ 61 trong 1 phút bị reject (429)
- [ ] API key không được xuất hiện trong bất kỳ log line nào
- [ ] `pytest tests/test_agents.py` — 0 failures

---

#### Phase 2 — Multi-Asset Analytics

```bash
pytest tests/test_analytics.py -v --tb=short
```

**Tiêu chí PASS Phase 2:**
- [ ] `GET /api/v1/market/quote/AAPL` trả price, change, volume hợp lệ
- [ ] Quote endpoint: cache hit < 200ms, cache miss < 3s
- [ ] `POST /api/v1/market/quotes/batch` với 5 symbols trả đủ 5 quotes
- [ ] `GET /api/v1/market/history/AAPL?interval=1d` trả OHLCV bars đúng format
- [ ] `GET /api/v1/equity/AAPL/info` trả sector, market_cap, P/E hợp lệ
- [ ] `POST /api/v1/equity/AAPL/dcf` trả intrinsic_value là số dương
- [ ] `POST /api/v1/portfolio/optimize` trả weights tổng = 1.0 (±0.001)
- [ ] `POST /api/v1/derivatives/greeks` với BSM trả delta ∈ (0, 1) cho call
- [ ] Response format: tất cả endpoints trả đúng schema, không có raw script output
- [ ] `pytest tests/test_analytics.py` — 0 failures

---

#### Phase 3 — QuantLib Suite

```bash
pytest tests/test_quantlib.py -v --tb=short
```

**Tiêu chí PASS Phase 3:**
- [ ] `POST /api/v1/quant/option/price` (BSM call): latency < 10ms (direct import)
- [ ] BSM price accuracy: so với reference value, sai số < 0.0001
- [ ] Greeks accuracy: Delta, Gamma, Theta, Vega, Rho sai số < 0.0001
- [ ] `POST /api/v1/quant/option/batch-greeks` 100 contracts: tổng thời gian < 500ms
- [ ] `POST /api/v1/quant/bond/price` trả clean_price, dirty_price hợp lệ
- [ ] `POST /api/v1/quant/bond/ytm` — YTM tính ngược lại cho ra price ban đầu (±0.01)
- [ ] `POST /api/v1/quant/risk/var` (historical method) trả var là số âm
- [ ] `POST /api/v1/quant/stochastic/gbm` trả đúng shape `n_paths × n_steps`
- [ ] `pytest tests/test_quantlib.py` — 0 failures, numerical tests tolerance 1e-4

---

#### Phase 4 — Global Intelligence

```bash
pytest tests/test_intelligence.py -v --tb=short
```

**Tiêu chí PASS Phase 4:**
- [ ] `GET /api/v1/intelligence/economics/fred/GDP` trả observations array không rỗng
- [ ] `GET /api/v1/intelligence/economics/calendar` trả ít nhất 1 upcoming event
- [ ] `GET /api/v1/intelligence/geopolitics/events` trả events array (có thể rỗng nếu không có ACLED key — nhưng không được 500)
- [ ] `GET /api/v1/intelligence/geopolitics/countries` trả danh sách countries
- [ ] Maritime endpoint: trả 404 với message rõ ràng khi IMO không tồn tại (không được 500)
- [ ] Missing API key: trả `{"error": {"code": "MISSING_API_KEY"}}` (không được crash)
- [ ] Cache: gọi FRED 2 lần liên tiếp — lần 2 phải là cache hit (kiểm tra qua Redis)
- [ ] `pytest tests/test_intelligence.py` — 0 failures

---

#### Phase 5 — AI Quant Lab

```bash
pytest tests/test_quant_lab.py -v --tb=short
```

**Tiêu chí PASS Phase 5:**
- [ ] `POST /api/v1/quant-lab/backtest` trả `{job_id, status: "queued"}` ngay lập tức (< 500ms)
- [ ] `GET /api/v1/quant-lab/jobs/{job_id}` trả status đúng (queued/running/completed)
- [ ] Job hoàn thành: `GET /api/v1/quant-lab/jobs/{job_id}/result` trả equity_curve và metrics
- [ ] WebSocket stream: nhận ít nhất 1 progress event trong quá trình job chạy
- [ ] `DELETE /api/v1/quant-lab/jobs/{job_id}` cancel job đang chạy thành công
- [ ] Job timeout: job quá 30 phút tự động fail với error rõ ràng
- [ ] `POST /api/v1/quant-lab/models/train` (LightGBM, dataset nhỏ) hoàn thành < 5 phút
- [ ] `pytest tests/test_quant_lab.py` — 0 failures (dùng mock Qlib cho unit tests)

---

### 8.3 CODE REVIEW GATE — Checklist tự review

Sau khi Test Gate PASS, agent tự review code theo checklist này. Mỗi mục phải được kiểm tra và xác nhận:

#### Correctness
- [ ] Tất cả endpoints trong PLAN.md đã được implement (không bỏ sót)
- [ ] URL patterns đúng `/api/v1/{module}/{resource}`
- [ ] HTTP methods đúng (GET cho read, POST cho compute/create, DELETE cho cancel)
- [ ] Response schemas khớp với PLAN.md (không thêm/bớt fields tùy tiện)
- [ ] Error codes dùng đúng enum đã định (`AUTH_REQUIRED`, `SCRIPT_TIMEOUT`, v.v.)

#### Security
- [ ] Không có API key nào xuất hiện trong logs (grep `api_key` trong log output)
- [ ] Input validation: tất cả string inputs được validate bằng Pydantic
- [ ] Rate limiting hoạt động đúng tier (60/600 req/min)
- [ ] Subprocess env: chỉ inject keys đã whitelist, không leak env vars khác

#### Performance
- [ ] Không có blocking call (`subprocess.run`, `time.sleep`, sync I/O) trong async handlers
- [ ] Cache được áp dụng cho tất cả endpoints có TTL trong PLAN.md
- [ ] Concurrent subprocess cap được enforce (max 5 cho runner thường, max 10 cho agents)

#### Code quality
- [ ] Không có dead code, commented-out code, hay debug prints
- [ ] Không có hardcoded paths — dùng `ScriptCatalog` hoặc config
- [ ] Không có hardcoded secrets — dùng env vars
- [ ] Type hints đầy đủ cho tất cả function signatures
- [ ] Docstrings cho tất cả public functions và router handlers

#### Tests
- [ ] Mỗi endpoint có ít nhất 1 unit test (happy path)
- [ ] Mỗi endpoint có ít nhất 1 error test (invalid input hoặc upstream failure)
- [ ] Test coverage ≥ 70% cho module vừa implement
- [ ] Không có `# TODO` hay `# FIXME` còn sót trong code production

---

### 8.4 SIGN-OFF GATE — Báo cáo cho người dùng

Sau khi cả Test Gate và Code Review Gate đều PASS, agent **PHẢI báo cáo** cho người dùng trước khi chuyển Phase. Báo cáo theo format sau:

```
## ✅ Phase N — [Tên Phase] — SẴN SÀNG CHUYỂN PHASE

### Kết quả Test Gate
- Tổng số tests: X passed, 0 failed, 0 errors
- Endpoints đã verify: X/Y
- Performance: [metric quan trọng nhất, ví dụ: quote latency 45ms cache hit]

### Kết quả Code Review
- Security: ✅ Không có API key leak
- Performance: ✅ Không có blocking calls
- Coverage: X% (target: ≥70%)
- Issues tìm thấy và đã sửa: [liệt kê nếu có]

### Deliverables đã hoàn thành
- [x] [Deliverable 1]
- [x] [Deliverable 2]
- ...

### Vấn đề còn mở (nếu có)
- [Mô tả vấn đề, mức độ ảnh hưởng, đề xuất xử lý]

### Đề xuất
Sẵn sàng chuyển sang Phase [N+1] — [Tên Phase tiếp theo].
Bạn có muốn tôi bắt đầu không?
```

**Chỉ bắt đầu Phase tiếp theo khi người dùng xác nhận.**

---

### 8.5 Xử lý khi Test Gate FAIL

Nếu có test fail, agent phải:

1. **Phân tích root cause** — đọc error message, stack trace, xác định nguyên nhân
2. **Phân loại lỗi:**
   - **Bug trong code** → sửa và chạy lại test, không cần hỏi người dùng
   - **Thiếu dependency/config** → kiểm tra PLAN.md, nếu có trong plan thì tự fix, nếu không có thì hỏi
   - **External service unavailable** (API key thiếu, service down) → báo cáo người dùng, đề xuất mock/skip
   - **Test sai** (test expect sai) → giải thích lý do và hỏi người dùng trước khi sửa test
3. **Không được** chuyển Phase khi còn test fail, dù chỉ 1 test

---

### 8.6 Ghi nhận kết quả vào WORKLOGS.md

Sau khi Phase pass Sign-off Gate, thêm entry đặc biệt vào WORKLOGS.md:

```
### [YYYY-MM-DD HH:MM] — ✅ PHASE N COMPLETE — Test & Review Passed

**Phase:** Phase N — [Tên Phase]
**Trạng thái:** ✅ Hoàn thành — Đã qua Test Gate + Code Review Gate + Sign-off

**Test Gate kết quả:**
- Tests: X passed / 0 failed
- Endpoints verified: X/Y
- Performance highlights: [...]

**Code Review kết quả:**
- Security issues: 0
- Performance issues: 0 (đã sửa X issues)
- Coverage: X%

**Quyết định kỹ thuật trong Phase này:**
- [Liệt kê các quyết định quan trọng]

**Sẵn sàng cho Phase tiếp theo:** Phase [N+1] — [Tên]

---
```

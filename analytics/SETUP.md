# Hướng dẫn Setup & Test thực tế — Analytics Microservice

## Tổng quan

```
analytics/            ← FastAPI server (port 8000)
    .env              ← Config của API server
    .venv/            ← Venv nhỏ: fastapi, redis, structlog...

fincept-qt/scripts/   ← 300+ Python scripts (data, agents, analytics)
    venv-numpy2/      ← Venv lớn: numpy, pandas, agno, qlib, torch...
    agents/finagent_core/.env  ← Config cho agents khi test standalone
```

**Luồng hoạt động:**
```
Client → analytics (.venv) → subprocess → script (venv-numpy2)
                                    ↑
                         inject env vars từ analytics/.env
```

---

## Bước 1: Tạo venv-numpy2 (chỉ làm 1 lần, ~15-30 phút)

```powershell
# Từ thư mục gốc FinceptTerminal
cd G:\Code\AI-APP\FinceptTerminal\fincept-qt

# Tạo venv
python -m venv venv-numpy2

# Upgrade pip trước
venv-numpy2\Scripts\python.exe -m pip install --upgrade pip

# Option A: Cài FULL (tất cả features, ~30 phút, ~5GB)
venv-numpy2\Scripts\pip install -r resources\requirements-numpy2.txt --pre

# Option B: Cài MINIMAL (đủ để test Phase 1-4, ~10 phút, ~1GB)
# Bỏ qua: torch, qlib, voice, VisionQuant
venv-numpy2\Scripts\pip install -r resources\requirements-api-minimal.txt
```

> **Lưu ý về `--pre` flag:** Một số packages như `mplfinance` chỉ có pre-release versions.
> Dùng `--pre` để pip chấp nhận cài chúng.
>
> **Nếu gặp lỗi `mplfinance>=0.12.0`:** Đã được fix trong requirements-numpy2.txt
> (pin thành `mplfinance==0.12.10b0`)

> **Lỗi PyAudio trên Windows:** Cần Microsoft C++ Build Tools
> ```powershell
> # Cài Build Tools: https://visualstudio.microsoft.com/visual-cpp-build-tools/
> # Hoặc skip PyAudio (chỉ cần cho voice features):
> venv-numpy2\Scripts\pip install -r resources\requirements-numpy2.txt --pre --ignore-installed PyAudio
> ```

---

## Bước 2: Cấu hình analytics/.env

File `.env` đã được tạo tại `analytics/.env`. Mở và điền:

### Bắt buộc (API không chạy được nếu thiếu):

```env
# Đường dẫn đến scripts (thường auto-detect đúng)
SCRIPTS_DIR=G:\Code\AI-APP\FinceptTerminal\fincept-qt\scripts

# Python của venv-numpy2 (sau khi tạo ở Bước 1)
VENV_NUMPY2_PYTHON=G:\Code\AI-APP\FinceptTerminal\fincept-qt\venv-numpy2\Scripts\python.exe
```

### LLM (cần ít nhất 1 để test agents):

**Option A — Groq (FREE, không cần credit card):**
1. Đăng ký tại https://console.groq.com
2. Tạo API key
3. Điền vào `.env`:
```env
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=llama-3.1-70b-versatile
LLM_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx
```

**Option B — OpenAI:**
```env
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxx
```

**Option C — Ollama local (FREE, không cần internet):**
```powershell
# Cài Ollama: https://ollama.ai/download
ollama pull llama3.2
```
```env
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=llama3.2
LLM_API_KEY=ollama
```

**Option D — DeepSeek (rẻ, ~$0.001/1K tokens):**
```env
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
LLM_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx
```

### Data APIs (optional, để trống = endpoint đó skip):

```env
# FRED Economics — FREE, đăng ký tại fred.stlouisfed.org
FRED_API_KEY=your_fred_key

# Finnhub Market Data — FREE 60 req/min, đăng ký tại finnhub.io
FINNHUB_API_KEY=your_finnhub_key
```

---

## Bước 3: Chạy Redis

```powershell
# Option A: Docker (khuyến nghị)
docker run -d --name analytics-redis -p 6379:6379 redis:7.4-alpine

# Option B: Redis trực tiếp (nếu đã cài)
redis-server

# Kiểm tra Redis đang chạy
docker ps | findstr redis
```

---

## Bước 4: Chạy Analytics API

```powershell
cd G:\Code\AI-APP\FinceptTerminal\analytics

# Kích hoạt venv
.venv\Scripts\activate

# Chạy server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Kết quả mong đợi:
```
INFO     analytics.startup version=1.0.0 env=development
INFO     redis.connected url=redis://localhost:6379/0
INFO     script_catalog.validation_ok total=40
INFO     Application startup complete.
```

> Nếu thấy `script_catalog.validation_failed` — kiểm tra lại `SCRIPTS_DIR`
> Nếu thấy `cache.connect_failed` — kiểm tra Redis đang chạy

---

## Bước 5: Test cơ bản

### 5.1 Health check
```powershell
curl http://localhost:8000/health
# Kết quả: {"status":"ok","version":"1.0.0","env":"development","redis":"ok"}
```

### 5.2 Swagger UI
Mở trình duyệt: http://localhost:8000/docs

### 5.3 Test market data (không cần LLM)
```powershell
# Quote AAPL (dùng yfinance, không cần API key)
curl http://localhost:8000/api/v1/market/quote/AAPL

# Lịch sử giá
curl "http://localhost:8000/api/v1/market/history/AAPL?start=2024-01-01&interval=1d"

# Thông tin công ty
curl http://localhost:8000/api/v1/equity/AAPL/info
```

### 5.4 Test QuantLib (không cần LLM)
```powershell
# BSM option pricing
curl -X POST http://localhost:8000/api/v1/quant/option/price `
  -H "Content-Type: application/json" `
  -d '{"S":150,"K":155,"T":0.25,"r":0.05,"sigma":0.2,"option_type":"call","model":"bsm"}'
```

### 5.5 Test AI Agent (cần LLM key)
```powershell
# Discover agents (không cần LLM)
curl -H "X-API-Key: analytics_admin_dev_key_local" `
     http://localhost:8000/api/v1/agents/

# Run agent (cần LLM key trong .env)
curl -X POST http://localhost:8000/api/v1/agents/run `
  -H "X-API-Key: analytics_admin_dev_key_local" `
  -H "Content-Type: application/json" `
  -d '{
    "query": "What is 2+2?",
    "llm_config": {
      "model": "llama-3.1-70b-versatile",
      "api_key": "gsk_YOUR_GROQ_KEY",
      "base_url": "https://api.groq.com/openai/v1"
    }
  }'
```

### 5.6 Test FRED Economics (cần FRED_API_KEY)
```powershell
curl http://localhost:8000/api/v1/intelligence/economics/fred/CPIAUCSL
```

---

## Bước 6: Test với Postman

1. Mở Postman
2. Import từ URL: `http://localhost:8000/openapi.json`
   - Postman → Import → Link → `http://localhost:8000/openapi.json`
3. Tạo Environment trong Postman:
   ```
   base_url = http://localhost:8000
   api_key  = analytics_admin_dev_key_local
   llm_key  = gsk_YOUR_GROQ_KEY  (hoặc key của provider bạn dùng)
   ```
4. Thêm header vào Collection:
   - `X-API-Key: {{api_key}}`

---

## Troubleshooting

### Lỗi: `ModuleNotFoundError: No module named 'yfinance'`
→ `VENV_NUMPY2_PYTHON` chưa đúng hoặc venv-numpy2 chưa cài requirements
```powershell
# Kiểm tra
G:\Code\AI-APP\FinceptTerminal\fincept-qt\venv-numpy2\Scripts\python.exe -c "import yfinance; print('OK')"
```

### Lỗi: `cache.connect_failed`
→ Redis chưa chạy
```powershell
docker start analytics-redis
# hoặc
docker run -d --name analytics-redis -p 6379:6379 redis:7.4-alpine
```

### Lỗi: `script_catalog.scripts_dir_missing`
→ `SCRIPTS_DIR` sai
```powershell
# Kiểm tra path tồn tại
Test-Path "G:\Code\AI-APP\FinceptTerminal\fincept-qt\scripts"
# Phải trả về True
```

### Lỗi: `Invalid LLM config: OpenAI API key must start with 'sk-'`
→ API key sai format. Kiểm tra lại key từ provider.

### Lỗi: `Script timed out after 120s`
→ Script mất quá lâu. Tăng timeout trong `.env`:
```env
AGENT_RUN_TIMEOUT=300
```

### Agent trả về `Unknown action: delete_session`
→ Cần update `finagent_core/main.py` (đã fix trong commit mới nhất)

---

## Test Integration thực tế

```powershell
cd G:\Code\AI-APP\FinceptTerminal\analytics

# Chạy integration tests (cần venv-numpy2 + Redis)
.venv\Scripts\python.exe -m pytest tests/integration/ -v -s

# Chỉ test market data (không cần LLM)
.venv\Scripts\python.exe -m pytest tests/integration/test_scripts_real.py::test_yfinance_quote_real -v -s

# Test với LLM (cần set OPENAI_API_KEY hoặc LLM_API_KEY)
$env:LLM_API_KEY="gsk_YOUR_GROQ_KEY"
.venv\Scripts\python.exe -m pytest tests/integration/test_scripts_real.py::test_agent_run_real -v -s
```

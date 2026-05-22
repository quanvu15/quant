# Integration Tests — Analytics Microservice

Tests này chạy với **scripts thực** (không mock). Cần chuẩn bị môi trường trước.

## Chuẩn bị

### 1. Tạo venv-numpy2 (nếu chưa có)

```bash
# Từ thư mục gốc FinceptTerminal
python -m venv fincept-qt/venv-numpy2

# Windows
fincept-qt\venv-numpy2\Scripts\pip install -r fincept-qt\resources\requirements-numpy2.txt

# Linux/macOS
fincept-qt/venv-numpy2/bin/pip install -r fincept-qt/resources/requirements-numpy2.txt
```

### 2. Tạo .env

```bash
cp analytics/.env.example analytics/.env
```

Điền vào `.env`:
```env
SCRIPTS_DIR=G:\Code\AI-APP\FinceptTerminal\fincept-qt\scripts
VENV_NUMPY2_PYTHON=G:\Code\AI-APP\FinceptTerminal\fincept-qt\venv-numpy2\Scripts\python.exe
REDIS_URL=redis://localhost:6379/0
MASTER_API_KEY=analytics_admin_test_key_dev
```

### 3. Chạy Redis

```bash
docker run -d -p 6379:6379 redis:7.4-alpine
```

### 4. Chạy integration tests

```bash
cd analytics
.venv\Scripts\python.exe -m pytest tests/integration/ -v -s
```

## Checklist chuẩn bị

- [ ] `venv-numpy2` đã tạo và cài requirements-numpy2.txt
- [ ] `.env` đã điền `SCRIPTS_DIR` và `VENV_NUMPY2_PYTHON`
- [ ] Redis đang chạy trên port 6379
- [ ] (Optional) API keys cho external services: OPENAI_API_KEY, POLYGON_API_KEY, FRED_API_KEY

## Test matrix

| Test | Script | Cần API key | Thời gian |
|------|---------|-------------|-----------|
| test_yfinance_quote | yfinance_data.py | Không | ~2s |
| test_yfinance_history | yfinance_data.py | Không | ~3s |
| test_derivatives_bsm | derivatives_pricing.py | Không | ~1s |
| test_fred_series | fred_data.py | FRED_API_KEY | ~3s |
| test_agent_discover | finagent_core/main.py | Không | ~5s |
| test_agent_run | finagent_core/main.py | LLM API key | ~30s |

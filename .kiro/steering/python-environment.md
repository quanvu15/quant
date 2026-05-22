# Python Environment — FinceptTerminal Workspace

## Môi trường Python chính

**Venv duy nhất trong workspace:**

```
g:\Code\AI-APP\FinceptTerminal\fincept-qt\venv-numpy2\
```

### Executables

| Lệnh | Đường dẫn đầy đủ |
|---|---|
| `python` | `g:\Code\AI-APP\FinceptTerminal\fincept-qt\venv-numpy2\Scripts\python.exe` |
| `pip` | `g:\Code\AI-APP\FinceptTerminal\fincept-qt\venv-numpy2\Scripts\pip.exe` |
| `pytest` | `g:\Code\AI-APP\FinceptTerminal\fincept-qt\venv-numpy2\Scripts\pytest.exe` |

### Python version

Python 3.12.10

---

## Quy tắc bắt buộc

> **LUÔN dùng đường dẫn đầy đủ đến venv khi chạy Python, pip, pytest.**
> Không dùng `python`, `pip`, `pytest` trực tiếp — sẽ dùng system Python và thiếu packages.

### Chạy Python script

```powershell
& "g:\Code\AI-APP\FinceptTerminal\fincept-qt\venv-numpy2\Scripts\python.exe" <script.py>
```

### Chạy pytest (analytics)

```powershell
& "g:\Code\AI-APP\FinceptTerminal\fincept-qt\venv-numpy2\Scripts\python.exe" -m pytest `
    "g:\Code\AI-APP\FinceptTerminal\analytics\tests\" -v
```

Hoặc chạy file cụ thể:

```powershell
& "g:\Code\AI-APP\FinceptTerminal\fincept-qt\venv-numpy2\Scripts\python.exe" -m pytest `
    "g:\Code\AI-APP\FinceptTerminal\analytics\tests\test_news_canonicalize.py" -v
```

### Cài package mới

```powershell
& "g:\Code\AI-APP\FinceptTerminal\fincept-qt\venv-numpy2\Scripts\pip.exe" install <package>
```

---

## Packages đã cài (core)

| Package | Version |
|---|---|
| Python | 3.12.10 |
| fastapi | 0.136.1 |
| asyncpg | 0.31.0 |
| SQLAlchemy | 2.1.0b2 |
| redis | 8.0.0b2 |
| pydantic | 2.13.4 |
| pydantic-settings | 2.14.1 |
| structlog | 25.5.0 |
| python-jose | 3.5.0 |
| feedparser | (installed) |
| httpx | (installed) |
| pytest | (installed) |
| pytest-asyncio | 1.3.0 |
| pytest-cov | 7.1.0 |

---

## Working directory cho analytics

Khi chạy pytest cho `analytics/`, cwd phải là thư mục `analytics/` để import paths hoạt động:

```powershell
# cwd = g:\Code\AI-APP\FinceptTerminal\analytics
& "g:\Code\AI-APP\FinceptTerminal\fincept-qt\venv-numpy2\Scripts\python.exe" -m pytest tests/ -v
```

Hoặc dùng `--rootdir`:

```powershell
& "g:\Code\AI-APP\FinceptTerminal\fincept-qt\venv-numpy2\Scripts\python.exe" -m pytest `
    --rootdir="g:\Code\AI-APP\FinceptTerminal\analytics" `
    "g:\Code\AI-APP\FinceptTerminal\analytics\tests\" -v
```

---

## Lưu ý

- `venv-numpy2` là venv dùng cho cả `fincept-qt/scripts/` (numpy, pandas, yfinance, etc.) và `analytics/` (FastAPI backend).
- Nếu cần cài thêm package cho analytics, dùng pip của venv này.
- Không tạo venv mới trừ khi có lý do đặc biệt.

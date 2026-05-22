# Load Tests — Analytics Microservice

k6-based load tests for the Analytics microservice. These tests validate the performance requirements defined in **Requirement 6.3**.

## Requirements validated

| Test | Scenario | Threshold |
|---|---|---|
| `k6_news_list.js` | 100 concurrent `GET /api/v1/news` | p99 < 500ms, error rate < 1% |
| `k6_news_ws.js` | 200 concurrent WebSocket subscribers `/ws/news` | connection success rate > 99% |
| `k6_chat_streaming.js` | 50 concurrent SSE `POST /api/v1/chat/completions` | TTFB p95 < 1500ms, 0 connection drops |

---

## Install k6

### macOS

```bash
brew install k6
```

### Linux (Debian/Ubuntu)

```bash
sudo gpg -k
sudo gpg --no-default-keyring \
  --keyring /usr/share/keyrings/k6-archive-keyring.gpg \
  --keyserver hkp://keyserver.ubuntu.com:80 \
  --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" \
  | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update
sudo apt-get install k6
```

### Windows (Chocolatey)

```powershell
choco install k6
```

### Windows (winget)

```powershell
winget install k6 --source winget
```

### Docker (no install needed)

```bash
docker run --rm -i grafana/k6 run - < tests/load/k6_news_list.js
```

Verify installation:

```bash
k6 version
```

---

## Environment variables

All tests accept these environment variables via `-e KEY=VALUE`:

| Variable | Default | Description |
|---|---|---|
| `BASE_URL` | `http://localhost:8000` | Analytics service base URL |
| `AUTH_TOKEN` | _(empty)_ | JWT Bearer token (required if auth is enforced) |
| `LLM_BASE_URL` | _(empty)_ | LLM provider base URL (chat streaming test only) |
| `LLM_API_KEY` | _(empty)_ | LLM provider API key (chat streaming test only) |
| `LLM_MODEL` | `gpt-4o-mini` | LLM model name (chat streaming test only) |

---

## Running the tests

Make sure the Analytics service is running before executing any test:

```bash
# Start the service (from analytics/ directory)
docker compose up -d
# or
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### k6_news_list.js — 100 concurrent GET /news

```bash
# Basic run (no auth)
k6 run tests/load/k6_news_list.js

# With auth token and custom base URL
k6 run tests/load/k6_news_list.js \
  -e BASE_URL=http://localhost:8000 \
  -e AUTH_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Output results to JSON for later analysis
k6 run tests/load/k6_news_list.js --out json=results/news_list.json
```

Expected output when thresholds pass:

```
✓ status 200
✓ has items array
✓ latency < 500ms

http_req_duration............: p(99)=312ms  ← must be < 500ms
http_req_failed..............: 0.00%        ← must be < 1%
```

### k6_news_ws.js — 200 concurrent WebSocket subscribers

```bash
# Basic run
k6 run tests/load/k6_news_ws.js

# With auth
k6 run tests/load/k6_news_ws.js \
  -e BASE_URL=http://localhost:8000 \
  -e AUTH_TOKEN=your_jwt_token
```

Each virtual user connects to `/ws/news`, waits for 3 messages, then disconnects. The test validates that at least 99% of connections succeed.

Expected output when thresholds pass:

```
✓ WS connection established
✓ received messages

ws_connect_success...........: 99.8%   ← must be > 99%
ws_messages_received.........: 598 total
```

### k6_chat_streaming.js — 50 concurrent SSE streams

```bash
# Without LLM (validates graceful error handling — no connection drops)
k6 run tests/load/k6_chat_streaming.js

# With a real LLM backend (validates actual streaming performance)
k6 run tests/load/k6_chat_streaming.js \
  -e LLM_BASE_URL=https://api.openai.com/v1 \
  -e LLM_API_KEY=sk-your-key \
  -e LLM_MODEL=gpt-4o-mini \
  -e AUTH_TOKEN=your_jwt_token

# With a local Ollama instance
k6 run tests/load/k6_chat_streaming.js \
  -e LLM_BASE_URL=http://localhost:11434/v1 \
  -e LLM_API_KEY=ollama \
  -e LLM_MODEL=llama3.2
```

Expected output when thresholds pass:

```
✓ no connection drop
✓ TTFB < 1500ms
✓ valid response status

chat_stream_ttfb_ms..........: p(95)=820ms  ← must be < 1500ms
chat_stream_connection_drops.: 0            ← must be 0
```

---

## Interpreting results

### Key metrics to watch

| Metric | What it means |
|---|---|
| `http_req_duration p(99)` | 99th percentile response time — most users experience this or better |
| `http_req_failed rate` | Fraction of requests that returned a non-2xx status or network error |
| `ws_connect_success rate` | Fraction of WebSocket connections that established successfully |
| `chat_stream_ttfb_ms p(95)` | Time until the first SSE byte arrives for 95% of requests |
| `chat_stream_connection_drops count` | Number of requests that dropped mid-stream (must be 0) |

### Reading the threshold summary

At the end of each run, k6 prints a threshold summary:

```
✓ http_req_duration............: p(99)<500    ← PASS (green ✓)
✗ http_req_failed..............: rate<0.01    ← FAIL (red ✗)
```

A `✗` means the threshold was breached. Investigate the `http_req_failed` metric details to find which requests failed and why.

### Common failure causes

| Symptom | Likely cause |
|---|---|
| High p99 latency on `/news` | DB query missing index, or Redis cache cold |
| WS connection success < 99% | Server running out of file descriptors (`ulimit -n`) |
| Chat TTFB > 1500ms | LLM provider slow to respond, or service under-provisioned |
| Connection drops on chat | Proxy timeout too short (Caddy/Nginx default 60s) |

---

## CI weekly setup (GitHub Actions)

Add this workflow to `.github/workflows/load-tests.yml` in the repository root:

```yaml
name: Load Tests (Weekly)

on:
  schedule:
    # Every Monday at 02:00 UTC
    - cron: "0 2 * * 1"
  workflow_dispatch:  # allow manual trigger

jobs:
  load-test:
    name: k6 Load Tests
    runs-on: ubuntu-latest

    services:
      analytics:
        image: ghcr.io/your-org/analytics-api:latest
        ports:
          - 8000:8000
        env:
          REDIS_URL: redis://redis:6379/0
          DATABASE_URL: postgresql://analytics_app:password@postgres:5432/quantdinger
          JWT_SECRET_KEY: ${{ secrets.ANALYTICS_JWT_SECRET }}
        options: >-
          --health-cmd "curl -f http://localhost:8000/health || exit 1"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 10

      redis:
        image: redis:7.4-alpine
        ports:
          - 6379:6379

      postgres:
        image: postgres:16-alpine
        ports:
          - 5432:5432
        env:
          POSTGRES_DB: quantdinger
          POSTGRES_USER: analytics_app
          POSTGRES_PASSWORD: password

    steps:
      - uses: actions/checkout@v4

      - name: Install k6
        run: |
          sudo gpg -k
          sudo gpg --no-default-keyring \
            --keyring /usr/share/keyrings/k6-archive-keyring.gpg \
            --keyserver hkp://keyserver.ubuntu.com:80 \
            --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
          echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" \
            | sudo tee /etc/apt/sources.list.d/k6.list
          sudo apt-get update
          sudo apt-get install k6

      - name: Wait for service to be ready
        run: |
          for i in $(seq 1 30); do
            curl -sf http://localhost:8000/health && break
            echo "Waiting for analytics service... ($i/30)"
            sleep 2
          done

      - name: Run news list load test
        run: |
          k6 run analytics/tests/load/k6_news_list.js \
            -e BASE_URL=http://localhost:8000 \
            --out json=results/news_list.json
        continue-on-error: false

      - name: Run news WebSocket load test
        run: |
          k6 run analytics/tests/load/k6_news_ws.js \
            -e BASE_URL=http://localhost:8000 \
            --out json=results/news_ws.json
        continue-on-error: false

      - name: Run chat streaming load test
        run: |
          k6 run analytics/tests/load/k6_chat_streaming.js \
            -e BASE_URL=http://localhost:8000 \
            --out json=results/chat_streaming.json
        # Without LLM config, validates graceful error handling (no connection drops)
        continue-on-error: false

      - name: Upload results
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: k6-load-test-results-${{ github.run_id }}
          path: results/
          retention-days: 30

      - name: Post summary to job
        if: always()
        run: |
          echo "## Load Test Results" >> $GITHUB_STEP_SUMMARY
          echo "" >> $GITHUB_STEP_SUMMARY
          echo "| Test | Status |" >> $GITHUB_STEP_SUMMARY
          echo "|---|---|" >> $GITHUB_STEP_SUMMARY
          echo "| News List (100 VUs, p99 < 500ms) | See artifacts |" >> $GITHUB_STEP_SUMMARY
          echo "| News WebSocket (200 VUs, success > 99%) | See artifacts |" >> $GITHUB_STEP_SUMMARY
          echo "| Chat Streaming (50 VUs, TTFB p95 < 1500ms) | See artifacts |" >> $GITHUB_STEP_SUMMARY
```

### Notes on the CI setup

- The workflow runs **every Monday at 02:00 UTC** via cron schedule.
- Use `workflow_dispatch` to trigger it manually from the GitHub Actions UI.
- Results are uploaded as artifacts and retained for 30 days.
- The chat streaming test runs without a real LLM in CI — it validates that the server handles missing LLM config gracefully (no connection drops). To test real streaming, add `LLM_BASE_URL` and `LLM_API_KEY` as GitHub secrets and pass them via `-e`.
- Adjust the `analytics` service image tag (`ghcr.io/your-org/analytics-api:latest`) to match your registry.

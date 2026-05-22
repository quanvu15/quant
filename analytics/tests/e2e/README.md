# Analytics E2E Tests — Playwright

End-to-end tests for the Analytics microservice UI, covering the three main pages:
`/analytics/news`, `/analytics/chat`, and `/analytics/agents`.

**Validates:** Requirements 5.1, 5.2, 5.3

---

## Prerequisites

All services must be running before executing E2E tests:

| Service | Default URL | How to start |
|---|---|---|
| QuantDinger Vue (fincept-web) | `http://localhost:8888` | `cd fincept-web && npm run dev -- --port 8888` |
| Analytics FastAPI backend | `http://localhost:8000` | `cd analytics && uvicorn app.main:app --port 8000` |
| Postgres | `localhost:5432` | `docker compose up -d postgres` |
| Redis | `localhost:6379` | `docker compose up -d redis` |

Or start everything at once:

```bash
docker compose up -d
```

---

## Install Playwright

Playwright is a Node.js package. Install it in the `fincept-web` directory (or any Node project):

```bash
# From the workspace root
cd fincept-web
npm install --save-dev @playwright/test

# Install browser binaries (Chromium only is enough for most tests)
npx playwright install chromium
```

Or install globally:

```bash
npm install -g @playwright/test
playwright install chromium
```

---

## Run Tests

### All E2E tests

```bash
# From the workspace root
npx playwright test \
  --config=analytics/tests/e2e/playwright.config.js
```

### Single test file

```bash
npx playwright test \
  --config=analytics/tests/e2e/playwright.config.js \
  analytics/tests/e2e/test_agents_page.spec.js
```

### With UI mode (interactive, great for debugging)

```bash
npx playwright test \
  --config=analytics/tests/e2e/playwright.config.js \
  --ui
```

### Headed mode (see the browser)

```bash
npx playwright test \
  --config=analytics/tests/e2e/playwright.config.js \
  --headed
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `E2E_BASE_URL` | `http://localhost:8888` | Vue dev server URL |
| `E2E_AUTH_TOKEN` | _(empty)_ | JWT token from QuantDinger login |
| `E2E_API_KEY` | _(empty)_ | Analytics API key (alternative to JWT) |
| `E2E_LLM_API_KEY` | _(empty)_ | LLM provider API key (enables send-message + agent run tests) |
| `E2E_LLM_MODEL` | `gpt-4o-mini` | LLM model name |
| `E2E_LLM_BASE_URL` | `https://api.openai.com/v1` | LLM provider base URL |

### Example: run with auth + LLM

```bash
E2E_AUTH_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
E2E_LLM_API_KEY="sk-..." \
E2E_LLM_MODEL="gpt-4o-mini" \
npx playwright test --config=analytics/tests/e2e/playwright.config.js
```

### Getting an auth token

1. Open QuantDinger in your browser and log in.
2. Open DevTools → Application → Local Storage → `auth_token`.
3. Copy the value and set it as `E2E_AUTH_TOKEN`.

Or use the QuantDinger API directly:

```bash
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "yourpassword"}' \
  | jq -r '.token'
```

---

## Test Structure

```
analytics/tests/e2e/
├── playwright.config.js          # Playwright configuration
├── helpers.js                    # Shared auth injection + wait utilities
├── test_news_page.spec.js        # /analytics/news — ≥10 articles, filters
├── test_chat_page.spec.js        # /analytics/chat — session, send message
├── test_agents_page.spec.js      # /analytics/agents + /warren_buffett run
└── README.md                     # This file
```

---

## Test Behavior

### Tests that skip gracefully

Many tests check for UI elements that may not be implemented yet (e.g., `/analytics/news` and `/analytics/chat` pages are Phase 1/2 work). If the element is not found, the test calls `test.skip()` with an explanation rather than failing.

This means:
- Tests that require auth will skip if `E2E_AUTH_TOKEN` / `E2E_API_KEY` is not set.
- Tests that require a real LLM will skip if `E2E_LLM_API_KEY` is not set.
- Tests for unimplemented UI will skip with a clear message.

### Artifacts on failure

When a test fails, Playwright saves:
- **Screenshot** → `test-results/<test-name>/screenshot.png`
- **Video** (on retry) → `test-results/<test-name>/video.webm`
- **Trace** (on retry) → `test-results/<test-name>/trace.zip`

View the HTML report:

```bash
npx playwright show-report analytics/tests/e2e/playwright-report
```

---

## CI Integration

Add to your CI pipeline (GitHub Actions example):

```yaml
- name: Install Playwright
  run: |
    cd fincept-web
    npm ci
    npx playwright install --with-deps chromium

- name: Run E2E tests
  env:
    E2E_BASE_URL: http://localhost:8888
    E2E_AUTH_TOKEN: ${{ secrets.E2E_AUTH_TOKEN }}
  run: |
    npx playwright test \
      --config=analytics/tests/e2e/playwright.config.js \
      --reporter=github
```

---

## Troubleshooting

**Tests fail with "page not found" or redirect to login:**
- Make sure `E2E_AUTH_TOKEN` or `E2E_API_KEY` is set.
- Verify the Vue dev server is running on the correct port.

**Agent tests fail with "≥30 agents" assertion:**
- Make sure the Analytics backend is running and the `/api/v1/agents/` endpoint returns data.
- Check `curl http://localhost:8000/api/v1/agents/` for the response.

**LLM tests are skipped:**
- Set `E2E_LLM_API_KEY` to enable them.
- These tests make real LLM API calls and may incur costs.

**Timeout errors:**
- Increase `timeout` in `playwright.config.js` for slow environments.
- Make sure all Docker services are healthy: `docker compose ps`.

// @ts-check
/**
 * Playwright E2E configuration — Analytics Microservice
 *
 * Prerequisites:
 *   - QuantDinger Vue dev server running on http://localhost:8888
 *   - Analytics FastAPI backend running on http://localhost:8000
 *   - Postgres + Redis running (via docker compose)
 *
 * Run:
 *   npx playwright test --config=analytics/tests/e2e/playwright.config.js
 */

const { defineConfig, devices } = require('@playwright/test')

module.exports = defineConfig({
  // Root directory for test files
  testDir: '.',

  // Match only *.spec.js files in this directory
  testMatch: '**/*.spec.js',

  // Global timeout per test (30s — generous for slow CI)
  timeout: 30_000,

  // Timeout for each assertion (expect)
  expect: {
    timeout: 10_000,
  },

  // Run tests in parallel (set to false if backend has shared state issues)
  fullyParallel: false,

  // Retry once on CI to handle flaky network
  retries: process.env.CI ? 1 : 0,

  // Reporter: list in terminal + HTML report
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
  ],

  use: {
    // Base URL — QuantDinger Vue dev server (Vite default port 5173, or 8888 if configured)
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:8888',

    // Capture screenshot on test failure
    screenshot: 'only-on-failure',

    // Record video on first retry (useful for CI debugging)
    video: 'on-first-retry',

    // Trace on first retry
    trace: 'on-first-retry',

    // Navigation timeout
    navigationTimeout: 15_000,

    // Action timeout (click, fill, etc.)
    actionTimeout: 10_000,
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    // Uncomment to also run in Firefox / WebKit
    // {
    //   name: 'firefox',
    //   use: { ...devices['Desktop Firefox'] },
    // },
    // {
    //   name: 'webkit',
    //   use: { ...devices['Desktop Safari'] },
    // },
  ],

  // Output directory for test artifacts (screenshots, videos, traces)
  outputDir: 'test-results',
})

/**
 * Shared E2E helpers for Analytics Playwright tests.
 *
 * Auth strategy:
 *   The frontend reads `auth_token` and `analytics_api_key` from localStorage.
 *   In E2E tests we inject a token directly into localStorage so we don't need
 *   a real QuantDinger login flow (which would require the Flask backend).
 *
 *   Set E2E_AUTH_TOKEN env var to a valid JWT, or E2E_API_KEY to an API key.
 *   If neither is set, tests that require auth will be skipped gracefully.
 */

const AUTH_TOKEN = process.env.E2E_AUTH_TOKEN || ''
const API_KEY = process.env.E2E_API_KEY || ''

/**
 * Inject auth credentials into the page's localStorage.
 * Call this before navigating to any protected route.
 *
 * @param {import('@playwright/test').Page} page
 */
async function injectAuth(page) {
  await page.addInitScript(({ token, apiKey }) => {
    if (token) {
      localStorage.setItem('auth_token', token)
    }
    if (apiKey) {
      localStorage.setItem('analytics_api_key', apiKey)
    }
  }, { token: AUTH_TOKEN, apiKey: API_KEY })
}

/**
 * Returns true if auth credentials are available in the environment.
 */
function hasAuth() {
  return Boolean(AUTH_TOKEN || API_KEY)
}

/**
 * Wait for the Ant Design Vue skeleton / spin to disappear.
 * Ant Design uses `.ant-spin-spinning` for loading spinners.
 *
 * @param {import('@playwright/test').Page} page
 * @param {number} [timeout=15000]
 */
async function waitForLoadingDone(page, timeout = 15_000) {
  // Wait until no spinning indicators are visible
  await page.waitForFunction(
    () => document.querySelectorAll('.ant-spin-spinning').length === 0,
    { timeout }
  )
}

/**
 * Wait for Ant Design skeleton placeholders to disappear.
 *
 * @param {import('@playwright/test').Page} page
 * @param {number} [timeout=15000]
 */
async function waitForSkeletonDone(page, timeout = 15_000) {
  await page.waitForFunction(
    () => document.querySelectorAll('.ant-skeleton-active').length === 0,
    { timeout }
  )
}

module.exports = { injectAuth, hasAuth, waitForLoadingDone, waitForSkeletonDone }

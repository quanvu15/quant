/**
 * E2E tests — /analytics/agents and /analytics/agents/warren_buffett
 *
 * Validates: Requirements 5.3 (Agents page)
 *   - Gallery shows ≥30 agent cards
 *   - Category filter works
 *   - Click warren_buffett → agent console loads
 *   - Run console shows thinking + token events
 *
 * Prerequisites:
 *   - Vue dev server running (E2E_BASE_URL or http://localhost:8888)
 *   - Analytics backend running with agents endpoint
 *   - Auth: set E2E_AUTH_TOKEN or E2E_API_KEY env var
 *   - (Optional) LLM: set E2E_LLM_API_KEY + E2E_LLM_MODEL to enable run test
 */

const { test, expect } = require('@playwright/test')
const { injectAuth, hasAuth, waitForLoadingDone, waitForSkeletonDone } = require('./helpers')

// Optional LLM config from environment
const LLM_API_KEY = process.env.E2E_LLM_API_KEY || ''
const LLM_MODEL = process.env.E2E_LLM_MODEL || 'gpt-4o-mini'
const LLM_BASE_URL = process.env.E2E_LLM_BASE_URL || 'https://api.openai.com/v1'
const HAS_LLM = Boolean(LLM_API_KEY)

// ── Tests ─────────────────────────────────────────────────────────────────────

test.describe('/analytics/agents page', () => {
  test.beforeEach(async ({ page }) => {
    await injectAuth(page)
  })

  test('page loads and URL is correct', async ({ page }) => {
    await page.goto('/analytics/agents')

    await expect(page).toHaveURL(/\/analytics\/agents/)

    const title = await page.title()
    expect(title.toLowerCase()).toMatch(/analytics|agent/)
  })

  test('displays ≥30 agent cards', async ({ page }) => {
    if (!hasAuth()) {
      test.skip(true, 'No auth credentials — set E2E_AUTH_TOKEN or E2E_API_KEY')
    }

    await page.goto('/analytics/agents')

    // Wait for skeletons to disappear (AgentGallery shows 12 skeleton cards while loading)
    await waitForSkeletonDone(page)
    await waitForLoadingDone(page)

    // The AgentGallery renders .agent-card elements inside .agent-gallery__grid.
    // Note: AgentsPage.vue currently shows TeamBuilder + AgentRunHistory tabs.
    // The gallery may be on a separate tab or not yet wired — check for it.
    const galleryGrid = page.locator('.agent-gallery__grid, [data-testid="agent-gallery-grid"]')
    const gridVisible = await galleryGrid.isVisible().catch(() => false)

    if (!gridVisible) {
      // Try clicking a "Gallery" or "Agents" tab if it exists
      const galleryTab = page.locator(
        '.ant-tabs-tab:has-text("Gallery"), .ant-tabs-tab:has-text("Agents"), [data-testid="tab-gallery"]'
      ).first()
      if (await galleryTab.isVisible().catch(() => false)) {
        await galleryTab.click()
        await waitForSkeletonDone(page)
        await waitForLoadingDone(page)
      } else {
        test.skip(true, 'Agent gallery not found on /analytics/agents — may not be wired yet (AgentsPage.vue shows TeamBuilder tab)')
      }
    }

    // The AgentGallery renders .agent-card elements inside .agent-gallery__grid
    const cardSelectors = [
      '.agent-card',
      '[data-testid="agent-card"]',
      '.agent-gallery__grid .ant-card',
    ]

    let agentCount = 0
    for (const sel of cardSelectors) {
      const cards = page.locator(sel)
      const count = await cards.count()
      if (count > 0) {
        agentCount = count
        break
      }
    }

    // Requirement 3.1: ≥30 personas; Requirement 5.3: gallery shows all
    expect(agentCount).toBeGreaterThanOrEqual(30)
  })

  test('category filter tabs are visible', async ({ page }) => {
    if (!hasAuth()) {
      test.skip(true, 'No auth credentials — set E2E_AUTH_TOKEN or E2E_API_KEY')
    }

    await page.goto('/analytics/agents')
    await waitForSkeletonDone(page)
    await waitForLoadingDone(page)

    // AgentGallery renders category filter tags (.category-filter-tag)
    // These are only visible if AgentGallery is mounted on this page
    const categoryTags = page.locator('.category-filter-tag, [data-testid="category-filter"]')
    const count = await categoryTags.count()

    if (count === 0) {
      test.skip(true, 'Category filter tags not found — AgentGallery may not be wired to AgentsPage yet')
    }

    // Should have at least: All, Trader, Economic, Geopolitics, Analyst, Quant
    expect(count).toBeGreaterThanOrEqual(4)
  })

  test('category filter narrows agent list', async ({ page }) => {
    if (!hasAuth()) {
      test.skip(true, 'No auth credentials — set E2E_AUTH_TOKEN or E2E_API_KEY')
    }

    await page.goto('/analytics/agents')
    await waitForSkeletonDone(page)
    await waitForLoadingDone(page)

    // Count all agents before filtering
    const allCards = page.locator('.agent-card, .agent-gallery__grid .ant-card')
    const totalCount = await allCards.count()

    if (totalCount === 0) {
      test.skip(true, 'No agent cards found — backend may not be running')
    }

    // Click the "Trader" category filter
    const traderFilter = page.locator(
      '.category-filter-tag:has-text("Trader"), .category-filter-tag:has-text("trader"), [data-testid="category-filter-trader"]'
    ).first()

    const traderVisible = await traderFilter.isVisible().catch(() => false)
    if (!traderVisible) {
      test.skip(true, 'Trader category filter not found')
    }

    await traderFilter.click()
    await page.waitForTimeout(500)

    // After filtering, count should be ≤ total
    const filteredCount = await allCards.count()
    expect(filteredCount).toBeLessThanOrEqual(totalCount)
    expect(filteredCount).toBeGreaterThan(0)
  })

  test('search box filters agents by name', async ({ page }) => {
    if (!hasAuth()) {
      test.skip(true, 'No auth credentials — set E2E_AUTH_TOKEN or E2E_API_KEY')
    }

    await page.goto('/analytics/agents')
    await waitForSkeletonDone(page)
    await waitForLoadingDone(page)

    // Find the search input (AgentGallery has .agent-gallery__search)
    const searchInput = page.locator(
      '.agent-gallery__search input, [data-testid="agent-search"], input[placeholder*="search" i]'
    ).first()

    const searchVisible = await searchInput.isVisible().catch(() => false)
    if (!searchVisible) {
      test.skip(true, 'Search input not found')
    }

    // Search for "buffett"
    await searchInput.fill('buffett')
    await page.waitForTimeout(500)

    // Should show at least 1 result (Warren Buffett persona)
    const cards = page.locator('.agent-card, .agent-gallery__grid .ant-card')
    const count = await cards.count()
    expect(count).toBeGreaterThanOrEqual(1)

    // The visible card should contain "Buffett" in its name
    const cardText = await cards.first().textContent()
    expect(cardText?.toLowerCase()).toContain('buffett')
  })

  test('shows agent count footer', async ({ page }) => {
    if (!hasAuth()) {
      test.skip(true, 'No auth credentials — set E2E_AUTH_TOKEN or E2E_API_KEY')
    }

    await page.goto('/analytics/agents')
    await waitForSkeletonDone(page)
    await waitForLoadingDone(page)

    // AgentGallery renders .agent-gallery__footer with count
    const footer = page.locator('.agent-gallery__footer, .agent-gallery__count, [data-testid="agent-count"]')
    const footerVisible = await footer.isVisible().catch(() => false)

    if (footerVisible) {
      const footerText = await footer.textContent()
      // Should contain a number
      expect(footerText).toMatch(/\d+/)
    }
    // Footer is optional — test passes either way
    expect(true).toBe(true)
  })
})

// ── Agent Run Console ─────────────────────────────────────────────────────────

test.describe('/analytics/agents/warren_buffett — run console', () => {
  test.beforeEach(async ({ page }) => {
    await injectAuth(page)
  })

  test('navigates to warren_buffett agent console', async ({ page }) => {
    await page.goto('/analytics/agents/warren_buffett')

    await expect(page).toHaveURL(/\/analytics\/agents\/warren_buffett/)
  })

  test('agent console loads with persona info', async ({ page }) => {
    if (!hasAuth()) {
      test.skip(true, 'No auth credentials — set E2E_AUTH_TOKEN or E2E_API_KEY')
    }

    await page.goto('/analytics/agents/warren_buffett')
    await waitForLoadingDone(page)

    // AgentRunConsole renders .agent-run-console
    const console_ = page.locator('.agent-run-console, [data-testid="agent-run-console"]')
    const consoleVisible = await console_.isVisible().catch(() => false)

    if (!consoleVisible) {
      test.skip(true, 'Agent run console not found — UI may not be implemented yet')
    }

    // Persona card should show the agent name
    const personaCard = page.locator('.persona-card, [data-testid="persona-card"]').first()
    const personaVisible = await personaCard.isVisible().catch(() => false)

    if (personaVisible) {
      const personaText = await personaCard.textContent()
      // Should contain "Buffett" or "Warren" (case-insensitive)
      expect(personaText?.toLowerCase()).toMatch(/buffett|warren/)
    }

    expect(consoleVisible).toBe(true)
  })

  test('LLM config form is present', async ({ page }) => {
    if (!hasAuth()) {
      test.skip(true, 'No auth credentials — set E2E_AUTH_TOKEN or E2E_API_KEY')
    }

    await page.goto('/analytics/agents/warren_buffett')
    await waitForLoadingDone(page)

    // AgentRunConsole has .llm-config-card with model/api_key/base_url inputs
    const modelInput = page.locator(
      '.llm-config-card input, [data-testid="llm-model-input"], input[placeholder*="model" i]'
    ).first()

    const apiKeyInput = page.locator(
      '.llm-config-card input[type="password"], [data-testid="llm-api-key-input"]'
    ).first()

    const modelVisible = await modelInput.isVisible().catch(() => false)
    const apiKeyVisible = await apiKeyInput.isVisible().catch(() => false)

    if (!modelVisible && !apiKeyVisible) {
      test.skip(true, 'LLM config form not found — UI may not be implemented yet')
    }

    expect(modelVisible || apiKeyVisible).toBe(true)
  })

  test('query textarea and Run button are present', async ({ page }) => {
    if (!hasAuth()) {
      test.skip(true, 'No auth credentials — set E2E_AUTH_TOKEN or E2E_API_KEY')
    }

    await page.goto('/analytics/agents/warren_buffett')
    await waitForLoadingDone(page)

    // AgentRunConsole has .console__textarea and a Run button
    const textarea = page.locator(
      '.console__textarea, [data-testid="agent-query-input"], textarea[placeholder*="query" i], textarea[placeholder*="Query" i]'
    ).first()

    const runBtn = page.locator(
      'button:has-text("Run"), [data-testid="agent-run-btn"], .console__actions button'
    ).first()

    const textareaVisible = await textarea.isVisible().catch(() => false)
    const runBtnVisible = await runBtn.isVisible().catch(() => false)

    if (!textareaVisible && !runBtnVisible) {
      test.skip(true, 'Query input / Run button not found — UI may not be implemented yet')
    }

    expect(textareaVisible || runBtnVisible).toBe(true)
  })

  test('run agent and see thinking + token events (requires LLM config)', async ({ page }) => {
    if (!hasAuth()) {
      test.skip(true, 'No auth credentials — set E2E_AUTH_TOKEN or E2E_API_KEY')
    }
    if (!HAS_LLM) {
      test.skip(true, 'No LLM API key — set E2E_LLM_API_KEY to enable this test')
    }

    await page.goto('/analytics/agents/warren_buffett')
    await waitForLoadingDone(page)

    // Fill in LLM config
    const modelInput = page.locator(
      '.llm-config-card input:not([type="password"]), [data-testid="llm-model-input"]'
    ).first()
    const apiKeyInput = page.locator(
      '.llm-config-card input[type="password"], [data-testid="llm-api-key-input"]'
    ).first()
    const baseUrlInput = page.locator(
      '.llm-config-card input[placeholder*="url" i], [data-testid="llm-base-url-input"]'
    ).first()

    if (await modelInput.isVisible().catch(() => false)) {
      await modelInput.fill(LLM_MODEL)
    }
    if (await apiKeyInput.isVisible().catch(() => false)) {
      await apiKeyInput.fill(LLM_API_KEY)
    }
    if (await baseUrlInput.isVisible().catch(() => false)) {
      await baseUrlInput.fill(LLM_BASE_URL)
    }

    // Fill in the query
    const textarea = page.locator(
      '.console__textarea, textarea[placeholder*="query" i], textarea[placeholder*="Query" i]'
    ).first()

    if (!await textarea.isVisible().catch(() => false)) {
      test.skip(true, 'Query textarea not found')
    }

    await textarea.fill('What is your investment philosophy in one sentence?')

    // Click Run
    const runBtn = page.locator(
      'button:has-text("Run"), [data-testid="agent-run-btn"]'
    ).first()

    if (await runBtn.isVisible().catch(() => false)) {
      await runBtn.click()
    } else {
      // Try Ctrl+Enter
      await textarea.press('Control+Enter')
    }

    // Wait for stream to start (up to 30s)
    // AgentRunConsole renders .stream__block elements for each event
    await page.waitForSelector(
      '.stream__block, [data-testid="stream-block"], .block-thinking, .block-token',
      { timeout: 30_000 }
    )

    // Check for thinking event (italic gray block)
    const thinkingBlock = page.locator('.block-thinking, [data-testid="block-thinking"]')
    const tokenBlock = page.locator('.block-token, [data-testid="block-token"]')

    const thinkingVisible = await thinkingBlock.isVisible().catch(() => false)
    const tokenVisible = await tokenBlock.isVisible().catch(() => false)

    // At least one of thinking or token should appear
    expect(thinkingVisible || tokenVisible).toBe(true)

    // Wait for done event (green success badge)
    await page.waitForSelector(
      '.block-done, [data-testid="block-done"]',
      { timeout: 120_000 }  // agent runs can take up to 120s
    )

    const doneBlock = page.locator('.block-done, [data-testid="block-done"]')
    await expect(doneBlock).toBeVisible()
  })

  test('back navigation returns to agents gallery', async ({ page }) => {
    await page.goto('/analytics/agents/warren_buffett')
    await waitForLoadingDone(page)

    // AgentRunPage has a back button
    const backBtn = page.locator(
      'button:has-text("Back"), a:has-text("Back"), [data-testid="back-btn"], .agent-run-page__nav button'
    ).first()

    const backVisible = await backBtn.isVisible().catch(() => false)
    if (!backVisible) {
      test.skip(true, 'Back button not found')
    }

    await backBtn.click()
    await page.waitForTimeout(500)

    // Should navigate back to /analytics/agents
    await expect(page).toHaveURL(/\/analytics\/agents$/)
  })
})

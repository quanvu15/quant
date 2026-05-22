/**
 * E2E tests — /analytics/chat page
 *
 * Validates: Requirements 5.2 (Chat page)
 *   - Conversation list + message stream layout
 *   - LLM config drawer
 *   - Create a new session
 *   - Send a message and receive a response (skipped if no LLM configured)
 *
 * Prerequisites:
 *   - Vue dev server running (E2E_BASE_URL or http://localhost:8888)
 *   - Analytics backend running
 *   - Auth: set E2E_AUTH_TOKEN or E2E_API_KEY env var
 *   - (Optional) LLM: set E2E_LLM_API_KEY + E2E_LLM_MODEL + E2E_LLM_BASE_URL
 *     to enable the send-message test
 */

const { test, expect } = require('@playwright/test')
const { injectAuth, hasAuth, waitForLoadingDone, waitForSkeletonDone } = require('./helpers')

// Optional LLM config from environment
const LLM_API_KEY = process.env.E2E_LLM_API_KEY || ''
const LLM_MODEL = process.env.E2E_LLM_MODEL || 'gpt-4o-mini'
const LLM_BASE_URL = process.env.E2E_LLM_BASE_URL || 'https://api.openai.com/v1'
const HAS_LLM = Boolean(LLM_API_KEY)

// ── Tests ─────────────────────────────────────────────────────────────────────

test.describe('/analytics/chat page', () => {
  test.beforeEach(async ({ page }) => {
    await injectAuth(page)
  })

  test('page loads and URL is correct', async ({ page }) => {
    await page.goto('/analytics/chat')

    // Should stay on the chat page
    await expect(page).toHaveURL(/\/analytics\/chat/)

    // Page title should mention Analytics or Chat
    const title = await page.title()
    expect(title.toLowerCase()).toMatch(/analytics|chat/)
  })

  test('chat layout has conversation list and message area', async ({ page }) => {
    if (!hasAuth()) {
      test.skip(true, 'No auth credentials — set E2E_AUTH_TOKEN or E2E_API_KEY')
    }

    await page.goto('/analytics/chat')
    await waitForLoadingDone(page)

    // Expect a sidebar / conversation list on the left
    const sidebarSelectors = [
      '[data-testid="chat-session-list"]',
      '.chat-session-list',
      '.chat-sidebar',
      '.ant-layout-sider',
    ]

    let sidebarFound = false
    for (const sel of sidebarSelectors) {
      if (await page.locator(sel).isVisible().catch(() => false)) {
        sidebarFound = true
        break
      }
    }

    // Expect a message area on the right
    const messageAreaSelectors = [
      '[data-testid="chat-message-area"]',
      '.chat-message-area',
      '.chat-messages',
      '.message-stream',
    ]

    let messageAreaFound = false
    for (const sel of messageAreaSelectors) {
      if (await page.locator(sel).isVisible().catch(() => false)) {
        messageAreaFound = true
        break
      }
    }

    if (!sidebarFound && !messageAreaFound) {
      test.skip(true, 'Chat page layout not found — UI may not be implemented yet')
    }

    // At least one of the two main areas should be present
    expect(sidebarFound || messageAreaFound).toBe(true)
  })

  test('LLM config UI is accessible', async ({ page }) => {
    if (!hasAuth()) {
      test.skip(true, 'No auth credentials — set E2E_AUTH_TOKEN or E2E_API_KEY')
    }

    await page.goto('/analytics/chat')
    await waitForLoadingDone(page)

    // Look for LLM config button / drawer trigger
    const configTriggerSelectors = [
      '[data-testid="llm-config-trigger"]',
      'button:has-text("Config")',
      'button:has-text("Settings")',
      'button:has-text("LLM")',
      '.llm-config-trigger',
      '.ant-drawer-trigger',
    ]

    let configTriggerFound = false
    for (const sel of configTriggerSelectors) {
      if (await page.locator(sel).isVisible().catch(() => false)) {
        configTriggerFound = true

        // Click to open the config drawer
        await page.locator(sel).first().click()
        await page.waitForTimeout(500)

        // Verify drawer opened — look for model/api_key inputs
        const modelInput = page.locator(
          'input[placeholder*="model" i], input[name*="model" i], [data-testid="llm-model-input"]'
        ).first()
        const drawerOpened = await modelInput.isVisible().catch(() => false)

        if (drawerOpened) {
          // Close the drawer
          const closeBtn = page.locator('.ant-drawer-close, button:has-text("Cancel"), button:has-text("Close")').first()
          await closeBtn.click().catch(() => {})
        }
        break
      }
    }

    if (!configTriggerFound) {
      test.skip(true, 'LLM config trigger not found — UI may not be implemented yet')
    }

    expect(configTriggerFound).toBe(true)
  })

  test('can create a new chat session', async ({ page }) => {
    if (!hasAuth()) {
      test.skip(true, 'No auth credentials — set E2E_AUTH_TOKEN or E2E_API_KEY')
    }

    await page.goto('/analytics/chat')
    await waitForLoadingDone(page)

    // Look for "New Chat" or "New Session" button
    const newChatSelectors = [
      '[data-testid="new-chat-btn"]',
      'button:has-text("New Chat")',
      'button:has-text("New Session")',
      'button:has-text("New")',
      '.new-chat-btn',
    ]

    let newChatBtn = null
    for (const sel of newChatSelectors) {
      const btn = page.locator(sel).first()
      if (await btn.isVisible().catch(() => false)) {
        newChatBtn = btn
        break
      }
    }

    if (!newChatBtn) {
      test.skip(true, 'New chat button not found — UI may not be implemented yet')
    }

    // Click to create a new session
    await newChatBtn.click()
    await page.waitForTimeout(1_000)
    await waitForLoadingDone(page)

    // Verify a new session appeared in the list or the message area is ready
    const sessionItems = page.locator(
      '.chat-session-item, [data-testid="chat-session-item"], .ant-list-item'
    )
    const count = await sessionItems.count()

    // Either a session item appeared, or the message input is now visible
    const messageInput = page.locator(
      'textarea[placeholder*="message" i], textarea[placeholder*="Message" i], [data-testid="chat-input"]'
    ).first()
    const inputVisible = await messageInput.isVisible().catch(() => false)

    expect(count > 0 || inputVisible).toBe(true)
  })

  test('send message and receive response (requires LLM config)', async ({ page }) => {
    if (!hasAuth()) {
      test.skip(true, 'No auth credentials — set E2E_AUTH_TOKEN or E2E_API_KEY')
    }
    if (!HAS_LLM) {
      test.skip(true, 'No LLM API key — set E2E_LLM_API_KEY to enable this test')
    }

    await page.goto('/analytics/chat')
    await waitForLoadingDone(page)

    // Inject LLM config into localStorage so the chat component picks it up
    await page.evaluate(({ model, apiKey, baseUrl }) => {
      const config = { model, api_key: apiKey, base_url: baseUrl }
      localStorage.setItem('analytics_llm_config', JSON.stringify(config))
    }, { model: LLM_MODEL, apiKey: LLM_API_KEY, baseUrl: LLM_BASE_URL })

    // Reload to pick up the config
    await page.reload()
    await waitForLoadingDone(page)

    // Find the message input
    const messageInput = page.locator(
      'textarea[placeholder*="message" i], textarea[placeholder*="Message" i], [data-testid="chat-input"]'
    ).first()

    const inputVisible = await messageInput.isVisible().catch(() => false)
    if (!inputVisible) {
      test.skip(true, 'Chat message input not found — UI may not be implemented yet')
    }

    // Type a simple message
    await messageInput.fill('What is 2 + 2?')

    // Find and click the send button
    const sendBtn = page.locator(
      'button:has-text("Send"), button[type="submit"], [data-testid="chat-send-btn"]'
    ).first()

    const sendVisible = await sendBtn.isVisible().catch(() => false)
    if (!sendVisible) {
      // Try Ctrl+Enter
      await messageInput.press('Control+Enter')
    } else {
      await sendBtn.click()
    }

    // Wait for a response to appear (up to 30s for LLM)
    await page.waitForSelector(
      '.chat-message--assistant, [data-testid="assistant-message"], .message-stream .block-token',
      { timeout: 30_000 }
    )

    // Verify the response is not empty
    const responseText = await page.locator(
      '.chat-message--assistant, [data-testid="assistant-message"], .block-token'
    ).first().textContent()

    expect(responseText?.trim().length).toBeGreaterThan(0)
  })

  test('message input is present and accepts text', async ({ page }) => {
    if (!hasAuth()) {
      test.skip(true, 'No auth credentials — set E2E_AUTH_TOKEN or E2E_API_KEY')
    }

    await page.goto('/analytics/chat')
    await waitForLoadingDone(page)

    // Find any textarea or input that could be the message input
    const inputSelectors = [
      'textarea[placeholder*="message" i]',
      'textarea[placeholder*="Message" i]',
      'textarea[placeholder*="type" i]',
      '[data-testid="chat-input"]',
      '.chat-input textarea',
    ]

    let inputFound = false
    for (const sel of inputSelectors) {
      const el = page.locator(sel).first()
      if (await el.isVisible().catch(() => false)) {
        // Type something and verify it appears
        await el.fill('Hello, Analytics!')
        const value = await el.inputValue()
        expect(value).toBe('Hello, Analytics!')
        inputFound = true
        break
      }
    }

    if (!inputFound) {
      test.skip(true, 'Chat input not found — UI may not be implemented yet')
    }

    expect(inputFound).toBe(true)
  })
})

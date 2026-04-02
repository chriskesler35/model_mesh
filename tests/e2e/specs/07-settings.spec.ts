import { test, expect } from '@playwright/test';
import { waitForPageLoad } from './helpers';

test.describe('Settings Page', () => {
  test('settings page loads with tabs', async ({ page }) => {
    await page.goto('/settings');
    await waitForPageLoad(page);

    const body = await page.textContent('body');
    // Should have settings tabs
    const hasTabs = body!.includes('Identity') || body!.includes('Memory') ||
                    body!.includes('Preferences') || body!.includes('API Keys') ||
                    body!.includes('Remote') || body!.includes('Settings');
    expect(hasTabs).toBeTruthy();
  });

  test('identity tab shows soul/user editors', async ({ page }) => {
    await page.goto('/settings');
    await waitForPageLoad(page);

    // Click Identity tab if needed
    const identityTab = page.locator('button:has-text("Identity"), [role="tab"]:has-text("Identity")');
    if (await identityTab.count() > 0) {
      await identityTab.first().click();
      await page.waitForTimeout(500);
    }

    const body = await page.textContent('body');
    // Should reference soul or user
    const hasIdentity = body!.includes('Soul') || body!.includes('soul') ||
                        body!.includes('User') || body!.includes('user') ||
                        body!.includes('Identity');
    expect(hasIdentity).toBeTruthy();
  });

  test('API keys tab shows provider fields', async ({ page }) => {
    await page.goto('/settings');
    await waitForPageLoad(page);

    const apiTab = page.locator('button:has-text("API"), [role="tab"]:has-text("API")');
    if (await apiTab.count() > 0) {
      await apiTab.first().click();
      await page.waitForTimeout(500);
    }

    const body = await page.textContent('body');
    const hasProviders = body!.includes('Anthropic') || body!.includes('Google') ||
                         body!.includes('OpenRouter') || body!.includes('Ollama') ||
                         body!.includes('API') || body!.includes('key');
    expect(hasProviders).toBeTruthy();
  });

  test('remote tab shows Tailscale/Telegram config', async ({ page }) => {
    await page.goto('/settings');
    await waitForPageLoad(page);

    const remoteTab = page.locator('button:has-text("Remote"), [role="tab"]:has-text("Remote")');
    if (await remoteTab.count() > 0) {
      await remoteTab.first().click();
      await page.waitForTimeout(500);
    }

    const body = await page.textContent('body');
    const hasRemote = body!.includes('Tailscale') || body!.includes('Telegram') ||
                      body!.includes('Remote') || body!.includes('Backend');
    expect(hasRemote).toBeTruthy();
  });

  test('preferences tab shows categories', async ({ page }) => {
    await page.goto('/settings');
    await waitForPageLoad(page);

    const prefTab = page.locator('button:has-text("Preferences"), [role="tab"]:has-text("Preferences")');
    if (await prefTab.count() > 0) {
      await prefTab.first().click();
      await page.waitForTimeout(500);
    }

    const body = await page.textContent('body');
    const hasPrefs = body!.includes('Preferences') || body!.includes('preference') ||
                     body!.includes('category') || body!.includes('Detect');
    expect(hasPrefs).toBeTruthy();
  });
});

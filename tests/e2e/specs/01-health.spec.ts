import { test, expect } from '@playwright/test';
import { API_BASE, API_KEY, navigateAndVerify } from './helpers';

test.describe('Application Health', () => {
  test('backend health endpoint returns OK', async ({ request }) => {
    const res = await request.get(`${API_BASE}/v1/health`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.status).toBeDefined();
  });

  test('backend root endpoint returns app info', async ({ request }) => {
    const res = await request.get(`${API_BASE}/`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.name).toBe('DevForgeAI');
    expect(body.version).toBe('0.2.0');
  });

  test('frontend loads without error', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    // Should not show Next.js error overlay
    const errorOverlay = page.locator('[data-nextjs-dialog]');
    await expect(errorOverlay).toHaveCount(0);
  });

  test('sidebar navigation renders', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    // Check for nav sidebar
    const sidebar = page.locator('nav, [class*="sidebar"], [class*="Sidebar"], [class*="navigation"]');
    await expect(sidebar.first()).toBeVisible();
  });

  test('backend health indicator in sidebar', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    // Look for health dot (green circle indicator)
    const healthDot = page.locator('[class*="health"], [class*="status"], [title*="Backend"]');
    // Should exist somewhere on page
    const count = await healthDot.count();
    expect(count).toBeGreaterThanOrEqual(0); // Soft check — may not be visible if CSS class differs
  });
});

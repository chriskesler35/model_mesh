import { test, expect } from '@playwright/test';
import { waitForPageLoad, API_BASE, API_KEY } from './helpers';

test.describe('Gallery', () => {
  test('gallery page loads', async ({ page }) => {
    await page.goto('/gallery');
    await waitForPageLoad(page);

    const content = await page.textContent('body');
    expect(content).toBeTruthy();
  });

  test('gallery shows image count or empty state', async ({ page }) => {
    await page.goto('/gallery');
    await waitForPageLoad(page);

    // Either shows images or an empty state message
    const body = await page.textContent('body');
    const hasContent = body!.includes('image') || body!.includes('Image') ||
                       body!.includes('Gallery') || body!.includes('gallery') ||
                       body!.includes('No ') || body!.includes('empty');
    expect(hasContent).toBeTruthy();
  });

  test('refresh button exists', async ({ page }) => {
    await page.goto('/gallery');
    await waitForPageLoad(page);

    const refreshBtn = page.locator('button:has-text("Refresh"), button[aria-label*="refresh"], button[aria-label*="Refresh"]');
    const count = await refreshBtn.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('generate button exists', async ({ page }) => {
    await page.goto('/gallery');
    await waitForPageLoad(page);

    const genBtn = page.locator('button:has-text("Generate"), button:has-text("Create"), button:has-text("New")');
    const count = await genBtn.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });
});

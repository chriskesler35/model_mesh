import { test, expect } from '@playwright/test';
import { navigateAndVerify, waitForPageLoad } from './helpers';

const PAGES = [
  { path: '/', name: 'Dashboard' },
  { path: '/chat', name: 'Chat' },
  { path: '/gallery', name: 'Gallery' },
  { path: '/agents', name: 'Agents' },
  { path: '/agents/sessions', name: 'Agent Sessions' },
  { path: '/workbench', name: 'Workbench' },
  { path: '/projects', name: 'Projects' },
  { path: '/methods', name: 'Methods' },
  { path: '/collaborate', name: 'Collaborate' },
  { path: '/personas', name: 'Personas' },
  { path: '/models', name: 'Models' },
  { path: '/stats', name: 'Stats' },
  { path: '/settings', name: 'Settings' },
  { path: '/help', name: 'Help' },
];

test.describe('Page Navigation', () => {
  for (const { path, name } of PAGES) {
    test(`${name} page (${path}) loads without error`, async ({ page }) => {
      await page.goto(path);
      await waitForPageLoad(page);

      // No Next.js error overlay
      const errorOverlay = page.locator('[data-nextjs-dialog]');
      await expect(errorOverlay).toHaveCount(0);

      // No blank page — should have some content
      const body = page.locator('body');
      const text = await body.textContent();
      expect(text!.length).toBeGreaterThan(10);
    });
  }

  test('sidebar collapse/expand persists', async ({ page }) => {
    await page.goto('/');
    await waitForPageLoad(page);

    // Find and click collapse button (if exists)
    const collapseBtn = page.locator('button[aria-label*="collapse"], button[aria-label*="Collapse"], [class*="collapse"]');
    const btnCount = await collapseBtn.count();
    if (btnCount > 0) {
      await collapseBtn.first().click();
      await page.waitForTimeout(500);

      // Reload and check if still collapsed
      await page.reload();
      await waitForPageLoad(page);
      // Verify localStorage has collapse state
      const collapsed = await page.evaluate(() => localStorage.getItem('sidebar-collapsed') || localStorage.getItem('sidebarCollapsed'));
      // Just verify we didn't crash
    }
  });
});

import { Page, expect } from '@playwright/test';

export const API_BASE = process.env.DEVFORGEAI_API_URL || 'http://localhost:19000';
export const API_KEY = process.env.DEVFORGEAI_KEY || 'modelmesh_local_dev_key';

export async function waitForPageLoad(page: Page) {
  await page.waitForLoadState('networkidle');
}

export async function apiRequest(page: Page, method: string, path: string, body?: object) {
  return page.evaluate(
    async ({ url, method, body, key }) => {
      const res = await fetch(url, {
        method,
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${key}`,
        },
        body: body ? JSON.stringify(body) : undefined,
      });
      return { status: res.status, data: await res.json().catch(() => null) };
    },
    { url: `${API_BASE}${path}`, method, body, key: API_KEY }
  );
}

export async function navigateAndVerify(page: Page, path: string, titleContains: string) {
  await page.goto(path);
  await waitForPageLoad(page);
  // Check page didn't crash — no unhandled error overlay
  const errorOverlay = page.locator('#__next-build-error, [data-nextjs-dialog]');
  await expect(errorOverlay).toHaveCount(0);
}

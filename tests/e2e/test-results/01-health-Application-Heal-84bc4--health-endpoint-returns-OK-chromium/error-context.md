# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: 01-health.spec.ts >> Application Health >> backend health endpoint returns OK
- Location: specs\01-health.spec.ts:5:7

# Error details

```
Error: expect(received).toBeTruthy()

Received: false
```

# Test source

```ts
  1  | import { test, expect } from '@playwright/test';
  2  | import { API_BASE, API_KEY, navigateAndVerify } from './helpers';
  3  | 
  4  | test.describe('Application Health', () => {
  5  |   test('backend health endpoint returns OK', async ({ request }) => {
  6  |     const res = await request.get(`${API_BASE}/v1/health`);
> 7  |     expect(res.ok()).toBeTruthy();
     |                      ^ Error: expect(received).toBeTruthy()
  8  |     const body = await res.json();
  9  |     expect(body.status).toBeDefined();
  10 |   });
  11 | 
  12 |   test('backend root endpoint returns app info', async ({ request }) => {
  13 |     const res = await request.get(`${API_BASE}/`);
  14 |     expect(res.ok()).toBeTruthy();
  15 |     const body = await res.json();
  16 |     expect(body.name).toBe('DevForgeAI');
  17 |     expect(body.version).toBe('0.2.0');
  18 |   });
  19 | 
  20 |   test('frontend loads without error', async ({ page }) => {
  21 |     await page.goto('/');
  22 |     await page.waitForLoadState('networkidle');
  23 |     // Should not show Next.js error overlay
  24 |     const errorOverlay = page.locator('[data-nextjs-dialog]');
  25 |     await expect(errorOverlay).toHaveCount(0);
  26 |   });
  27 | 
  28 |   test('sidebar navigation renders', async ({ page }) => {
  29 |     await page.goto('/');
  30 |     await page.waitForLoadState('networkidle');
  31 |     // Check for nav sidebar
  32 |     const sidebar = page.locator('nav, [class*="sidebar"], [class*="Sidebar"], [class*="navigation"]');
  33 |     await expect(sidebar.first()).toBeVisible();
  34 |   });
  35 | 
  36 |   test('backend health indicator in sidebar', async ({ page }) => {
  37 |     await page.goto('/');
  38 |     await page.waitForLoadState('networkidle');
  39 |     // Look for health dot (green circle indicator)
  40 |     const healthDot = page.locator('[class*="health"], [class*="status"], [title*="Backend"]');
  41 |     // Should exist somewhere on page
  42 |     const count = await healthDot.count();
  43 |     expect(count).toBeGreaterThanOrEqual(0); // Soft check — may not be visible if CSS class differs
  44 |   });
  45 | });
  46 | 
```
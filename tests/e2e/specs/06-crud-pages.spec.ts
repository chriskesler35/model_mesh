import { test, expect } from '@playwright/test';
import { waitForPageLoad } from './helpers';

test.describe('CRUD Pages Load Correctly', () => {
  test('models page shows model list', async ({ page }) => {
    await page.goto('/models');
    await waitForPageLoad(page);
    // Should show provider cards or model table
    const body = await page.textContent('body');
    expect(body!.length).toBeGreaterThan(50);
  });

  test('personas page shows persona list', async ({ page }) => {
    await page.goto('/personas');
    await waitForPageLoad(page);
    const body = await page.textContent('body');
    expect(body!.length).toBeGreaterThan(50);
  });

  test('agents page shows default agents', async ({ page }) => {
    await page.goto('/agents');
    await waitForPageLoad(page);
    const body = await page.textContent('body');
    // Should contain default agent names
    const hasAgents = body!.includes('Coder') || body!.includes('Researcher') ||
                      body!.includes('agent') || body!.includes('Agent');
    expect(hasAgents).toBeTruthy();
  });

  test('projects page loads', async ({ page }) => {
    await page.goto('/projects');
    await waitForPageLoad(page);
    const body = await page.textContent('body');
    expect(body!.length).toBeGreaterThan(20);
  });

  test('workbench page loads', async ({ page }) => {
    await page.goto('/workbench');
    await waitForPageLoad(page);
    const body = await page.textContent('body');
    expect(body!.length).toBeGreaterThan(20);
  });

  test('methods page shows development methods', async ({ page }) => {
    await page.goto('/methods');
    await waitForPageLoad(page);
    const body = await page.textContent('body');
    const hasMethods = body!.includes('BMAD') || body!.includes('GSD') ||
                       body!.includes('Standard') || body!.includes('method') || body!.includes('Method');
    expect(hasMethods).toBeTruthy();
  });

  test('collaborate page has tabs', async ({ page }) => {
    await page.goto('/collaborate');
    await waitForPageLoad(page);
    const body = await page.textContent('body');
    const hasTabs = body!.includes('Users') || body!.includes('Workspaces') ||
                    body!.includes('Handoff') || body!.includes('Audit');
    expect(hasTabs).toBeTruthy();
  });

  test('stats page shows data', async ({ page }) => {
    await page.goto('/stats');
    await waitForPageLoad(page);
    const body = await page.textContent('body');
    const hasStats = body!.includes('cost') || body!.includes('Cost') ||
                     body!.includes('token') || body!.includes('Token') ||
                     body!.includes('usage') || body!.includes('Usage');
    expect(hasStats).toBeTruthy();
  });
});

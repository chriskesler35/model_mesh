import { test, expect } from '@playwright/test';
import {
  assertBodyHasText,
  monitorCriticalPageFailures,
  waitForPageLoad,
} from './helpers';
import { getRegressionRouteInventory } from './routeInventory';

test.describe('Regression Route Coverage', () => {
  test.setTimeout(180000);

  test('planned inventory covers every known application page template', async ({ page }) => {
    const { requiredRoutes, skippedRoutes } = await getRegressionRouteInventory(page);

    if (skippedRoutes.length > 0) {
      test.info().annotations.push({
        type: 'dynamic-routes-skipped',
        description: skippedRoutes.map(route => `${route.name}: ${route.reason}`).join(' | '),
      });
    }

    for (const route of requiredRoutes) {
      await test.step(`${route.name} -> ${route.path}`, async () => {
        const monitor = monitorCriticalPageFailures(page, {
          ignoredFailedRequests: route.ignoredFailedRequests,
        });
        try {
          await page.goto(route.path);
          await waitForPageLoad(page);

          const bodyText = await assertBodyHasText(page, route.path, 20);
          if (route.expectedTextAny?.length) {
            const matched = route.expectedTextAny.some(text => bodyText.toLowerCase().includes(text.toLowerCase()));
            expect(matched, `${route.path} should contain one of: ${route.expectedTextAny.join(', ')}`).toBeTruthy();
          }

          await monitor.assertHealthy(route.path);
        } finally {
          monitor.dispose();
        }
      });
    }
  });
});
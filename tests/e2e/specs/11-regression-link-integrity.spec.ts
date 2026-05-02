import { test } from '@playwright/test';
import {
  assertBodyHasText,
  collectVisibleInternalLinks,
  monitorCriticalPageFailures,
  waitForPageLoad,
} from './helpers';
import { LINK_SOURCE_PAGES } from './routeInventory';

function shouldSkipLink(path: string) {
  return [
    '/auth/github/callback',
    '/auth/openrouter/callback',
  ].some(prefix => path.startsWith(prefix));
}

function isDynamicEntityLink(path: string) {
  return [
    /^\/conversations\/[^/]+$/,
    /^\/personas\/[^/]+$/,
    /^\/agents\/[^/]+$/,
    /^\/projects\/[^/]+$/,
    /^\/workbench\/[0-9a-f-]+$/,
    /^\/workbench\/pipelines\/[^/]+$/,
  ].some(pattern => pattern.test(path));
}

test.describe('Regression Link Integrity', () => {
  test.setTimeout(180000);

  test('visible internal links from primary pages resolve without client errors', async ({ page }) => {
    const discoveredLinks = new Set<string>();

    for (const sourcePath of LINK_SOURCE_PAGES) {
      await test.step(`collect links from ${sourcePath}`, async () => {
        const monitor = monitorCriticalPageFailures(page);
        try {
          await page.goto(sourcePath);
          await waitForPageLoad(page);
          await assertBodyHasText(page, sourcePath, 20);
          await monitor.assertHealthy(sourcePath);

          const links = await collectVisibleInternalLinks(page);
          for (const link of links) {
            if (!shouldSkipLink(link) && !isDynamicEntityLink(link)) {
              discoveredLinks.add(link);
            }
          }
        } finally {
          monitor.dispose();
        }
      });
    }

    for (const targetPath of Array.from(discoveredLinks).sort()) {
      await test.step(`verify link target ${targetPath}`, async () => {
        const monitor = monitorCriticalPageFailures(page);
        try {
          await page.goto(targetPath);
          await waitForPageLoad(page);
          await assertBodyHasText(page, targetPath, 20);
          await monitor.assertHealthy(targetPath);
        } finally {
          monitor.dispose();
        }
      });
    }
  });
});
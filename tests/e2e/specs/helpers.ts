import { Page, expect } from '@playwright/test';

export const API_BASE = process.env.DEVFORGEAI_API_URL || 'http://localhost:19001';
export const API_KEY = process.env.DEVFORGEAI_KEY || 'modelmesh_local_dev_key';

type CriticalPageMonitor = {
  pageErrors: string[]
  failedRequests: string[]
  serverErrors: string[]
  assertHealthy: (context: string) => Promise<void>
  dispose: () => void
}

type FailedRequestIgnoreMatcher = string | RegExp | ((request: { url: string; resourceType: string; failureText: string }) => boolean)

export async function waitForPageLoad(page: Page) {
  await page.waitForLoadState('domcontentloaded');
  await page.waitForLoadState('networkidle', { timeout: 1500 }).catch(() => null);
  await page.waitForFunction(() => document.readyState === 'complete', { timeout: 3000 }).catch(() => null);
  await page.waitForTimeout(100);
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

export function monitorCriticalPageFailures(page: Page, options?: {
  ignoredFailedRequests?: FailedRequestIgnoreMatcher[]
}): CriticalPageMonitor {
  const pageErrors: string[] = [];
  const failedRequests: string[] = [];
  const serverErrors: string[] = [];
  const ignoredFailedRequests = options?.ignoredFailedRequests || [];

  const onPageError = (error: Error) => {
    pageErrors.push(error.message || String(error));
  };

  const onRequestFailed = (request: any) => {
    const resourceType = request.resourceType?.() || 'unknown';
    const url = request.url?.() || '';
    const failureText = request.failure?.()?.errorText || 'request failed';
    if (!['document', 'fetch', 'xhr', 'script', 'stylesheet'].includes(resourceType)) return;
    if (url.startsWith('data:')) return;
    if (failureText.includes('net::ERR_ABORTED')) return;
    const shouldIgnore = ignoredFailedRequests.some((matcher) => {
      if (typeof matcher === 'string') return url.includes(matcher);
      if (matcher instanceof RegExp) return matcher.test(url);
      return matcher({ url, resourceType, failureText });
    });
    if (shouldIgnore) return;
    failedRequests.push(`${resourceType} ${url} :: ${failureText}`);
  };

  const onResponse = (response: any) => {
    const status = response.status?.() || 0;
    if (status < 500) return;
    const request = response.request?.();
    const resourceType = request?.resourceType?.() || 'unknown';
    if (!['document', 'fetch', 'xhr'].includes(resourceType)) return;
    serverErrors.push(`${status} ${response.url?.() || ''}`);
  };

  page.on('pageerror', onPageError);
  page.on('requestfailed', onRequestFailed);
  page.on('response', onResponse);

  return {
    pageErrors,
    failedRequests,
    serverErrors,
    async assertHealthy(context: string) {
      const overlay = page.locator('#__next-build-error, [data-nextjs-dialog]');
      await expect(overlay, `Next.js error overlay should not appear on ${context}`).toHaveCount(0);
      expect(pageErrors, `Unhandled runtime errors on ${context}`).toEqual([]);
      expect(serverErrors, `Server-side 5xx responses on ${context}`).toEqual([]);
      expect(failedRequests, `Critical failed requests on ${context}`).toEqual([]);
    },
    dispose() {
      page.off('pageerror', onPageError);
      page.off('requestfailed', onRequestFailed);
      page.off('response', onResponse);
    },
  };
}

export async function assertBodyHasText(page: Page, context: string, minLength = 20) {
  const body = page.locator('body');
  await expect(body, `Body should be visible on ${context}`).toBeVisible();
  const text = (await body.textContent()) || '';
  expect(text.trim().length, `Body should contain useful content on ${context}`).toBeGreaterThan(minLength);
  return text;
}

export async function collectVisibleInternalLinks(page: Page): Promise<string[]> {
  const hrefs = await page.locator('a[href]').evaluateAll((anchors) => {
    const values = anchors
      .map(anchor => {
        const element = anchor as HTMLAnchorElement;
        const href = element.getAttribute('href') || '';
        if (!href || href.startsWith('#') || href.startsWith('mailto:') || href.startsWith('tel:') || href.startsWith('javascript:')) {
          return null;
        }

        const url = new URL(href, window.location.origin);
        if (url.origin !== window.location.origin) return null;
        if (url.pathname.startsWith('/api/')) return null;
        if (/\.(svg|png|jpg|jpeg|gif|webp|ico)$/i.test(url.pathname)) return null;

        return `${url.pathname}${url.search}`;
      })
      .filter((href): href is string => !!href);

    return Array.from(new Set(values)).sort();
  });

  return hrefs;
}

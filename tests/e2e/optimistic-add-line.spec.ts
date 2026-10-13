// PoC §8.2 and DEMO-F04: «Add line» paints the line at once, before the server answers; on a done
// item the 409 takes the provisional line back and a toast says why; the server's result keeps only
// the saved lines; repeating a request with the same client_line_id does not duplicate it.
import { type Page, expect, test } from '@playwright/test';

import { A, api, createItem, itemDetail, login, record, shot, uniqueName } from './helpers';

/** Arms in-page probes: click time of «Add line», first/last time a provisional line is on screen. */
async function armProbes(page: Page): Promise<void> {
  await page.evaluate(() => {
    const w = window as unknown as { __t: Record<string, number> };
    w.__t = {};
    document.querySelector('[data-testid=demo-line-add]')?.addEventListener('click', () => (w.__t.click = performance.now()), {
      capture: true,
      once: true,
    });
    const observer = new MutationObserver(() => {
      const pending = document.querySelector('[data-testid=demo-line-pending]');
      if (pending && w.__t.shown === undefined) w.__t.shown = performance.now();
      if (!pending && w.__t.shown !== undefined && w.__t.gone === undefined) {
        w.__t.gone = performance.now();
        observer.disconnect();
      }
    });
    observer.observe(document.body, { subtree: true, childList: true });
  });
}

async function readProbes(page: Page) {
  return page.evaluate(() => {
    const t = (window as unknown as { __t: Record<string, number> }).__t;
    const entry = performance
      .getEntriesByType('resource')
      .filter((e) => e.name.includes('/api/demo/items/add_line'))
      .at(-1) as PerformanceResourceTiming | undefined;
    const r = (v: number | undefined) => (v === undefined ? null : Math.round(v - t.click));
    return {
      clickToShownMs: r(t.shown),
      clickToResponseMs: r(entry?.responseEnd),
      clickToPendingGoneMs: r(t.gone),
    };
  });
}

async function addLine(page: Page, text: string): Promise<void> {
  await page.locator('[data-testid=demo-line-input-text] input').fill(text);
  await armProbes(page);
  await page.locator('[data-testid=demo-line-add]').click();
}

const lineTexts = (page: Page) => page.locator('[data-testid=demo-line-text]').allInnerTexts();

test('add line: optimistic, 409 rollback with toast, server keeps only saved lines, idempotent', async ({ page, context }) => {
  await login(page, A);
  const item = await createItem(context, A, uniqueName('Optimistic'));
  await page.goto(`/demo/items/${item.id}`);
  await expect(page.locator('[data-testid=demo-detail-status]')).toBeVisible();
  await expect(page.locator('[data-testid=demo-lines-empty]')).toBeVisible();

  // 1) Natural speed of the local stack.
  await addLine(page, 'First line');
  await expect(page.locator('[data-testid=demo-line-pending]')).toHaveCount(0);
  await expect(page.locator('[data-testid=demo-line-text]')).toHaveText(['First line']);
  const natural = await readProbes(page);

  // 2) Slow network (the add_line answer held back 800 ms): the line is there long before it.
  await page.route('**/api/demo/items/add_line', async (route) => {
    await new Promise((r) => setTimeout(r, 800));
    await route.continue();
  });
  await addLine(page, 'Second line');
  await expect(page.locator('[data-testid=demo-line-pending]')).toBeVisible();
  await page.screenshot({ path: shot('04-optimistic-pending-line') });
  await expect(page.locator('[data-testid=demo-line-pending]')).toHaveCount(0, { timeout: 5000 });
  const slow = await readProbes(page);
  await page.unroute('**/api/demo/items/add_line');

  // 3) Mark done, then add: 409 → the provisional line goes away and a toast explains it.
  await page.locator('[data-testid=demo-detail-toggle]').click();
  await expect(page.locator('[data-testid=demo-detail-status]')).toHaveText(/Done/);
  const conflict = page.waitForResponse((r) => r.url().includes('/api/demo/items/add_line'));
  await addLine(page, 'Refused line');
  const conflictStatus = (await conflict).status();
  const toast = page.locator('ion-toast');
  await expect(toast).toBeVisible();
  const toastMessage = await toast.evaluate((el) => (el as HTMLElement & { message?: string }).message ?? '');
  await page.screenshot({ path: shot('04-optimistic-409-toast') });
  await expect(page.locator('[data-testid=demo-line-pending]')).toHaveCount(0);
  const rejected = await readProbes(page);
  const shownAfter409 = await lineTexts(page);
  const textBackInField = await page.locator('[data-testid=demo-line-input-text] input').inputValue();
  const server = await itemDetail(context, A, item.id);

  // 4) Idempotency: the same client_line_id twice (reopened item) → one line.
  await api(context, A, 'POST', '/demo/items/update', { id: item.id, status: 'open' });
  const clientLineId = crypto.randomUUID();
  const once = await api(context, A, 'POST', '/demo/items/add_line', { id: item.id, text: 'Retry', qty: '1', client_line_id: clientLineId });
  const twice = await api(context, A, 'POST', '/demo/items/add_line', { id: item.id, text: 'Retry', qty: '1', client_line_id: clientLineId });
  const afterRetry = await itemDetail(context, A, item.id);
  await expect(page.locator('[data-testid=demo-line-text]')).toHaveText(['First line', 'Second line', 'Retry']);

  record('04-optimistic-add-line', {
    natural,
    slowNetwork800ms: slow,
    conflict: { status: conflictStatus, toastMessage, probes: rejected, shownAfter409, textBackInField },
    serverLinesAfter409: server.lines.map((l) => l.text),
    idempotency: {
      firstStatus: once.status,
      secondStatus: twice.status,
      linesWithThatId: afterRetry.lines.filter((l) => l.client_line_id === clientLineId).length,
      totalLines: afterRetry.lines.length,
    },
  });

  expect(natural.clickToShownMs).not.toBeNull();
  expect(natural.clickToShownMs!).toBeLessThan(100);
  expect(slow.clickToShownMs!).toBeLessThan(100);
  expect(slow.clickToShownMs!).toBeLessThan(slow.clickToResponseMs!);
  expect(conflictStatus).toBe(409);
  expect(rejected.clickToShownMs).not.toBeNull();
  expect(toastMessage).toContain('closed');
  expect(shownAfter409).toEqual(['First line', 'Second line']);
  expect(server.lines.map((l) => l.text)).toEqual(['First line', 'Second line']);
  expect(textBackInField).toBe('Refused line');
  expect(once.status).toBe(200);
  expect(twice.status).toBe(200);
  expect(afterRetry.lines.filter((l) => l.client_line_id === clientLineId)).toHaveLength(1);
  expect(afterRetry.lines).toHaveLength(3);
});

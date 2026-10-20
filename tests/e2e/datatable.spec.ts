// The demo list as a server-side DataTable (DEMO-F01/F05 screen, second pass): the search, the page
// and the page size are the server's (the live subscription is reopened with them, never filtered
// in the browser); the columns, the page-size and the column choosers are there by default; the
// list/cards ion-segment switches the view and back; on a phone «Load more» brings the next rows.
import { type BrowserContext, type Page, expect, test } from '@playwright/test';

import { A, api, createItem, decodeSubs, listReady, login, record, rowNames, shot, shown } from './helpers';

const COUNT = 12;
// Rows the search must leave out: «the search really narrowed something» holds on a fresh database
// too, without the rows other specs leave behind.
const OUTSIDE = 2;

type Sub = { op: string; params: Record<string, unknown> };

/** Every `/api/live` the page opens, with its subscriptions decoded. */
function trackSubscriptions(page: Page): Sub[][] {
  const opened: Sub[][] = [];
  page.on('request', (req) => {
    if (req.url().includes('/api/live')) opened.push(decodeSubs(req.url()) as Sub[]);
  });
  return opened;
}

const listParams = (opened: Sub[][]) => opened.at(-1)?.find((s) => s.op === 'demo.item.list')?.params;

async function seed(context: BrowserContext, prefix: string, count = COUNT): Promise<string[]> {
  const names: string[] = [];
  for (let i = 1; i <= count; i += 1) {
    const name = `${prefix} ${String(i).padStart(2, '0')}`;
    await createItem(context, A, name);
    names.push(name);
  }
  return names;
}

async function cleanup(context: BrowserContext, prefix: string): Promise<void> {
  const found = await api<{ rows: { id: string }[] }>(context, A, 'GET', `/demo/items?limit=100&search=${encodeURIComponent(prefix)}`);
  for (const row of found.data.rows) await api(context, A, 'POST', '/demo/items/delete', { id: row.id });
}

const rows = (page: Page) => shown(page).locator('[data-testid=demo-items-row]');

test('server-side search, page size 10 with prev/next, list ⇄ cards segment, columns and choosers by default', async ({ page, context }) => {
  await login(page, A);
  const prefix = `DT${Date.now().toString(36)}`;
  const outside = `DO${Date.now().toString(36)}`;
  try {
    await seed(context, outside, OUTSIDE);
    const names = await seed(context, prefix);
    const opened = trackSubscriptions(page);
    await page.goto('/demo/items');
    await listReady(page);
    const table = shown(page).locator('.data-table');

    // Columns and the two choosers, visible by default (desktop).
    // textContent: the header paints the labels in capitals (CSS), the labels themselves are not.
    const headers = (await table.locator('[role=columnheader]').allTextContents()).map((t) => t.trim());
    const pageSizeSelect = table.locator('ion-select.data-table__page-size-select');
    const columnsSelect = table.locator('ion-select.data-table__columns-select');
    await expect(pageSizeSelect).toBeVisible();
    await expect(columnsSelect).toBeVisible();
    const defaultPageSize = await pageSizeSelect.evaluate((el) => (el as HTMLElement & { value?: unknown }).value);
    const totalAll = (await api<{ total: number }>(context, A, 'GET', '/demo/items?limit=1')).data.total;

    // Search: the subscription is reopened with `search`; only the seeded rows come back.
    await shown(page).locator('[data-testid=demo-items-search] input').fill(prefix);
    await expect.poll(() => listParams(opened)?.search).toBe(prefix);
    await expect(rows(page)).toHaveCount(COUNT);
    const searched = await rowNames(page);
    await page.screenshot({ path: shot('datatable--search') });

    // Page size 10: 10 rows, the subscription asks for limit 10; next → the 2 oldest; prev → back.
    await pageSizeSelect.click();
    await page.locator('ion-popover ion-radio').filter({ hasText: /^\s*10\s*$/ }).click();
    await expect.poll(() => listParams(opened)?.limit).toBe(10);
    await expect(rows(page)).toHaveCount(10);
    const page1 = await rowNames(page);
    const next = shown(page).locator('[data-testid=demo-items-page-next]');
    const prev = shown(page).locator('[data-testid=demo-items-page-prev]');
    await expect(prev).toHaveAttribute('disabled', /.*/);
    await next.click();
    await expect.poll(() => listParams(opened)?.offset).toBe(10);
    await expect(rows(page)).toHaveCount(COUNT - 10);
    const page2 = await rowNames(page);
    const pagerInfo = (await table.locator('.data-table__pager-info').innerText()).trim();
    await page.screenshot({ path: shot('datatable--page-2-of-size-10') });
    await prev.click();
    await expect.poll(() => listParams(opened)?.offset).toBe(0);
    await expect(rows(page)).toHaveCount(10);

    // List → cards → list, with the ion-segment.
    const segment = shown(page).locator('[data-testid=demo-items-view]');
    await shown(page).locator('[data-testid=demo-items-view-cards]').click();
    await expect(segment).toHaveJSProperty('value', 'cards');
    await expect(table.locator('ion-card[data-testid=demo-items-row]')).toHaveCount(10);
    const gridInCards = await table.locator('[role=table]').count();
    await page.screenshot({ path: shot('datatable--cards') });
    await shown(page).locator('[data-testid=demo-items-view-table]').click();
    await expect(segment).toHaveJSProperty('value', 'table');
    await expect(table.locator('[role=table] [data-testid=demo-items-row]')).toHaveCount(10);

    record('datatable', {
      headers,
      defaultPageSize,
      totalAll,
      searchedCount: searched.length,
      subscriptions: opened.map((subs) => subs.map((s) => s.params)),
      page1,
      page2,
      pagerInfo,
      gridInCards,
    });
    expect(headers).toEqual(['Name', 'Status', 'Lines', 'Updated']); // WORKBOOK «Elementos» order
    expect(defaultPageSize).toBe(50);
    expect(totalAll).toBeGreaterThan(COUNT); // the search really narrowed something
    expect([...searched].sort()).toEqual([...names].sort());
    expect(page1).toEqual([...names].reverse().slice(0, 10)); // most recently changed first
    expect(page2).toEqual([...names].reverse().slice(10));
    expect(gridInCards).toBe(0);
  } finally {
    await cleanup(context, prefix);
    await cleanup(context, outside);
  }
});

test('phone: cards by default and «Load more» brings the next rows below the ones shown', async ({ page, context }) => {
  await login(page, A);
  const prefix = `DM${Date.now().toString(36)}`;
  const names = await seed(context, prefix);
  try {
    const opened = trackSubscriptions(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/demo/items');
    await listReady(page);
    const table = shown(page).locator('.data-table');
    await shown(page).locator('[data-testid=demo-items-search] input').fill(prefix);
    await expect(rows(page)).toHaveCount(COUNT);
    const cards = await table.locator('ion-card[data-testid=demo-items-row]').count();
    // The page size is not offered on a phone: 50 per «page», so 12 fit and there is no «Load more».
    const loadMoreWith50 = await shown(page).locator('[data-testid=demo-items-load-more]').count();

    // Back on desktop pick 10 per page, then on the phone «Load more» must add the last 2 below.
    await page.setViewportSize({ width: 1280, height: 860 });
    await table.locator('ion-select.data-table__page-size-select').click();
    await page.locator('ion-popover ion-radio').filter({ hasText: /^\s*10\s*$/ }).click();
    await expect(rows(page)).toHaveCount(10);
    await page.setViewportSize({ width: 390, height: 844 });
    const loadMore = shown(page).locator('[data-testid=demo-items-load-more]');
    await expect(loadMore).toBeVisible();
    await page.screenshot({ path: shot('datatable--phone-load-more') });
    await loadMore.click();
    // One live window from the first row: the subscription asks for 2 pages from offset 0.
    await expect.poll(() => listParams(opened)).toEqual({ search: prefix, limit: 20, offset: 0 });
    await page.waitForTimeout(1500);
    const afterLoadMore = await rowNames(page);
    const loadMoreLeft = await loadMore.count();
    await page.screenshot({ path: shot('datatable--phone-after-load-more') });

    record('datatable-phone', { cards, loadMoreWith50, afterLoadMore, loadMoreLeft, windowParams: listParams(opened) });
    expect(cards).toBe(COUNT);
    expect(loadMoreWith50).toBe(0);
    expect(afterLoadMore, '«Load more» replaced the first 10 rows instead of adding 2 below them').toEqual([...names].reverse());
    expect(loadMoreLeft, 'every row is shown: no «Load more» left').toBe(0);
  } finally {
    await cleanup(context, prefix);
  }
});

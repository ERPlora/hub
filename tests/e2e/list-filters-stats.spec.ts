// The demo list as the WORKBOOK specifies it (DEMO-F05, «Elementos»): the status filter is the
// server's (the live subscription is reopened with `status`, never filtered in the browser), the
// «Updated» column paints exactly what the shared formatter of @erplora/ui gives, and the figures
// «Open», «Done» and «Lines» follow a write made elsewhere in under a second, without reloading.
import { type BrowserContext, type Page, expect, test } from '@playwright/test';

import { formatDateTime } from '../../packages/ui/src/components/format/dateTime';
import { A, api, createItem, decodeSubs, listReady, login, record, rowOf, shot, shown } from './helpers';

type Sub = { op: string; params: Record<string, unknown> };
type Figures = { open: number; done: number; lines: number };

/** Every `/api/live` the page opens, with its subscriptions decoded. */
function trackSubscriptions(page: Page): Sub[][] {
  const opened: Sub[][] = [];
  page.on('request', (req) => {
    if (req.url().includes('/api/live')) opened.push(decodeSubs(req.url()) as Sub[]);
  });
  return opened;
}

const listParams = (opened: Sub[][]) => opened.at(-1)?.find((s) => s.op === 'demo.item.list')?.params;

const rows = (page: Page) => shown(page).locator('[data-testid=demo-items-row]');

/** Whitespace as text: ICU builds differ on the space before «AM» (U+0020 or U+202F). */
const plain = (text: string) => text.replace(/\s+/g, ' ').trim();

async function seed(context: BrowserContext, prefix: string): Promise<{ open: string[]; done: string[] }> {
  const open = [`${prefix} open 1`, `${prefix} open 2`];
  const done = [`${prefix} done 1`, `${prefix} done 2`];
  for (const name of open) await createItem(context, A, name);
  for (const name of done) {
    const item = await createItem(context, A, name);
    const res = await api(context, A, 'POST', '/demo/items/update', { id: item.id, status: 'done' });
    expect(res.status, `mark ${name} done`).toBe(200);
  }
  return { open, done };
}

async function cleanup(context: BrowserContext, prefix: string): Promise<void> {
  const found = await api<{ rows: { id: string }[] }>(context, A, 'GET', `/demo/items?limit=100&search=${encodeURIComponent(prefix)}`);
  for (const row of found.data.rows) await api(context, A, 'POST', '/demo/items/delete', { id: row.id });
}

/** Picks an option of the toolbar status filter through its Ionic popover, and waits until the
 *  popover is gone (a click while it is still dismissing lands on its backdrop and opens nothing). */
async function filterBy(page: Page, label: 'All' | 'Open' | 'Done'): Promise<void> {
  const popover = page.locator('ion-popover');
  await expect(popover).toHaveCount(0);
  await shown(page).locator('[data-testid=demo-items-status-filter]').click({ timeout: 10_000 });
  await popover.locator('ion-radio').filter({ hasText: new RegExp(`^\\s*${label}\\s*$`) }).click({ timeout: 10_000 });
  await expect(popover).toHaveCount(0);
}

/** The figures the page paints (the chips' `data-value`). */
async function shownFigures(page: Page): Promise<Figures> {
  const value = async (name: keyof Figures) =>
    Number(await shown(page).locator(`[data-testid=demo-stats-${name}]`).getAttribute('data-value'));
  return { open: await value('open'), done: await value('done'), lines: await value('lines') };
}

/** In-page probe: the `Date.now()` at which the figures first read `wanted` (see `figuresAt`). */
async function watchFigures(page: Page, wanted: Figures): Promise<void> {
  await page.evaluate((target) => {
    const w = window as unknown as { __figuresAt?: number };
    delete w.__figuresAt;
    const read = (name: string) =>
      Number(document.querySelector(`.ion-page:not(.ion-page-hidden) [data-testid=demo-stats-${name}]`)?.getAttribute('data-value'));
    const check = (): boolean => {
      const ok = read('open') === target.open && read('done') === target.done && read('lines') === target.lines;
      if (ok && w.__figuresAt === undefined) w.__figuresAt = Date.now();
      return ok;
    };
    if (check()) return;
    const observer = new MutationObserver(() => {
      if (check()) observer.disconnect();
    });
    observer.observe(document.body, { subtree: true, attributes: true, attributeFilter: ['data-value'] });
  }, wanted);
}

const figuresAt = (page: Page) => page.evaluate(() => (window as unknown as { __figuresAt?: number }).__figuresAt);

test('status filter on the server and the «Updated» column painted by the shared formatter', async ({ page, context }) => {
  await login(page, A);
  const prefix = `LF${Date.now().toString(36)}`;
  const seeded = await seed(context, prefix);
  try {
    const opened = trackSubscriptions(page);
    await page.goto('/demo/items');
    await listReady(page);
    await shown(page).locator('[data-testid=demo-items-search] input').fill(prefix);
    await expect.poll(() => listParams(opened)?.search).toBe(prefix);
    await expect(rows(page)).toHaveCount(4);

    // «Done»: the subscription is reopened with `status: done`; only the two done items come back.
    await filterBy(page, 'Done');
    await expect.poll(() => listParams(opened)).toEqual({ search: prefix, status: 'done', limit: 50, offset: 0 });
    await expect(rows(page)).toHaveCount(2);
    const doneNames = await shown(page).locator('[data-testid=demo-item-name]').allInnerTexts();
    const doneBadges = await shown(page).locator('[data-testid=demo-item-status]').allInnerTexts();
    await page.screenshot({ path: shot('list-filters--done') });

    // «Open» and back to «All» (no `status` at all).
    await filterBy(page, 'Open');
    await expect.poll(() => listParams(opened)?.status).toBe('open');
    await expect(rows(page)).toHaveCount(2);
    const openNames = await shown(page).locator('[data-testid=demo-item-name]').allInnerTexts();
    await filterBy(page, 'All');
    await expect.poll(() => listParams(opened)).toEqual({ search: prefix, limit: 50, offset: 0 });
    await expect(rows(page)).toHaveCount(4);

    // «Updated»: the header, and every cell is the shared formatter's text for the server's value,
    // in the page's language and the browser's time zone.
    const headers = (await shown(page).locator('.data-table [role=columnheader]').allTextContents()).map((t) => t.trim());
    const lang = await page.evaluate(() => document.documentElement.lang);
    const listed = await api<{ rows: { id: string; updated_at: string }[] }>(
      context,
      A,
      'GET',
      `/demo/items?limit=100&search=${encodeURIComponent(prefix)}`,
    );
    const cells: { shown: string; expected: string }[] = [];
    for (const item of listed.data.rows) {
      const cell = rowOf(page, item.id).locator('[data-testid=demo-item-updated]');
      cells.push({ shown: plain(await cell.innerText()), expected: plain(formatDateTime(item.updated_at, lang)) });
    }
    await page.screenshot({ path: shot('list-filters--updated-column') });

    record('list-filters', { subscriptions: opened.map((subs) => subs.map((s) => s.params)), doneNames, doneBadges, openNames, headers, lang, cells });
    expect([...doneNames].sort()).toEqual([...seeded.done].sort());
    expect(doneBadges).toEqual(['Done', 'Done']);
    expect([...openNames].sort()).toEqual([...seeded.open].sort());
    expect(headers).toContain('Updated');
    expect(cells).toHaveLength(4);
    for (const cell of cells) {
      expect(cell.shown).not.toBe('');
      expect(cell.shown).toBe(cell.expected);
    }
  } finally {
    await cleanup(context, prefix);
  }
});

test('the figures follow a write made elsewhere in under a second, without reloading', async ({ page, context }) => {
  await login(page, A);
  const prefix = `LS${Date.now().toString(36)}`;
  try {
    await page.goto('/demo/items');
    await listReady(page);
    const stats = shown(page).locator('[data-testid=demo-stats]');
    await expect(stats).toHaveAttribute('aria-busy', 'false');
    const server = (await api<Figures>(context, A, 'GET', '/demo/items/stats')).data;
    const before = await shownFigures(page);
    await page.screenshot({ path: shot('list-stats--before') });
    const navigations: string[] = [];
    page.on('framenavigated', (frame) => {
      if (frame === page.mainFrame()) navigations.push(frame.url());
    });

    // Another tablet (the API, same business) creates an item: «Open» goes up by one. Each delay runs
    // from the start of the write to the moment the page painted the new figures (in-page probe).
    const afterCreate = { ...before, open: before.open + 1 };
    await watchFigures(page, afterCreate);
    const createdAt = Date.now();
    const item = await createItem(context, A, `${prefix} stats`);
    await expect.poll(() => shownFigures(page)).toEqual(afterCreate);
    const createDelay = Number(await figuresAt(page)) - createdAt;

    // It adds a line: «Lines» goes up by one.
    const afterLine = { ...afterCreate, lines: afterCreate.lines + 1 };
    await watchFigures(page, afterLine);
    const lineAt = Date.now();
    const line = await api(context, A, 'POST', '/demo/items/add_line', { id: item.id, text: 'Coffee', qty: '1' });
    expect(line.status).toBe(200);
    await expect.poll(() => shownFigures(page)).toEqual(afterLine);
    const lineDelay = Number(await figuresAt(page)) - lineAt;

    // It closes the item: one fewer «Open», one more «Done».
    const afterDone = { ...afterLine, open: afterLine.open - 1, done: afterLine.done + 1 };
    await watchFigures(page, afterDone);
    const doneAt = Date.now();
    const done = await api(context, A, 'POST', '/demo/items/update', { id: item.id, status: 'done' });
    expect(done.status).toBe(200);
    await expect.poll(() => shownFigures(page)).toEqual(afterDone);
    const doneDelay = Number(await figuresAt(page)) - doneAt;
    await page.screenshot({ path: shot('list-stats--after') });

    record('list-stats', { server, before, afterCreate, afterLine, afterDone, createDelay, lineDelay, doneDelay, navigations });
    expect(before).toEqual({ open: server.open, done: server.done, lines: server.lines });
    expect(navigations, 'no reload').toEqual([]);
    for (const delay of [createDelay, lineDelay, doneDelay]) expect(delay).toBeLessThan(1000);
  } finally {
    await cleanup(context, prefix);
  }
});

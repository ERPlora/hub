// PoC §8.5 (second half): changing a `.vue` hot-swaps the module without a reload and without
// losing the live stream; changing a `.py` restarts Django and the page's stream reconnects alone.
// Every file touched is restored byte for byte.
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { type BrowserContext, type Page, expect, test } from '@playwright/test';

import { A, createItem, HUB_DIR, healthy, listReady, login, record, row, shot, shown, uniqueName, waitFor } from './helpers';
import { STACK } from './stack';

const VUE = join(HUB_DIR, 'apps/demo/frontend/pages/ItemListPage.vue');
const PY = join(HUB_DIR, 'apps/demo/queries.py');
const ROOT_TAG = `<AppPage :title="$t('demo.items.title')">`;

type LiveLog = { at: number; status?: number }[];

function trackLive(page: Page): LiveLog {
  const log: LiveLog = [];
  page.on('request', (req) => {
    if (req.url().includes('/api/live')) log.push({ at: Date.now() });
  });
  page.on('response', (res) => {
    if (!res.url().includes('/api/live')) return;
    const entry = log.findLast((r) => r.status === undefined);
    if (entry) entry.status = res.status();
  });
  return log;
}

async function openList(page: Page): Promise<number> {
  await login(page, A);
  await listReady(page);
  await page.evaluate(() => ((window as unknown as { __doc: string }).__doc = 'original'));
  return page.evaluate(() => performance.getEntriesByType('navigation').length);
}

const sameDocument = async (page: Page) =>
  (await page.evaluate(() => (window as unknown as { __doc?: string }).__doc)) === 'original';

/** Adds and removes a comment in `queries.py` (StatReloader restarts Django) and waits for the stream. */
async function touchPython(page: Page, context: BrowserContext, log: LiveLog, label: string) {
  const original = readFileSync(PY, 'utf8');
  const from = log.length;
  const t0 = Date.now();
  try {
    writeFileSync(PY, `${original}# e2e: touch to restart runserver\n`);
    await page.waitForTimeout(300);
  } finally {
    writeFileSync(PY, original);
  }
  expect(readFileSync(PY, 'utf8')).toBe(original);
  await waitFor(() => log.slice(from).some((r) => r.status === 200), 60_000);
  const reconnectedInMs = Date.now() - t0;
  await waitFor(healthy, 30_000);
  await expect(shown(page).locator('[data-testid=demo-items-reconnecting]')).toBeHidden({ timeout: 30_000 });
  const name = uniqueName(`After py ${label}`);
  await createItem(context, A, name);
  await expect(row(page, name)).toBeVisible({ timeout: 5000 });
  await page.screenshot({ path: shot(`07-after-py-restart-${label}`) });
  return {
    reconnectedInMs,
    sameDocument: await sameDocument(page),
    streamAttempts: log.slice(from).map((r) => ({ t: r.at - t0, status: r.status ?? null })),
  };
}

test('.vue edit → HMR applies without reload and without reopening the stream', async ({ page, context }) => {
  const log = trackLive(page);
  const navEntries = await openList(page);
  const original = readFileSync(VUE, 'utf8');
  expect(original).toContain(ROOT_TAG);
  const from = log.length;
  let inMs = NaN;
  let outMs = NaN;
  try {
    const t0 = Date.now();
    writeFileSync(VUE, original.replace(ROOT_TAG, `<AppPage :title="$t('demo.items.title')" data-hmr="1">`));
    await expect(page.locator('[data-hmr="1"]')).toHaveCount(1, { timeout: 15_000 });
    inMs = Date.now() - t0;
    await page.screenshot({ path: shot('07-hmr-applied') });
  } finally {
    const t1 = Date.now();
    writeFileSync(VUE, original);
    await expect(page.locator('[data-hmr="1"]')).toHaveCount(0, { timeout: 15_000 });
    outMs = Date.now() - t1;
  }
  expect(readFileSync(VUE, 'utf8')).toBe(original);
  await page.waitForTimeout(1000);
  const name = uniqueName('After HMR');
  await createItem(context, A, name);
  await expect(row(page, name)).toBeVisible({ timeout: 5000 });
  const result = {
    hmrInMs: inMs,
    hmrOutMs: outMs,
    sameDocument: await sameDocument(page),
    navigationEntries: await page.evaluate(() => performance.getEntriesByType('navigation').length),
    streamsOpenedDuringHmr: log.length - from,
  };
  record('07-hmr-vue', result);
  expect(result.sameDocument).toBe(true);
  expect(result.navigationEntries).toBe(navEntries);
  expect(result.streamsOpenedDuringHmr).toBe(0);
});

test('.py edit → Django restarts and the page recovers by itself, without a full reload', async ({ page, context }) => {
  const log = trackLive(page);
  await openList(page);
  const result = await touchPython(page, context, log, 'plain');
  record('07-hmr-py-plain', result);
  // §8.5: «cambiar un .py → reinicio y reconexión sola». A reload would drop unsaved input.
  expect(result.sameDocument, 'the page was fully reloaded (Vite «page reload apps/demo/queries.py»)').toBe(true);
});

test('.py edit with Vite full-reloads filtered out → the SDK alone reconnects the stream', async ({ page, context }) => {
  const dropped: string[] = [];
  await context.routeWebSocket(new RegExp(`localhost:${STACK.vitePort}`), (ws) => {
    const server = ws.connectToServer();
    ws.onMessage((message) => server.send(message));
    server.onMessage((message) => {
      if (typeof message === 'string' && message.includes('"full-reload"')) dropped.push(message.slice(0, 120));
      else ws.send(message);
    });
  });
  const log = trackLive(page);
  await openList(page);
  const result = await touchPython(page, context, log, 'filtered');
  record('07-hmr-py-filtered', { ...result, droppedViteMessages: dropped });
  expect(result.sameDocument).toBe(true);
  expect(result.streamAttempts.filter((r) => r.status === 200)).toHaveLength(1);
});

// PoC §8.5 (first half): runserver dies for 10 s with a list open. The page shows «Reconnecting…»,
// reopens ONE stream with the same subscriptions once the server is back, and paints an item created
// meanwhile from another tab, without a reload and without duplicate rows.
//
// Killing runserver also kills its Vite (dev only), and Vite's HMR client reloads the page when its
// socket comes back. That reload is not what is under test (production has no Vite), so the HMR
// socket is routed and kept open from the page's side: only the live stream sees the outage.
import { expect, test } from '@playwright/test';

import {
  A,
  createViaPage,
  decodeSubs,
  healthy,
  listeningPids,
  listReady,
  login,
  record,
  row,
  rowNames,
  shot,
  shown,
  startRunserver,
  uniqueName,
  viteReady,
  waitFor,
} from './helpers';
import { STACK } from './stack';

const DOWN_MS = 10_000;

test('runserver down 10 s → «Reconnecting…», one reconnection, same subscriptions, new item shows', async ({ context }) => {
  await context.routeWebSocket(new RegExp(`localhost:${STACK.vitePort}`), (ws) => {
    const server = ws.connectToServer();
    server.onClose(() => {
      // keep the page's side open: no "server connection lost" → no location.reload()
    });
  });
  const page = await context.newPage();
  const liveRequests: { at: number; url: string; status?: number; failed?: string }[] = [];
  page.on('request', (req) => {
    if (req.url().includes('/api/live')) liveRequests.push({ at: Date.now(), url: req.url() });
  });
  page.on('response', (res) => {
    const entry = liveRequests.findLast((r) => r.url === res.url() && r.status === undefined);
    if (res.url().includes('/api/live') && entry) entry.status = res.status();
  });
  page.on('requestfailed', (req) => {
    const entry = liveRequests.findLast((r) => r.url === req.url() && r.failed === undefined && r.status === undefined);
    if (req.url().includes('/api/live') && entry) entry.failed = req.failure()?.errorText ?? 'failed';
  });
  await login(page, A);
  await listReady(page);
  await page.evaluate(() => ((window as unknown as { __doc: string }).__doc = 'original'));
  const openBefore = liveRequests.filter((r) => r.status === 200);
  expect(openBefore.length).toBeGreaterThan(0);
  const subsBefore = openBefore.at(-1)!.url;
  const firstAfterKill = liveRequests.length;

  // Kill the process listening on runserver's port (the autoreloader's child); its parent exits and
  // stops Vite.
  const pids = listeningPids(STACK.hubPort);
  expect(pids.length).toBeGreaterThan(0);
  const killedAt = Date.now();
  for (const pid of pids) process.kill(pid, 'SIGTERM');
  const chip = shown(page).locator('[data-testid=demo-items-reconnecting]');
  await expect(chip).toBeVisible({ timeout: 15_000 });
  const chipAfterMs = Date.now() - killedAt;
  await page.screenshot({ path: shot('06-reconnecting-chip') });

  await page.waitForTimeout(Math.max(0, DOWN_MS - (Date.now() - killedAt)));
  await waitFor(() => listeningPids(STACK.vitePort).length === 0, 10_000); // the old Vite is gone
  const restartAt = Date.now();
  startRunserver();
  const bootMs = await waitFor(healthy, 60_000);
  const requestsBeforeHealthy = liveRequests.length - firstAfterKill;
  await waitFor(viteReady, 60_000); // the new tab's HTML loads its modules from Vite

  // Another tab creates an item while the first one is (still) reconnecting.
  const other = await context.newPage();
  await other.goto('/demo/items');
  await listReady(other);
  const name = uniqueName('After restart');
  await createViaPage(other, name);

  await expect(chip).toBeHidden({ timeout: 60_000 });
  const liveAgainAfterHealthyMs = Date.now() - restartAt - bootMs;
  await expect(row(page, name)).toBeVisible({ timeout: 10_000 });
  await page.waitForTimeout(1500); // anything late (a second stream, a duplicate row) shows up now
  await page.screenshot({ path: shot('06-recovered-with-new-item') });

  const names = await rowNames(page);
  const sameDocument = (await page.evaluate(() => (window as unknown as { __doc?: string }).__doc)) === 'original';
  const afterKill = liveRequests.slice(firstAfterKill);
  const ok = afterKill.filter((r) => r.status === 200);
  record('06-reconnect', {
    downMs: DOWN_MS,
    killedPids: pids,
    chipVisibleAfterMs: chipAfterMs,
    runserverBootMs: bootMs,
    liveAgainAfterHealthyMs,
    attemptsWhileDown: requestsBeforeHealthy,
    liveRequests: afterKill.map((r) => ({ t: r.at - killedAt, status: r.status ?? null, failed: r.failed ?? null })),
    successfulReconnections: ok.length,
    subscriptionsBefore: decodeSubs(subsBefore),
    subscriptionsAfter: ok.map((r) => decodeSubs(r.url)),
    duplicateRows: names.length - new Set(names).size,
    newItemRows: names.filter((n) => n === name).length,
    sameDocument,
  });

  expect(sameDocument).toBe(true);
  expect(ok).toHaveLength(1);
  expect(decodeSubs(ok[0].url)).toEqual(decodeSubs(subsBefore));
  expect(names.filter((n) => n === name)).toHaveLength(1);
  expect(names.length).toBe(new Set(names).size);
});

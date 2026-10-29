// flow: PRINTING-F01 PRINTING-F18
// The bell with the device off (FIX-HUB-PRINTING-BELL-SILENT-WITH-DEVICE-OFF; the old hub's print_hosts::is_undrained
// and its bell row, old-hub:HUB_SHELL-F63): a device set up for the receipt printer that gave no news for 90 s is off,
// and a receipt that has waited a minute on it rings «Nadie está imprimiendo «Recibo» (N)» for the owner of hub `a`,
// in Spanish, with no event and no reload: the bell reads its rows again by the clock (`bell_refresh_every`, 30 s).
// Its row leads to Printing → Printers, whose receipts' card says «Dispositivo apagado» and what to do. With Printers
// open, the device comes back (its hello on /ws/print, the presence Printing declares): the bell quiets and the card says
// «Listo» by themselves; it goes quiet again and both say so again, with no event and no reload (the card reads the
// summary every 30 s while something waits). The minute and the 90 s are not waited for: `psql()` moves the receipt and
// the device's last news back. In each of the three sizes,
// leaving the capture `FIX-HUB-PRINTING-BELL-SILENT-WITH-DEVICE-OFF-<width>` with the bell open. What it makes is
// «e2e Off …», deleted before and after.
import { type Browser, type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, bellBadge, horizontalOverflow, login, openBell, psql, shot, shown, untilStill } from './helpers';
import { FLOW_VIEWPORTS, forgetDevices } from './printing-helpers';
import { stamp } from './sale-helpers';

test.describe.configure({ mode: 'serial' });

const KEY = 'FIX-HUB-PRINTING-BELL-SILENT-WITH-DEVICE-OFF';
const ROW = 'printing.stalled_receipt';
const TAG = 'e2e Off';
const RUN = stamp();
/** The bell's own reading of its rows, which Printing's clock makes it do. */
const READ_AGAIN = '/api/home/bell';
/** The receipts' card's own reading of the summary by the clock, while something waits. */
const CARD_READ = '/api/printing/jobs/summary';
/** Longer than the bell's period (30 s) and a read: what the bell takes to notice by itself. */
const BY_THE_CLOCK = { timeout: 45_000 };

function cleanUp(): void {
  psql(`delete from printing_printjob where printer_id in (select id from printing_printer where name like '${TAG} %')`);
  forgetDevices(`${TAG} %`, { names: [`${TAG} %`] });
  psql(`delete from printing_printer where name like '${TAG} %'`);
}

/** The receipt printer of this run. */
let printer = '';

test.beforeAll(async ({ browser }) => {
  cleanUp();
  const context = await browser.newContext({ baseURL: A });
  try {
    await login(await context.newPage(), A, '/printing/printers');
    const created = await api<{ id: string }>(context, A, 'POST', '/printing/printers', {
      name: `${TAG} Till ${RUN}`,
      kind: 'network',
      address: '10.0.0.78',
      usage: 'receipt',
    });
    expect(created.status, JSON.stringify(created.data)).toBe(201);
    printer = created.data.id;
  } finally {
    await context.close();
  }
});

test.afterAll(() => cleanUp());

interface Counter {
  key: string;
  count: number;
}

/** What the bell counts now, as the server says (`base.bell.counters`). */
async function counters(context: BrowserContext): Promise<{ total: number; stalled: number; every: number | null }> {
  const res = await api<{ counters: Counter[]; refresh_every: number | null }>(context, A, 'GET', '/home/bell');
  expect(res.status).toBe(200);
  const total = res.data.counters.reduce((sum, counter) => sum + counter.count, 0);
  const stalled = res.data.counters.find((counter) => counter.key === ROW)?.count ?? 0;
  return { total, stalled, every: res.data.refresh_every };
}

/** Sets up the device `device` with this run's printer, from the device (its `X-Device-Id`), as Devices does. */
async function setUpDevice(context: BrowserContext, device: string): Promise<void> {
  const host = new URL(A).hostname;
  const csrf = (await context.cookies(A)).find((c) => c.name === 'csrftoken' && c.domain === host)?.value ?? '';
  const res = await context.request.post(`${A}/api/printing/devices`, {
    headers: { 'X-CSRFToken': csrf, Accept: 'application/json', 'X-Device-Id': device },
    data: { name: `${TAG} Counter ${RUN}`, printers: [printer] },
  });
  expect(res.status(), await res.text()).toBe(201);
}

/** The device and the receipt as if it went quiet and the receipt was queued `minutes` ago. */
function wentOff(device: string, job: string, minutes = 2): void {
  psql(`update printing_printdevice set last_seen_at = now() - interval '${minutes} minutes' where key = encode(sha256('${device}'::bytea), 'hex')`);
  psql(`update printing_printjob set created_at = now() - interval '${minutes} minutes' where id = '${job}'`);
}

/** The device's print host connects from `page` the way the app does (/ws/print, `hello`): it is there again. */
async function comesBack(page: Page, device: string): Promise<void> {
  const ready = await page.evaluate(
    ([deviceId, printerId]) =>
      new Promise<string>((resolve, reject) => {
        const socket = new WebSocket(`${location.origin.replace(/^http/, 'ws')}/ws/print`);
        (window as unknown as { printSocket: WebSocket }).printSocket = socket;
        socket.onopen = () => socket.send(JSON.stringify({ type: 'hello', session: '', deviceId, printers: [printerId] }));
        socket.onmessage = (event) => resolve((JSON.parse(event.data as string) as { type: string }).type);
        socket.onerror = () => reject(new Error('the print socket failed'));
      }),
    [device, printer],
  );
  expect(ready).toBe('ready');
}

/**
 * The owner on `a` in Spanish, signed in; `ready` runs before the Home is read again (what it changes has told its
 * events by then), and then every `/api/live`, every bell read and every page load is noted.
 */
async function spanishOwner(browser: Browser, viewport: { width: number; height: number }, ready: (context: BrowserContext) => Promise<void>) {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'es-ES' });
  const page = await context.newPage();
  await login(page, A, '/');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  await ready(context);
  const streams: number[] = [];
  const reads: number[] = [];
  const loads: number[] = [];
  const cardReads: number[] = [];
  page.on('load', () => loads.push(Date.now()));
  page.on('request', (request) => {
    const path = new URL(request.url()).pathname;
    if (path === '/api/live') streams.push(Date.now());
    if (path === READ_AGAIN) reads.push(Date.now());
    if (path === CARD_READ) cardReads.push(Date.now());
  });
  await page.goto(`${A}/`);
  await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
  await expect(shown(page).locator('[data-testid="home-my-apps"]')).toBeVisible();
  return { context, page, streams, reads, loads, cardReads };
}

/** Waits until the page has opened no `/api/live` for a second: every subscription of the screen is declared. */
async function settled(streams: number[]): Promise<void> {
  await expect.poll(() => Date.now() - (streams.at(-1) ?? 0), { timeout: 15_000 }).toBeGreaterThan(1_000);
}

async function badgeSays(page: Page, total: number, options = {}): Promise<void> {
  if (total > 0) await expect(bellBadge(page)).toHaveText(String(total), options);
  else await expect(bellBadge(page)).toHaveCount(0, options);
}

FLOW_VIEWPORTS.forEach(({ label, width, height }) => {
  test(`${KEY} PRINTING-F01 «Nadie está imprimiendo «Recibo»» with the device off, by the clock — ${label}`, async ({ browser }) => {
    const device = `${TAG} device ${RUN} ${label}`;
    let job = '';
    // The device set up from itself is there; a receipt queued on its printer is its: nothing rings.
    const { context, page, streams, reads, loads, cardReads } = await spanishOwner(browser, { width, height }, async (context) => {
      await setUpDevice(context, device);
      const queued = await api<{ job: { id: string } }>(context, A, 'POST', '/printing/jobs', {
        document_type: 'receipt',
        document: { business_name: 'e2e', receipt_id: `T-${RUN}`, items: [{ name: 'Haircut', quantity: 1, total: 18 }], total: 18 },
        job_key: `${TAG} ${RUN} ${label}`,
        printer,
      });
      expect(queued.status, JSON.stringify(queued.data)).toBe(201);
      job = queued.data.job.id;
    });
    try {
      const before = await counters(context);
      expect(before.every, 'Printing asks the bell to read the clock').toBe(30);
      await badgeSays(page, before.total);
      await settled(streams);
      const onTheHome = loads.length;

      // The till went quiet 2 min ago and the receipt has waited as long: no event says so, the clock does.
      wentOff(device, job);
      const readsBefore = reads.length;
      await badgeSays(page, before.total + 1, BY_THE_CLOCK);
      // Any live result re-runs the rows too (the SaaS's picture after a sign-in, another app's write): what proves
      // the bell needs none is that it reads them by itself.
      await expect.poll(() => reads.length, { ...BY_THE_CLOCK, message: 'the bell reads its rows again by itself' }).toBeGreaterThan(readsBefore);
      expect(loads.length, 'without a reload').toBe(onTheHome);
      expect((await counters(context)).stalled).toBe(before.stalled + 1);

      // The capture: the Home with the bell open, the row naming the function as Printing does.
      await openBell(page);
      const row = page.locator('ion-popover [data-testid="hub-bell-row"]', { hasText: /^\s*Nadie está imprimiendo «Recibo» \(\d+\)\s*$/ });
      await expect(row).toHaveText(`Nadie está imprimiendo «Recibo» (${before.stalled + 1})`);
      await untilStill(page);
      const overflow = await horizontalOverflow(page);
      expect(overflow, `no sideways scroll at ${label}`).toBeLessThanOrEqual(0);
      await page.screenshot({ path: shot(`${KEY}-${label}`) });

      // The row leads to the printers, where the receipts' card says the device is off and what to do.
      await row.click();
      await expect(page).toHaveURL(`${A}/printing/printers`);
      const card = shown(page).locator('[data-testid=printing-summary-card-receipt]');
      await expect(card).toContainText('Dispositivo apagado');
      await expect(shown(page).locator('[data-testid=printing-summary-device-off-receipt]')).toHaveText(
        'El dispositivo que lo imprime no responde: enciéndelo y abre en él la app de ERPlora.',
      );
      await expect(shown(page).locator('[data-testid=printing-summary-no-device-receipt]')).toHaveCount(0);

      // With Printers open, the device comes back (its hello, which tells no event): the bell quiets and the card says
      // «Listo» by themselves, by the clock.
      await settled(streams);
      const onThePrinters = loads.length;
      await comesBack(page, device);
      const readsBack = reads.length;
      const cardReadsBack = cardReads.length;
      await badgeSays(page, before.total, BY_THE_CLOCK);
      await expect(card).toContainText('Listo', BY_THE_CLOCK);
      await expect(shown(page).locator('[data-testid=printing-summary-device-off-receipt]')).toHaveCount(0);
      await expect.poll(() => reads.length, { ...BY_THE_CLOCK, message: 'the bell reads its rows again by itself' }).toBeGreaterThan(readsBack);
      expect(cardReads.length, 'the card read the summary again by itself').toBeGreaterThan(cardReadsBack);
      expect((await counters(context)).stalled).toBe(before.stalled);

      // It goes quiet again (no news for 2 min): still on Printers, the card and the bell say so, with no event.
      wentOff(device, job);
      const cardReadsOff = cardReads.length;
      await expect(card).toContainText('Dispositivo apagado', BY_THE_CLOCK);
      await expect(shown(page).locator('[data-testid=printing-summary-device-off-receipt]')).toBeVisible();
      await badgeSays(page, before.total + 1, BY_THE_CLOCK);
      expect(cardReads.length, 'the card read the summary again by itself').toBeGreaterThan(cardReadsOff);
      expect(loads.length, 'without a reload').toBe(onThePrinters);
    } finally {
      await page.evaluate(() => (window as unknown as { printSocket?: WebSocket }).printSocket?.close()).catch(() => undefined);
      await context.close();
      psql(`delete from printing_printjob where printer_id = '${printer}'`);
      forgetDevices(`${TAG} %`, { ids: [device] });
    }
  });
});

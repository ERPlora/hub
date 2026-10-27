// flow: PRINTING-F01
// Printing's hooks of the Home (FIX-PRINTING-SETUP-HOOKS; the old hub's core item «Configura la impresora» and its bell
// row «Nadie está imprimiendo «…»», old-hub:HUB_SHELL-F63; docs/reference/old-hub/dashboard-*.png), as the owner of hub
// `a` reads them in Spanish: «Configura la impresora» pending and «Recomendado» in «Termina de configurar tu negocio»
// while no device set up prints the receipts, its «Configurar» leading to Printing → Devices; a receipt queued on a
// receipt printer no device reaches rings the bell without a reload, its row «Nadie está imprimiendo «Recibo» (N)»
// leads to Printing → Printers, whose receipts' card says «Sin dispositivo» and where to set one up; the device set up
// from it quiets the bell and the card and ticks the step, live; retired, the step is pending again. In each of the three sizes, leaving the capture `FIX-PRINTING-SETUP-HOOKS-<width>` with the bell
// open. What it makes is «e2e Hooks …», deleted before and after; the devices set up before it are parked (retired)
// for the run and put back after it.
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, bellBadge, login, openBell, psql, shot, shown, untilStill } from './helpers';
import { FLOW_VIEWPORTS, forgetDevices } from './printing-helpers';
import { stamp } from './sale-helpers';

test.describe.configure({ mode: 'serial' });

const KEY = 'FIX-PRINTING-SETUP-HOOKS';
const STEP = 'printing.printer';
const ROW = 'printing.stalled_receipt';
const TAG = 'e2e Hooks';
const RUN = stamp();
/** The devices set up before this file: retired with this mark for the run, back after it. */
const PARKED = 'e2e-fix-printing-hooks-parked';

function cleanUp(): void {
  psql(`delete from printing_printjob where printer_id in (select id from printing_printer where name like '${TAG} %')`);
  forgetDevices(`${TAG} %`, { names: [`${TAG} %`] });
  psql(`delete from printing_printer where name like '${TAG} %'`);
}

/** The receipt printer of this run: a network one no device reaches yet. */
let printer = '';

test.beforeAll(async ({ browser }) => {
  cleanUp();
  psql(`update printing_printdevice set retired_at = now(), retired_by = '${PARKED}' where retired_at is null`);
  const context = await browser.newContext({ baseURL: A });
  try {
    await login(await context.newPage(), A, '/printing/printers');
    const created = await api<{ id: string }>(context, A, 'POST', '/printing/printers', {
      name: `${TAG} Till ${RUN}`,
      kind: 'network',
      address: '10.0.0.77',
      usage: 'receipt',
    });
    expect(created.status, JSON.stringify(created.data)).toBe(201);
    printer = created.data.id;
  } finally {
    await context.close();
  }
});

test.afterAll(() => {
  try {
    cleanUp();
  } finally {
    psql(`update printing_printdevice set retired_at = null, retired_by = '' where retired_by = '${PARKED}'`);
  }
});

interface Counter {
  key: string;
  count: number;
}

/** What the bell counts now, as the server says (`base.bell.counters`). */
async function counters(context: BrowserContext): Promise<{ total: number; stalled: number }> {
  const res = await api<{ counters: Counter[] }>(context, A, 'GET', '/home/bell');
  expect(res.status).toBe(200);
  const total = res.data.counters.reduce((sum, counter) => sum + counter.count, 0);
  const stalled = res.data.counters.find((counter) => counter.key === ROW)?.count ?? 0;
  return { total, stalled };
}

/** Sets up the device `device` with this run's printer, from the device (its `X-Device-Id`), as Devices does. */
async function setUpDevice(context: BrowserContext, device: string): Promise<string> {
  const host = new URL(A).hostname;
  const csrf = (await context.cookies(A)).find((c) => c.name === 'csrftoken' && c.domain === host)?.value ?? '';
  const res = await context.request.post(`${A}/api/printing/devices`, {
    headers: { 'X-CSRFToken': csrf, Accept: 'application/json', 'X-Device-Id': device },
    data: { name: `${TAG} Counter ${RUN}`, printers: [printer] },
  });
  expect(res.status(), await res.text()).toBe(201);
  return ((await res.json()) as { id: string }).id;
}

/**
 * The owner on `a` in Spanish, on the Home, with the instant of every `/api/live` the page opens: a new stream brings
 * every result again, so a count that changes without one came over the stream already open, re-run by its events.
 */
async function spanishOwner(browser: Browser, viewport: { width: number; height: number }) {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'es-ES' });
  const page = await context.newPage();
  const streams: number[] = [];
  page.on('request', (request) => {
    if (request.url().includes('/api/live')) streams.push(Date.now());
  });
  await login(page, A, '/');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}/`);
  await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
  await expect(shown(page).locator('[data-testid="home-my-apps"]')).toBeVisible();
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  return { context, page, streams };
}

/** Waits until the page has opened no `/api/live` for a second: every subscription of the screen is declared. */
async function settled(streams: number[]): Promise<void> {
  await expect.poll(() => Date.now() - (streams.at(-1) ?? 0), { timeout: 15_000 }).toBeGreaterThan(1_000);
}

const card = (page: Page): Locator => shown(page).locator('[data-testid="setup-card"]');
const step = (page: Page): Locator => card(page).locator(`[data-testid="setup-row"][data-key="${STEP}"]`);
const pill = (page: Page): Locator => step(page).locator('[data-testid="setup-pill"]');
const stalledRow = (page: Page): Locator =>
  page.locator('ion-popover [data-testid="hub-bell-row"]', { hasText: /^\s*Nadie está imprimiendo «Recibo» \(\d+\)\s*$/ });

/** «Ver todo»: a «Recomendado» step is folded while more important ones are pending (two rows on a phone). */
async function unfolded(page: Page): Promise<void> {
  await expect(card(page)).toHaveAttribute('aria-busy', 'false');
  const toggle = card(page).locator('[data-testid="setup-toggle"]');
  if ((await toggle.count()) && (await toggle.textContent())?.trim() === 'Ver todo') await toggle.click();
  await expect(step(page)).toBeVisible();
}

async function badgeSays(page: Page, total: number): Promise<void> {
  if (total > 0) await expect(bellBadge(page)).toHaveText(String(total));
  else await expect(bellBadge(page)).toHaveCount(0);
}

FLOW_VIEWPORTS.forEach(({ label, width, height }) => {
  test(`${KEY} PRINTING-F01 «Configura la impresora» and «Nadie está imprimiendo «Recibo»» on the Home, live — ${label}`, async ({
    browser,
  }) => {
    const { context, page, streams } = await spanishOwner(browser, { width, height });
    const device = `${TAG} device ${RUN} ${label}`;
    let deviceId = '';
    try {
      // The step, as the old core item said it, pending while no device set up prints the receipts.
      await unfolded(page);
      await expect(step(page).locator('.setup-row-title')).toHaveText('Configura la impresora');
      await expect(step(page).locator('.setup-row-desc')).toHaveText(
        'Da de alta el dispositivo que imprime los tiques de tus clientes, para que la primera venta salga en papel.',
      );
      await expect(pill(page)).toHaveText('Recomendado');
      // «Configurar» leads to where the device is set up.
      await step(page).locator(`[data-testid="setup-configure-${STEP}"]`).click();
      await expect(page).toHaveURL(`${A}/printing/devices`);
      await expect(shown(page).locator('[data-testid=printing-devices-this]')).toBeVisible();
      await page.goBack();
      await expect(page).toHaveURL(`${A}/`);
      await unfolded(page);

      // The Home as it is read: its stream settled before anything changes the bell.
      await settled(streams);
      const before = await counters(context);
      await badgeSays(page, before.total);
      const onTheHome = streams.length;

      // A receipt queued on the till no device reaches: the bell rings without a reload, over the open stream.
      const queued = await api<{ job: { id: string } }>(context, A, 'POST', '/printing/jobs', {
        document_type: 'receipt',
        document: { business_name: 'e2e', receipt_id: `T-${RUN}`, items: [{ name: 'Haircut', quantity: 1, total: 18 }], total: 18 },
        job_key: `${TAG} ${RUN} ${label}`,
        printer,
      });
      expect(queued.status, JSON.stringify(queued.data)).toBe(201);
      await badgeSays(page, before.total + 1);
      expect(streams.length, 'the queued receipt reached the bell without a new /api/live').toBe(onTheHome);

      // The capture: the Home with the bell open, the row naming the function as Printing does.
      await openBell(page);
      const row = stalledRow(page);
      await expect(row).toHaveText(`Nadie está imprimiendo «Recibo» (${before.stalled + 1})`);
      await untilStill(page);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow, `no sideways scroll at ${label}`).toBeLessThanOrEqual(0);
      await page.screenshot({ path: shot(`${KEY}-${label}`) });

      // The row leads to the printers, where the receipts' card says why and where to fix it (gh:hub#2016).
      await row.click();
      await expect(page).toHaveURL(`${A}/printing/printers`);
      const why = shown(page).locator('[data-testid=printing-summary-no-device-receipt]');
      await expect(why).toHaveText('Ningún dispositivo dado de alta lo imprime: dalo de alta en Dispositivos.');
      await expect(shown(page).locator('[data-testid=printing-summary-card-receipt]')).toContainText('Sin dispositivo');

      // The device set up with the till quiets the bell and the card, live.
      deviceId = await setUpDevice(context, device);
      await badgeSays(page, before.total);
      await expect(why).toHaveCount(0);

      // Back on the Home, the step is done; the device retired, it is pending again without a reload.
      await page.goto(`${A}/`);
      await unfolded(page);
      await expect(pill(page)).toHaveText('Hecho');
      await expect(step(page).locator(`[data-testid="setup-configure-${STEP}"]`)).toHaveCount(0);
      const retired = await api(context, A, 'POST', '/printing/devices/retire', { device_id: deviceId });
      expect(retired.status).toBe(200);
      await expect(pill(page)).toHaveText('Recomendado');
      await badgeSays(page, before.total + 1);
    } finally {
      await context.close();
      psql(`delete from printing_printjob where printer_id = '${printer}'`);
      forgetDevices(`${TAG} %`, { ids: [device] });
    }
  });
});

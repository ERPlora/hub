// The device takes the paper out of the queue, in Chrome (apps/printing/WORKBOOK.md PRINTING-F18, F05, F13, F14;
// FIX-HUB-PRINTING-WS-PRINT-CLIENT-IN-PACKAGES-UI): the page runs as the installed app — a fake `window.__TAURI__` that
// keeps every command it is asked and answers it, well or with the device's error — against the Hub's real /ws/print
// (daphne). The owner sets this device up from Printing → Devices, and from then on, on any screen:
//   - «Test» on its printer leaves the «Test page» in the queue, the device prints it (`erplora_test_print`) and the
//     queue says «Printed» (F05);
//   - a cash charge at the till queues the receipt with the drawer's order; the device prints it (`erplora_print`), then
//     opens the drawer (`erplora_open_drawer`) and the queue says «Printed» (F18, F13); when the drawer does not answer,
//     the till says so and the receipt is not printed again (hub#2724);
//   - a printer that does not print: the job goes back to the queue with the device's error, and after five hand-outs
//     it is «Failed» (F14).
// Screenshots of the queue in the three viewports. What is made here is deleted, and the settings put back, after it.
// flow: PRINTING-F18
import { randomUUID } from 'node:crypto';

import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, login, psql, shot, shown } from './helpers';
import { cleanInventory, createProduct, dialog, fill, type Product } from './inventory-helpers';
import { cleanInvoices, ensureIssuer, snapshotSeries } from './invoice-helpers';
import { FLOW_VIEWPORTS, forgetDevices } from './printing-helpers';
import { cleanSales, drawerOff, restoreDrawer, stamp } from './sale-helpers';

test.describe.configure({ mode: 'serial' });

const RUN = stamp();
const PRINTER = `e2e WSC ${RUN}`;
const ADDRESS = '10.0.0.77';
const TARGET = `network:${ADDRESS}:9100`;
const DEVICE_NAME = `e2e WSC Counter ${RUN}`;
const KEY = 'FIX-HUB-PRINTING-WS-PRINT-CLIENT-IN-PACKAGES-UI';
/** The device's own id, the same in every test (each one opens a new browser context): the app keeps it across starts. */
const DEVICE = randomUUID();

// Filled in by the fake app's script in the page (`fakeAppScript`).
declare const ADDRESS_IN_PAGE: string;
declare const DEVICE_IN_PAGE: string;

interface Call {
  command: string;
  args: Record<string, unknown> | undefined;
}

interface Job {
  id: string;
  kind: string;
  status: string;
  attempts: number;
  last_error: string;
  open_drawer: boolean;
  document_type: string;
}

let printer: string;
let coffee: Product;
let settingsBefore: { open_drawer_on_sale: boolean; print_receipt_on_sale: boolean } | undefined;

/**
 * The installed app, faked on the hub's own pages only (the SaaS's login stays a browser's): the device's own id, which
 * the app keeps across starts, and Tauri's global bridge with an `invoke` that keeps each command and answers as the
 * tab's `e2e-print-mode` says (it outlives a reload, as the printer's state does) — `ok`, `fail` (every print refused,
 * as a printer switched off) or `drawer` (the paper prints, the drawer does not answer).
 */
function fakeApp(): void {
  if (!window.location.hostname.startsWith('a.')) return;
  window.localStorage.setItem('erplora.device_id', DEVICE_IN_PAGE);
  const state = {
    get mode() {
      return window.sessionStorage.getItem('e2e-print-mode') ?? 'ok';
    },
    calls: [] as { command: string; args: unknown }[],
  };
  Object.assign(window, { __e2ePrint: state });
  const prints = new Set(['erplora_print', 'erplora_test_print', 'erplora_open_drawer', 'print_document']);
  Object.assign(window, {
    __TAURI__: {
      core: {
        invoke: async (command: string, args?: unknown) => {
          if (!prints.has(command)) return null;
          state.calls.push({ command, args });
          if (state.mode === 'fail') throw `printer_unreachable: ${ADDRESS_IN_PAGE} did not answer`;
          if (state.mode === 'drawer' && command === 'erplora_open_drawer') throw `printer_unreachable: ${ADDRESS_IN_PAGE}`;
          return null;
        },
      },
    },
  });
}

/** The fake app with its address and device id (addInitScript serialises the function, not its scope). */
const fakeAppScript = `const ADDRESS_IN_PAGE = '${ADDRESS}';\nconst DEVICE_IN_PAGE = '${DEVICE}';\n(${fakeApp.toString()})();`;

async function appPage(page: Page, next: string): Promise<void> {
  await page.addInitScript({ content: fakeAppScript });
  await login(page, A, next);
}

const calls = (page: Page): Promise<Call[]> =>
  page.evaluate(() => (window as unknown as { __e2ePrint: { calls: Call[] } }).__e2ePrint.calls);

async function setMode(page: Page, mode: 'ok' | 'fail' | 'drawer'): Promise<void> {
  await page.evaluate((m) => window.sessionStorage.setItem('e2e-print-mode', m), mode);
}

async function jobsOf(context: BrowserContext): Promise<Job[]> {
  const res = await api<{ rows: Job[] }>(context, A, 'GET', `/printing/jobs?printer_id=${printer}&limit=100`);
  expect(res.status).toBe(200);
  return res.data.rows;
}

async function newestJob(context: BrowserContext): Promise<Job> {
  return (await jobsOf(context))[0];
}

/** The till, painted. */
async function tillReady(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid^=pos-product-], [data-testid=pos-grid-empty]').first().waitFor({ state: 'visible' });
}

/** A coffee charged in cash at the till, the way a person does. */
async function chargeCoffeeInCash(page: Page, cash: string): Promise<void> {
  await tillReady(page);
  await shown(page).locator('[data-testid=pos-search-trigger]').click();
  const search = page.locator('[data-testid=pos-search]');
  await search.locator('input').fill(coffee.sku);
  await search.locator(`[data-testid=pos-search-${coffee.id}]`).click();
  await expect(shown(page).locator('[data-testid=pos-total]')).toContainText(/1[.,]50/);
  await shown(page).locator('[data-testid=pos-charge]').click();
  const sheet = page.locator('[data-testid=sale-checkout-modal]');
  await expect(sheet).toBeVisible();
  await sheet.locator(`[data-testid=sale-checkout-method-${cash}]`).click();
  await sheet.locator('[data-testid=sale-checkout-keypad-5]').click();
  await sheet.locator('[data-testid=sale-checkout-confirm]').click();
  await expect(sheet).toBeHidden();
}

/** The sale's document, which the charge opens, closed: the till is free for the next one. */
async function closeDocument(page: Page): Promise<void> {
  const document = page.locator('[data-testid=sale-document-modal]');
  await expect(document).toBeVisible();
  await document.locator('[data-testid=sale-document-close]').click();
  await expect(document).toBeHidden();
}

async function printersRowAction(page: Page, action: string): Promise<void> {
  const hook = `printing-printers-row-${printer}-${action}`;
  const inline = shown(page).locator(`[data-testid=${hook}]`);
  if ((await inline.count()) > 0 && (await inline.first().isVisible())) {
    await inline.first().click();
    return;
  }
  await shown(page).locator(`[data-testid=printing-printers-row-${printer}-menu]`).first().click();
  await page.locator(`ion-popover [data-testid=${hook}]`).click();
}

async function dismissToasts(page: Page): Promise<void> {
  await page.locator('ion-toast').evaluateAll((toasts) =>
    Promise.all(toasts.map((toast) => (toast as unknown as { dismiss: () => Promise<boolean> }).dismiss())),
  );
  await expect(page.locator('ion-toast')).toHaveCount(0);
}

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/printing/printers');
  // The receipt is the fiscal document's: without an issuer the charge queues no paper.
  snapshotSeries();
  await ensureIssuer(context);
  const created = await api<{ id: string }>(context, A, 'POST', '/printing/printers', {
    name: PRINTER,
    kind: 'network',
    address: ADDRESS,
    usage: 'receipt',
  });
  expect(created.status, JSON.stringify(created.data)).toBe(201);
  printer = created.data.id;
  coffee = await createProduct(context, { name: `E2E WSC Coffee ${RUN}`, sku: `E2E-WSC-${RUN}`, price: 150 });
  await drawerOff(context);
  const settings = await api<{ open_drawer_on_sale: boolean; print_receipt_on_sale: boolean }>(context, A, 'GET', '/printing/settings');
  expect(settings.status).toBe(200);
  settingsBefore = settings.data;
  const on = await api(context, A, 'POST', '/printing/settings', { open_drawer_on_sale: true, print_receipt_on_sale: true });
  expect(on.status, JSON.stringify(on.data)).toBe(200);
  await context.close();
});

test.afterAll(() => {
  try {
    psql(`delete from printing_printjob where printer_id in (select id from printing_printer where name like 'e2e WSC %')`);
    forgetDevices('e2e WSC %', { ids: [DEVICE], names: ['e2e WSC Counter %'] });
    if (settingsBefore) {
      psql(
        `update printing_settings set open_drawer_on_sale = ${settingsBefore.open_drawer_on_sale}, ` +
          `print_receipt_on_sale = ${settingsBefore.print_receipt_on_sale}`,
      );
    }
    for (const column of ['receipt_printer_id', 'kitchen_printer_id', 'bar_printer_id', 'label_printer_id']) {
      psql(`update printing_settings set ${column} = null where ${column} in (select id from printing_printer where name like 'e2e WSC %')`);
    }
    psql(`delete from printing_printer where name like 'e2e WSC %'`);
    cleanInvoices();
  } finally {
    cleanSales();
    cleanInventory();
    restoreDrawer();
  }
});

test('PRINTING-F18, F05: the device set up from Devices prints the test page from the queue, and it says «Printed»', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await appPage(page, '/printing/devices');
  await shown(page).locator('[data-testid=printing-devices-this]').waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid=printing-devices-add]').click();
  const modal = dialog(page, 'printing-device');
  await expect(modal).toBeVisible();
  await fill(modal, 'printing-device-name', DEVICE_NAME);
  await modal.locator(`[data-testid=printing-device-printer-${printer}]`).click();
  await modal.locator('[data-testid=printing-device-submit]').click();
  await expect(modal).toBeHidden();
  const row = shown(page).locator('[data-testid=printing-devices-row]').filter({ hasText: DEVICE_NAME });
  await expect(row).toContainText(/This device|Este dispositivo/);
  // Connected: its hello is news that it is there, and the list shows when it was last seen.
  await expect
    .poll(() => psql(`select count(*) from printing_printdevice where name = '${DEVICE_NAME}' and last_seen_at is not null`))
    .toBe('1');
  await dismissToasts(page);

  await page.goto('/printing/printers');
  await shown(page).locator('[data-testid=printing-printers-row]').filter({ hasText: PRINTER }).waitFor({ state: 'visible' });
  await printersRowAction(page, 'test');
  await expect(page.locator('ion-toast').filter({ hasText: /Test page sent to the queue of|Hoja de prueba enviada a la cola de/ }).last()).toBeVisible();
  await expect.poll(async () => (await newestJob(context))?.status).toBe('done');
  const test = await newestJob(context);
  expect([test.kind, test.attempts]).toEqual(['test_page', 1]);
  const printed = (await calls(page)).filter((call) => call.command === 'erplora_test_print');
  expect(printed).toHaveLength(1);
  expect(printed[0].args?.printerId).toBe(TARGET);
  expect(printed[0].args?.data).toMatchObject({ locale: expect.any(String) });
});

test('PRINTING-F18, F13: a cash charge at the till prints its receipt, then opens the drawer; a drawer that does not answer is told', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await appPage(page, '/sale/pos');
  const list = await api<{ rows: { id: string; type: string }[] }>(context, A, 'GET', '/sale/payment_methods');
  const cash = list.data.rows.find((row) => row.type === 'cash')!.id;
  const before = (await jobsOf(context)).length;

  await chargeCoffeeInCash(page, cash);
  await expect.poll(async () => (await jobsOf(context)).length).toBe(before + 1);
  await expect.poll(async () => (await newestJob(context)).status).toBe('done');
  const receipt = await newestJob(context);
  expect([receipt.kind, receipt.document_type, receipt.open_drawer, receipt.attempts]).toEqual(['document', 'receipt', true, 1]);
  await expect.poll(async () => (await calls(page)).map((call) => call.command)).toEqual(['erplora_print', 'erplora_open_drawer']);
  const [paper, drawer] = await calls(page);
  expect(paper.args).toMatchObject({ printerId: TARGET, documentType: 'receipt', jobId: receipt.id });
  expect(drawer.args).toEqual({ printerId: TARGET });
  await closeDocument(page);
  await dismissToasts(page);

  // The drawer does not answer: the till says so, and the receipt that came out is not printed again.
  await setMode(page, 'drawer');
  await chargeCoffeeInCash(page, cash);
  const told = page.locator('ion-toast').filter({
    hasText: new RegExp(`(The cash drawer did not open: check that “${PRINTER}” is on and connected\\.|El cajón no se ha abierto: comprueba que «${PRINTER}» está encendida y conectada\\.)`),
  });
  await expect(told.last()).toBeVisible();
  await page.screenshot({ path: shot(`${KEY}-drawer-1440`) });
  await expect.poll(async () => (await jobsOf(context)).length).toBe(before + 2);
  await expect.poll(async () => (await newestJob(context)).status).toBe('done');
  expect((await newestJob(context)).attempts).toBe(1);
  expect((await calls(page)).filter((call) => call.command === 'erplora_print')).toHaveLength(2);
});

test('PRINTING-F18, F14: a printer that does not print sends the job back with its error, and after five hand-outs it is «Failed»', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await appPage(page, '/printing/printers');
  await setMode(page, 'fail');
  await shown(page).locator('[data-testid=printing-printers-row]').filter({ hasText: PRINTER }).waitFor({ state: 'visible' });
  await printersRowAction(page, 'test');
  await expect.poll(async () => (await newestJob(context)).attempts).toBe(1);
  const failing = await newestJob(context);
  expect([failing.kind, failing.status, failing.last_error]).toEqual(['test_page', 'pending', `printer_unreachable: ${ADDRESS} did not answer`]);
  // Back in the queue, the device does not take it again by itself (a printer out of paper would burn its five
  // hand-outs in a moment): the app opened again takes it at its next connection.
  for (let attempt = 2; attempt <= 5; attempt += 1) {
    await page.reload();
    await expect.poll(async () => (await newestJob(context)).attempts, { timeout: 20_000 }).toBe(attempt);
  }
  await expect.poll(async () => (await newestJob(context)).status).toBe('failed');

  await page.goto('/printing/jobs');
  const status = shown(page).locator(`[data-testid=printing-jobs-status-${failing.id}]`);
  await expect(status.first()).toContainText(/Failed|Fallido/);
  for (const viewport of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await expect(shown(page).locator(`[data-testid=printing-jobs-status-${failing.id}]`).first()).toBeVisible();
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await page.screenshot({ path: shot(`${KEY}-${viewport.label}`) });
  }
});

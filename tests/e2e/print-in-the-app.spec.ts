// Printing inside the installed app (hub#455; SALE-F21, SALE-F29, INVOICE-F18, CASH_REGISTER-F16), in Chrome: the
// app's webview prints nothing on `window.print()`, so without a receipt printer in the business the paper goes to
// the app's own print screen — the `print_document` command of ERPlora/app's bridge, answered here: it keeps the
// HTML it is handed, as the app hands it to the system's print dialog (a printer or «Save as PDF»). Each paper
// arrives as a whole page of its own, titled, with its styles and without a script, and painted under the print
// window's CSP it reads as on screen (`APP-PRINT-<paper>` screenshots). An app that cannot print says why (en + es).
// The business's printers are switched off for the run and back on after it; what it makes is deleted after it.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, login, psql, shot, shown } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { cleanInvoices, ensureIssuer, issuedIds, snapshotSeries } from './invoice-helpers';
import { chargeByApi, cleanSales, drawerOff, restoreDrawer, stamp } from './sale-helpers';

const RUN = stamp();
let coffee: Product;
/** The printers that were on before the run (switched off for it: nothing is queued, the device prints). */
let printersOn: string[] = [];
/** The cash sessions this run opened. */
const sessions = new Set<string>();

/** The window the app prints in (ERPlora/app `src-tauri/src/lib.rs`, `print_document`): no script, no address. */
const PRINT_WINDOW_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data: blob: https:";

interface Printed {
  /** Every `html` the app was asked to print. */
  documents: string[];
  /** `window.print()` calls: the webview's, which print nothing. */
  browser: number;
}

/** The app's bridge in every page of `context`: `print_document` keeps its HTML, or refuses with `refusal`. */
async function appBridge(context: BrowserContext, refusal = ''): Promise<void> {
  await context.addInitScript((refused: string) => {
    const printed: Printed = { documents: [], browser: 0 };
    (window as unknown as { printed: Printed }).printed = printed;
    const invoke = (command: string, args?: { html?: string }) => {
      if (command !== 'print_document') return Promise.reject('unknown_command');
      if (refused) return Promise.reject(refused);
      printed.documents.push(args?.html ?? '');
      return Promise.resolve(null);
    };
    (window as unknown as { __TAURI__: unknown }).__TAURI__ = { core: { invoke } };
    window.print = () => {
      printed.browser += 1;
    };
  }, refusal);
}

const printedIn = (page: Page): Promise<Printed> => page.evaluate(() => (window as unknown as { printed: Printed }).printed);

/** The one document the app was asked to print, once it was. */
async function theDocument(page: Page): Promise<string> {
  await expect.poll(async () => (await printedIn(page)).documents.length).toBe(1);
  const printed = await printedIn(page);
  expect(printed.browser, 'the webview prints nothing: window.print() is not the way').toBe(0);
  return printed.documents[0];
}

/** A whole page of its own, titled `title`, with its styles and no script. */
function expectStandalone(html: string, title: string): void {
  expect(html.startsWith('<!doctype html>')).toBe(true);
  expect(html).toContain(`<title>${title}</title>`);
  expect(html).toMatch(/<style>[^<]*\{/);
  expect(html).not.toMatch(/<script/i);
}

/** The document painted as the print window paints it (its CSP, no script), screenshotted. */
async function paintAsTheApp(page: Page, html: string, name: string): Promise<void> {
  const window = await page.context().newPage();
  const errors: string[] = [];
  window.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });
  await window.setViewportSize({ width: 820, height: 1180 });
  await window.setContent(html.replace('<head>', `<head><meta http-equiv="Content-Security-Policy" content="${PRINT_WINDOW_CSP}">`));
  await expect(window.locator('body > *').first()).toBeVisible();
  await window.screenshot({ path: shot(`APP-PRINT-${name}`), fullPage: true });
  expect(errors, 'the print window refuses nothing of the paper').toEqual([]);
  await window.close();
}

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  snapshotSeries();
  await ensureIssuer(context);
  await drawerOff(context);
  coffee = await createProduct(context, { name: `E2E App Coffee ${RUN}`, sku: `E2E-PIA-${RUN}`, price: 150 });
  printersOn = psql('select string_agg(id::text, \',\') from printing_printer where is_active').split(',').filter(Boolean);
  if (printersOn.length) psql(`update printing_printer set is_active = false where id in (${printersOn.map((id) => `'${id}'`).join(',')})`);
  await context.close();
});

test.afterAll(() => {
  try {
    const ids = [...sessions].map((id) => `'${id}'`).join(',');
    if (ids) {
      psql(`delete from cash_register_count where session_id in (${ids})`);
      psql(`delete from cash_register_movement where session_id in (${ids})`);
      psql(`delete from cash_register_session where id in (${ids})`);
    }
    cleanInvoices();
  } finally {
    if (printersOn.length) psql(`update printing_printer set is_active = true where id in (${printersOn.map((id) => `'${id}'`).join(',')})`);
    cleanSales();
    cleanInventory();
    restoreDrawer();
  }
});

test('SALE-F29: «Print» on a sale\'s document opens the app\'s print screen with the receipt alone', async ({ page, context }) => {
  await appBridge(context);
  await login(page, A, '/sale/sales');
  const sale = await chargeByApi(context, { lines: [{ product: coffee.sku, quantity: '1' }], payments: [{ method: 'card' }] });
  const number = sale.invoice_number || sale.number;
  await page.goto(`${A}/sale/sales`);
  const row = shown(page).locator(`[data-testid=sales-table-row][data-id="${sale.id}"]`).first();
  await expect(row).toBeVisible();
  const inline = shown(page).locator(`[data-testid=sales-table-row-${sale.id}-document]`);
  if ((await inline.count()) > 0 && (await inline.first().isVisible())) await inline.first().click();
  else {
    await shown(page).locator(`[data-testid=sales-table-row-${sale.id}-menu]`).first().click();
    await page.locator(`ion-popover [data-testid=sales-table-row-${sale.id}-document]`).click();
  }
  const modal = page.locator('[data-testid=sale-document-modal]');
  await expect(modal.locator('[data-testid=sale-document-print]')).toBeEnabled();
  await modal.locator('[data-testid=sale-document-print]').click();
  const html = await theDocument(page);
  expectStandalone(html, number);
  expect(html).toContain(number);
  expect(html).toContain(coffee.name);
  // The paper alone: nothing of the page around it.
  expect(html).not.toContain('sale-document-print');
  await expect(page.locator('ion-toast')).toHaveCount(0);
  await paintAsTheApp(page, html, 'SALE-F29');
});

test('SALE-F21: «Print» on the bill opens the app\'s print screen; an app that cannot print says why', async ({ page, context }) => {
  await appBridge(context);
  await login(page, A, '/sale/pos');
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid=pos-search-trigger]').click();
  const search = page.locator('[data-testid=pos-search]');
  await search.locator('input').fill(coffee.sku);
  await search.locator(`[data-testid=pos-search-${coffee.id}]`).click();
  await expect(shown(page).locator('[data-testid=pos-total]')).toContainText(/1[.,]50/);
  await shown(page).locator('[data-testid=pos-prebill]').click();
  const bill = page.locator('ion-modal[data-testid=pos-prebill]');
  await expect(bill.locator('[data-testid=pos-prebill-print]')).toBeEnabled();
  await bill.locator('[data-testid=pos-prebill-print]').click();
  const html = await theDocument(page);
  expectStandalone(html, 'Bill');
  expect(html).toContain(coffee.name);
  expect(html).not.toContain('pos-prebill-print');
  await paintAsTheApp(page, html, 'SALE-F21');
});

test('SALE-F21: an app from before the print screen says, in Spanish too, to update it', async ({ browser }) => {
  for (const [language, said] of [
    ['en', 'Bill could not be printed: this version of the ERPlora app cannot print; update it'],
    ['es', 'No se pudo imprimir la cuenta: esta versión de la app de ERPlora no puede imprimir; actualízala'],
  ] as const) {
    const context = await browser.newContext({ baseURL: A, locale: language === 'es' ? 'es-ES' : 'en-US' });
    // What Tauri answers for a command the app does not have.
    await appBridge(context, 'Command print_document not found');
    const page = await context.newPage();
    await login(page, A, '/sale/pos');
    await page.evaluate((lang) => localStorage.setItem('erplora.language', lang), language);
    await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
    await shown(page).locator('[data-testid=pos-search-trigger]').click();
    const search = page.locator('[data-testid=pos-search]');
    await search.locator('input').fill(coffee.sku);
    await search.locator(`[data-testid=pos-search-${coffee.id}]`).click();
    await shown(page).locator('[data-testid=pos-prebill]').click();
    const bill = page.locator('ion-modal[data-testid=pos-prebill]');
    await expect(bill.locator('[data-testid=pos-prebill-print]')).toBeEnabled();
    await bill.locator('[data-testid=pos-prebill-print]').click();
    await expect(page.locator('ion-toast').filter({ hasText: said })).toBeVisible();
    expect((await printedIn(page)).browser).toBe(0);
    await context.close();
  }
});

test('INVOICE-F18: «Print / PDF» of an invoice opens the app\'s print screen with its A4 page', async ({ page, context }) => {
  await appBridge(context);
  await login(page, A, '/invoice/invoices');
  const created = await api<{ id: string; number: string }>(context, A, 'POST', '/invoice/invoices', {
    customer_name: `e2e App Talleres ${RUN}`,
    customer_tax_id: 'B12345674',
    customer_address: 'Calle Luna 3, Madrid',
    lines: [{ description: 'e2e App course', quantity: '1', unit_price: 10000, tax_rate: '21' }],
  });
  expect(created.status, JSON.stringify(created.data)).toBe(201);
  issuedIds.add(created.data.id);
  await page.goto(`${A}/invoice/invoices/${created.data.id}`);
  await expect(shown(page).locator('[data-testid=invoice-detail-title]')).toHaveText(`Invoice ${created.data.number}`);
  await expect(shown(page).locator('[data-testid=invoice-detail-print]')).toBeEnabled();
  await shown(page).locator('[data-testid=invoice-detail-print]').click();
  const html = await theDocument(page);
  expectStandalone(html, `Invoice ${created.data.number}`);
  expect(html).toContain(created.data.number);
  expect(html).toContain(`e2e App Talleres ${RUN}`);
  await paintAsTheApp(page, html, 'INVOICE-F18');
});

test('CASH_REGISTER-F16: «Print» on a closed session opens the app\'s print screen with its Z report', async ({ page, context }) => {
  await appBridge(context);
  await login(page, A, '/cash_register/sessions');
  const left = (await api<{ session: { id: string; expected_balance: number | null } | null }>(context, A, 'GET', '/cash_register/sessions/current')).data.session;
  if (left) {
    const closed = await api(context, A, 'POST', '/cash_register/sessions/close', { session_id: left.id, closing_balance: Math.max(left.expected_balance ?? 0, 0) });
    expect(closed.status, JSON.stringify(closed.data)).toBe(200);
  }
  const opened = await api<{ id: string }>(context, A, 'POST', '/cash_register/sessions/open', { opening_balance: 1000 });
  expect(opened.status, JSON.stringify(opened.data)).toBe(201);
  sessions.add(opened.data.id);
  const closed = await api(context, A, 'POST', '/cash_register/sessions/close', { session_id: opened.data.id, closing_balance: 1000, closing_notes: 'e2e app' });
  expect(closed.status, JSON.stringify(closed.data)).toBe(200);
  const { number } = (await api<{ number: string }>(context, A, 'GET', `/cash_register/sessions/detail?session_id=${opened.data.id}`)).data;
  await page.goto(`${A}/cash_register/sessions/${opened.data.id}`);
  await shown(page).locator('[data-testid=cash-register-summary]').waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid=cash-register-detail-print]').click();
  const html = await theDocument(page);
  expectStandalone(html, `Cash closing (Z) · ${number}`);
  expect(html).toContain('Cash closing (Z)');
  expect(html).toContain(number);
  await paintAsTheApp(page, html, 'CASH_REGISTER-F16');
});

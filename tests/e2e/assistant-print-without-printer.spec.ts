// The prints the assistant can ask for where no receipt printer takes the paper, end to end: a sale's reprint
// (SALE-F29), a table's bill (SALE-F21) and a cash session's report (CASH_REGISTER-F16), asked of the assistant in
// Spanish, are not done and its receipt says why (BASE-F97, BASE-F99); a reprint a receipt printer takes says «Done».
// The business's printers are switched off for the run and back on after it; what it makes is deleted after it.
// hub#2328: the receipt said «Done» and nothing was printed.
// flow: SALE-F29
// flow: SALE-F21
// flow: CASH_REGISTER-F16
// flow: BASE-F97 (the receipt of a write that failed says why)

import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { askForACard, card, decide, lastAnswer, openPanelAtTheDesk, panel } from './assistant-panel';
import { A, api, capture, login, psql } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { cleanInvoices, ensureIssuer, snapshotSeries } from './invoice-helpers';
import { printersBackOn, printersOff } from './printing-helpers';
import { panelSpec } from './provider-helpers';
import { chargeByApi, cleanSales, drawerOff, restoreDrawer, stamp } from './sale-helpers';

const KEY = 'FIX-HUB-ASSISTANT-PRINT-WITHOUT-PRINTER';
const RUN = stamp();
const SIZES = [
  { width: 1440, height: 900 },
  { width: 820, height: 1180 },
  { width: 375, height: 667 },
] as const;
const NO_PRINTER_FOR_THE_SALE =
  'Ninguna impresora de tiques recibe el papel de esta venta: abre la venta para imprimirlo en este dispositivo.';
const NO_PRINTER_FOR_THE_BILL = 'Ninguna impresora de tiques recibe esta cuenta: ábrela en Ventas para imprimirla en este dispositivo.';
const NO_PRINTER_FOR_THE_REPORT =
  'Ninguna impresora de recibos recibe este informe: abre la sesión para imprimirlo en este dispositivo.';

panelSpec();
let coffee: Product;
/** The printers that were on before the run (switched off for it). */
let printersOn: string[] = [];
/** The cash sessions this run opened. */
const sessions = new Set<string>();

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  await login(await context.newPage(), A, '/sale/pos');
  snapshotSeries();
  await ensureIssuer(context);
  await drawerOff(context);
  coffee = await createProduct(context, { name: `E2E Apw Coffee ${RUN}`, sku: `E2E-APW-${RUN}`, price: 150 });
  printersOn = printersOff();
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
    printersBackOn(printersOn);
    restoreDrawer();
    cleanSales();
    cleanInventory();
  }
});

/** The owner, in Spanish, with the assistant open at a computer's size. */
async function inSpanish(page: Page, context: BrowserContext): Promise<void> {
  await login(page, A, '/');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await openPanelAtTheDesk(page);
}

const lastReceipt = (page: Page) => panel(page).locator('[data-testid="assistant-receipt"]').last();

/** The card of the write `tool` with `args`, asked of the assistant and confirmed. */
async function confirmed(page: Page, tool: string, args: Record<string, string>): Promise<void> {
  await askForACard(page, `E2E-ASK ${tool} ${JSON.stringify(args)}`);
  await expect(card(page)).toContainText('Imprimir');
  await decide(page, 'submit');
  await expect(lastAnswer(page)).toBeVisible();
}

/** The paper jobs of Printing that name `reference`. */
async function jobsOf(context: BrowserContext, reference: string): Promise<string[]> {
  const jobs = await api<{ rows: { reference: string }[] }>(context, A, 'GET', '/printing/jobs?limit=100');
  return jobs.data.rows.map((job) => job.reference).filter((named) => named === reference);
}

test('SALE-F29 from the assistant: a reprint no receipt printer takes is not done and says why', async ({ page, context }) => {
  await inSpanish(page, context);
  const sale = await chargeByApi(context, { lines: [{ product: coffee.sku, quantity: '1' }], payments: [{ method: 'card' }] });
  await confirmed(page, 'sale__sale__print', { sale_id: sale.id });
  await expect(lastReceipt(page)).toContainText(`No se hizo, falló: Imprimir en Ventas / TPV. ${NO_PRINTER_FOR_THE_SALE}`);
  for (const size of SIZES) {
    await page.setViewportSize(size);
    await expect(lastReceipt(page)).toBeVisible();
    await capture(page, `${KEY}-RECEIPT-${size.width}x${size.height}`);
  }
  expect(await jobsOf(context, sale.invoice_number ?? sale.number)).toEqual([]);
});

test('SALE-F21 from the assistant: a bill no receipt printer takes is not done, says why and leaves the table unmarked', async ({ page, context }) => {
  await inSpanish(page, context);
  const check = await api<{ id: string }>(context, A, 'POST', '/sale/orders', { label: `E2E Apw check ${RUN}`, lines: [{ product: coffee.sku }] });
  expect(check.status, JSON.stringify(check.data)).toBe(201);
  await confirmed(page, 'sale__order__print_bill', { order_id: check.data.id });
  await expect(lastReceipt(page)).toContainText('No se hizo');
  await expect(lastReceipt(page)).toContainText(NO_PRINTER_FOR_THE_BILL);
  expect(psql(`select bill_printed_at is null from sale_order where id = '${check.data.id}'`).trim()).toBe('t');
});

test('CASH_REGISTER-F16 from the assistant: a report no receipt printer takes is not done and says why', async ({ page, context }) => {
  await inSpanish(page, context);
  const left = (await api<{ session: { id: string; expected_balance: number | null } | null }>(context, A, 'GET', '/cash_register/sessions/current')).data.session;
  if (left) {
    const closed = await api(context, A, 'POST', '/cash_register/sessions/close', { session_id: left.id, closing_balance: Math.max(left.expected_balance ?? 0, 0) });
    expect(closed.status, JSON.stringify(closed.data)).toBe(200);
  }
  const opened = await api<{ id: string }>(context, A, 'POST', '/cash_register/sessions/open', { opening_balance: 1000 });
  expect(opened.status, JSON.stringify(opened.data)).toBe(201);
  sessions.add(opened.data.id);
  await confirmed(page, 'cash_register__session__print', { session_id: opened.data.id });
  await expect(lastReceipt(page)).toContainText('No se hizo');
  await expect(lastReceipt(page)).toContainText(NO_PRINTER_FOR_THE_REPORT);
});

test('SALE-F29 from the assistant: a reprint a receipt printer takes says «Done»', async ({ page, context }) => {
  await inSpanish(page, context);
  const till = await api<{ id: string }>(context, A, 'POST', '/printing/printers', {
    name: `e2e Apw Till ${RUN}`,
    kind: 'network',
    address: '192.168.1.50',
    usage: 'receipt',
  });
  expect(till.status, JSON.stringify(till.data)).toBe(201);
  try {
    const sale = await chargeByApi(context, { lines: [{ product: coffee.sku, quantity: '1' }], payments: [{ method: 'card' }] });
    await confirmed(page, 'sale__sale__print', { sale_id: sale.id });
    await expect(lastReceipt(page)).toHaveText(/Hecho: Imprimir en Ventas \/ TPV$/);
    expect(await jobsOf(context, sale.invoice_number ?? sale.number)).toHaveLength(2);
  } finally {
    psql(`delete from printing_printjob where printer_id = '${till.data.id}'`);
    psql(`delete from printing_printer where id = '${till.data.id}'`);
  }
});

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

import { askForACard, card, decide, lastAnswer, openPanelInSpanish, receipts } from './assistant-panel';
import { A, api, login, psql } from './helpers';
import { freshSession } from './cash-session-helpers';
import { endPrintRun, type PrintRun, startPrintRun } from './print-run-helpers';
import { fleetShots } from './printing-helpers';
import { panelSpec } from './provider-helpers';
import { chargeByApi, type SaleOut, stamp } from './sale-helpers';

const KEY = 'FIX-HUB-ASSISTANT-PRINT-WITHOUT-PRINTER';
const RUN = stamp();
const NO_PRINTER_FOR_THE_SALE =
  'Ninguna impresora de tiques recibe el papel de esta venta: abre la venta para imprimirlo en este dispositivo.';
const NO_PRINTER_FOR_THE_BILL = 'Ninguna impresora de tiques recibe esta cuenta: ábrela en Ventas para imprimirla en este dispositivo.';
const NO_PRINTER_FOR_THE_REPORT =
  'Ninguna impresora de recibos recibe este informe: abre la sesión para imprimirlo en este dispositivo.';

panelSpec();
let run: PrintRun;

test.beforeAll(async ({ browser }) => {
  run = await startPrintRun(browser, `E2E Apw Coffee ${RUN}`, `E2E-APW-${RUN}`);
});

test.afterAll(() => endPrintRun(run));

const lastReceipt = (page: Page) => receipts(page).last();

/** The card of the write `tool` with `args`, asked of the assistant by the owner in Spanish and confirmed. */
async function confirmed(page: Page, tool: string, args: Record<string, string>): Promise<void> {
  await openPanelInSpanish(page);
  await askForACard(page, `E2E-ASK ${tool} ${JSON.stringify(args)}`);
  await expect(card(page)).toContainText('Imprimir');
  await decide(page, 'submit');
  await expect(lastAnswer(page)).toBeVisible();
}

const aCoffee = (context: BrowserContext): Promise<SaleOut> =>
  chargeByApi(context, { lines: [{ product: run.coffee.sku, quantity: '1' }], payments: [{ method: 'card' }] });

/** The paper jobs of Printing for `sale`. */
async function jobsOf(context: BrowserContext, sale: SaleOut): Promise<string[]> {
  const jobs = await api<{ rows: { reference: string }[] }>(context, A, 'GET', '/printing/jobs?limit=100');
  return jobs.data.rows.map((job) => job.reference).filter((reference) => reference === (sale.invoice_number || sale.number));
}

test('SALE-F29 from the assistant: a reprint no receipt printer takes is not done and says why', async ({ page, context }) => {
  await login(page, A, '/');
  const sale = await aCoffee(context);
  await confirmed(page, 'sale__sale__print', { sale_id: sale.id });
  await expect(lastReceipt(page)).toContainText(`No se hizo, falló: Imprimir en Ventas / TPV. ${NO_PRINTER_FOR_THE_SALE}`);
  await fleetShots(page, `${KEY}-RECEIPT`, (shown) => expect(lastReceipt(shown)).toBeVisible());
  expect(await jobsOf(context, sale)).toEqual([]);
});

test('SALE-F21 from the assistant: a bill no receipt printer takes is not done, says why and leaves the table unmarked', async ({ page, context }) => {
  await login(page, A, '/');
  const check = await api<{ id: string }>(context, A, 'POST', '/sale/orders', { label: `E2E Apw check ${RUN}`, lines: [{ product: run.coffee.sku }] });
  expect(check.status, JSON.stringify(check.data)).toBe(201);
  await confirmed(page, 'sale__order__print_bill', { order_id: check.data.id });
  await expect(lastReceipt(page)).toContainText('No se hizo');
  await expect(lastReceipt(page)).toContainText(NO_PRINTER_FOR_THE_BILL);
  expect(psql(`select bill_printed_at is null from sale_order where id = '${check.data.id}'`).trim()).toBe('t');
});

test('CASH_REGISTER-F16 from the assistant: a report no receipt printer takes is not done and says why', async ({ page, context }) => {
  await login(page, A, '/');
  const session = await freshSession(context, run.sessions);
  await confirmed(page, 'cash_register__session__print', { session_id: session });
  await expect(lastReceipt(page)).toContainText('No se hizo');
  await expect(lastReceipt(page)).toContainText(NO_PRINTER_FOR_THE_REPORT);
});

test('SALE-F29 from the assistant: a reprint a receipt printer takes says «Done»', async ({ page, context }) => {
  await login(page, A, '/');
  const till = await api<{ id: string }>(context, A, 'POST', '/printing/printers', {
    name: `e2e Apw Till ${RUN}`,
    kind: 'network',
    address: '192.168.1.50',
    usage: 'receipt',
  });
  expect(till.status, JSON.stringify(till.data)).toBe(201);
  try {
    const sale = await aCoffee(context);
    await confirmed(page, 'sale__sale__print', { sale_id: sale.id });
    await expect(lastReceipt(page)).toHaveText(/Hecho: Imprimir en Ventas \/ TPV$/);
    expect(await jobsOf(context, sale)).toHaveLength(2);
  } finally {
    psql(`delete from printing_printjob where printer_id = '${till.data.id}'`);
    psql(`delete from printing_printer where id = '${till.data.id}'`);
  }
});

// Printing an invoice where no system printer takes it (INVOICE-F18), end to end: asked of the assistant, its receipt
// says it was not done and why, in Spanish, and «Done» only once a system printer took the page (BASE-F97, BASE-F99);
// on the invoice's own page, «Print / PDF» still opens the device's print dialog and says no error. The business's
// printers are switched off for the run and back on after it; what it makes is deleted after it.
// hub#2293: the receipt said «Hecho: Imprimir en Facturación» and nothing was printed.
// flow: INVOICE-F18
// flow: BASE-F97 (the receipt of a write that failed says why)

import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { askForACard, card, decide, lastAnswer, openPanelAtTheDesk, panel } from './assistant-panel';
import { A, api, login, psql, shown } from './helpers';
import { cleanInvoices, issuedIds, readyToInvoice } from './invoice-helpers';
import { fleetShots, printersBackOn, printersOff } from './printing-helpers';
import { panelSpec } from './provider-helpers';
import { stamp } from './sale-helpers';
import { toasts } from './toast-helpers';

const KEY = 'FIX-HUB-INVOICE-PRINT-WITHOUT-PRINTER';
const RUN = stamp();
const OFFICE = `e2e Office ${RUN}`;
const NOT_PRINTED =
  'No se hizo, falló: Imprimir en Facturación. Ninguna impresora del sistema recibe esta factura: ábrela para imprimirla o ' +
  'guardarla en PDF.';

panelSpec();
/** The printers that were on before the run (switched off for it). */
let printersOn: string[] = [];

test.beforeAll(async ({ browser }) => {
  await (await readyToInvoice(browser)).close();
  printersOn = printersOff();
});

test.afterAll(() => {
  try {
    cleanInvoices();
  } finally {
    printersBackOn(printersOn);
  }
});

async function anInvoice(context: BrowserContext): Promise<{ id: string; number: string }> {
  const created = await api<{ id: string; number: string }>(context, A, 'POST', '/invoice/invoices', {
    customer_name: `e2e Bodas Sur ${RUN}`,
    customer_tax_id: 'B12345674',
    customer_address: 'Calle Luna 3, Madrid',
    lines: [{ description: 'e2e Cumpleaños', quantity: '1', unit_price: 10000, tax_rate: '21' }],
  });
  expect(created.status, JSON.stringify(created.data)).toBe(201);
  issuedIds.add(created.data.id);
  return created.data;
}

/** The owner, in Spanish, with the assistant open at a computer's size. */
async function inSpanish(page: Page, context: BrowserContext): Promise<void> {
  await login(page, A, '/');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await openPanelAtTheDesk(page);
}

const lastReceipt = (page: Page) => panel(page).locator('[data-testid="assistant-receipt"]').last();

async function printedFromTheAssistant(page: Page, invoiceId: string): Promise<void> {
  await askForACard(page, `E2E-ASK invoice__invoice__print {"invoice_id":"${invoiceId}"}`);
  await expect(card(page)).toContainText('Imprimir en Facturación');
  await decide(page, 'submit');
  await expect(lastAnswer(page)).toBeVisible();
}

test('INVOICE-F18 from the assistant: with no system printer the receipt says it was not done and why', async ({ page, context }) => {
  await inSpanish(page, context);
  const invoice = await anInvoice(context);
  await printedFromTheAssistant(page, invoice.id);
  await expect(lastReceipt(page)).toHaveText(NOT_PRINTED);
  await fleetShots(page, `${KEY}-RECEIPT`, (shown) => expect(lastReceipt(shown)).toBeVisible());
  const jobs = await api<{ rows: { reference: string }[] }>(context, A, 'GET', '/printing/jobs?limit=100');
  expect(jobs.data.rows.filter((job) => job.reference === invoice.number)).toEqual([]);
});

test('INVOICE-F18 from the assistant: a page the system printer took says «Done»', async ({ page, context }) => {
  await inSpanish(page, context);
  const system = await api<{ id: string }>(context, A, 'POST', '/printing/printers', { name: OFFICE, kind: 'system', usage: 'receipt' });
  expect(system.status, JSON.stringify(system.data)).toBe(201);
  try {
    const invoice = await anInvoice(context);
    await printedFromTheAssistant(page, invoice.id);
    await expect(lastReceipt(page)).toHaveText('Hecho: Imprimir en Facturación');
    const jobs = await api<{ rows: { reference: string }[] }>(context, A, 'GET', `/printing/jobs?printer_id=${system.data.id}&limit=100`);
    expect(jobs.data.rows.map((job) => job.reference)).toEqual([invoice.number]);
  } finally {
    psql(`delete from printing_printjob where printer_id = '${system.data.id}'`);
    psql(`delete from printing_printer where id = '${system.data.id}'`);
  }
});

test('INVOICE-F18 on its page: with no system printer «Print / PDF» opens the device\'s dialog, with no error', async ({ page, context }) => {
  await context.addInitScript(() => {
    (window as unknown as { printed: number }).printed = 0;
    window.print = () => {
      (window as unknown as { printed: number }).printed += 1;
    };
  });
  await login(page, A, '/invoice/invoices');
  const invoice = await anInvoice(context);
  await page.goto(`${A}/invoice/invoices/${invoice.id}`);
  const detail = shown(page);
  await expect(detail.locator('[data-testid=invoice-detail-title]')).toHaveText(`Invoice ${invoice.number}`);
  await expect(detail.locator('[data-testid=invoice-detail-print]')).toBeEnabled();
  await detail.locator('[data-testid=invoice-detail-print]').click();
  await expect.poll(() => page.evaluate(() => (window as unknown as { printed: number }).printed)).toBe(1);
  await expect(toasts(page)).toHaveCount(0);
  // The dialog closed, as the browser's does once it prints or is cancelled.
  await page.evaluate(() => window.dispatchEvent(new Event('afterprint')));
  await fleetShots(page, `${KEY}-PAGE`, () => expect(detail.locator('[data-testid=invoice-detail-print]')).toBeVisible());
});

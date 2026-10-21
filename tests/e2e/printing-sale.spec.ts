// Sales and Invoicing ask Printing for their paper, in Chrome (apps/printing/WORKBOOK.md PRINTING-F07, F08, F09,
// F13; SALE-F01, F21, F29; INVOICE-F18): with a receipt printer and a system printer in the business,
//   - the till's charge in cash puts its receipt in the receipt printer's queue with the order to open the
//     drawer (a card charge, without it), and says where it went; «Print» on the sale's document queues a copy;
//   - «Reprint» on a row of Sales queues a copy of that sale's receipt;
//   - «Print bill» of an open check queues the bill;
//   - «Print / PDF» of an invoice queues its A4 page for the system printer.
// Screenshots of each flow in the three viewports. What is made here is deleted, and the settings put back,
// after it.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, login, psql, shown } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { cleanInvoices, ensureIssuer, issuedIds, snapshotSeries } from './invoice-helpers';
import { flowShots } from './printing-helpers';
import { chargeByApi, cleanSales, drawerOff, newestSaleOf, restoreDrawer, type SaleOut, stamp } from './sale-helpers';

const RUN = stamp();
const TILL = `e2e Till ${RUN}`;
const OFFICE = `e2e Office ${RUN}`;
let coffee: Product;
let methods: Record<string, string>;
let till: string;
let office: string;
let settingsBefore: { open_drawer_on_sale: boolean; print_receipt_on_sale: boolean } | undefined;

interface Job {
  id: string;
  kind: string;
  document_type: string;
  reference: string;
  format: string;
  printer_name: string | null;
  open_drawer: boolean;
  source_app: string;
}

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  snapshotSeries();
  await ensureIssuer(context);
  coffee = await createProduct(context, { name: `E2E Coffee ${RUN}`, sku: `E2E-PRS-${RUN}`, price: 150 });
  const list = await api<{ rows: { id: string; type: string }[] }>(context, A, 'GET', '/sale/payment_methods');
  methods = Object.fromEntries(list.data.rows.map((row) => [row.type, row.id]));
  await drawerOff(context);
  const settings = await api<{ open_drawer_on_sale: boolean; print_receipt_on_sale: boolean }>(context, A, 'GET', '/printing/settings');
  expect(settings.status).toBe(200);
  settingsBefore = settings.data;
  const on = await api(context, A, 'POST', '/printing/settings', { open_drawer_on_sale: true, print_receipt_on_sale: true });
  expect(on.status, JSON.stringify(on.data)).toBe(200);
  const receipt = await api<{ id: string }>(context, A, 'POST', '/printing/printers', { name: TILL, kind: 'network', address: '10.0.0.88', usage: 'receipt' });
  expect(receipt.status, JSON.stringify(receipt.data)).toBe(201);
  till = receipt.data.id;
  const system = await api<{ id: string }>(context, A, 'POST', '/printing/printers', { name: OFFICE, kind: 'system', usage: 'receipt' });
  expect(system.status, JSON.stringify(system.data)).toBe(201);
  office = system.data.id;
  await context.close();
});

test.afterAll(() => {
  try {
    psql(`delete from printing_printjob where printer_id in (select id from printing_printer where name like 'e2e %')`);
    if (settingsBefore) {
      psql(
        `update printing_settings set open_drawer_on_sale = ${settingsBefore.open_drawer_on_sale}, ` +
          `print_receipt_on_sale = ${settingsBefore.print_receipt_on_sale}`,
      );
    }
    for (const column of ['receipt_printer_id', 'kitchen_printer_id', 'bar_printer_id', 'label_printer_id']) {
      psql(`update printing_settings set ${column} = null where ${column} in (select id from printing_printer where name like 'e2e %')`);
    }
    psql(`delete from printing_printer where name like 'e2e %'`);
    cleanInvoices();
  } finally {
    cleanSales();
    cleanInventory();
    restoreDrawer();
  }
});

async function jobsOf(context: BrowserContext, printer: string): Promise<Job[]> {
  const res = await api<{ rows: Job[] }>(context, A, 'GET', `/printing/jobs?printer_id=${printer}&limit=100`);
  expect(res.status).toBe(200);
  return res.data.rows;
}

/** The newest job of `printer` once there are `count`. */
async function newest(context: BrowserContext, printer: string, count: number): Promise<Job> {
  await expect.poll(async () => (await jobsOf(context, printer)).length).toBe(count);
  return (await jobsOf(context, printer))[0];
}

const sentTo = (page: Page, printer: string) => page.locator('ion-toast').filter({ hasText: `Sent to ${printer}.` }).last();

async function tillReady(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid^=pos-product-], [data-testid=pos-grid-empty]').first().waitFor({ state: 'visible' });
}

async function addCoffee(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=pos-search-trigger]').click();
  const search = page.locator('[data-testid=pos-search]');
  await search.locator('input').fill(coffee.sku);
  await search.locator(`[data-testid=pos-search-${coffee.id}]`).click();
  await expect(shown(page).locator('[data-testid=pos-total]')).toContainText(/1[.,]50/);
}

async function rowAction(page: Page, sale: SaleOut, action: string): Promise<void> {
  const hook = `sales-table-row-${sale.id}-${action}`;
  const inline = shown(page).locator(`[data-testid=${hook}]`);
  if ((await inline.count()) > 0 && (await inline.first().isVisible())) {
    await inline.first().click();
    return;
  }
  await shown(page).locator(`[data-testid=sales-table-row-${sale.id}-menu]`).first().click();
  await page.locator(`ion-popover [data-testid=${hook}]`).click();
}

test('PRINTING-F07, F13, F08: the charge queues its receipt (the drawer only with cash) and «Print» a copy', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  await tillReady(page);
  await addCoffee(page);
  await shown(page).locator('[data-testid=pos-charge]').click();
  const sheet = page.locator('[data-testid=sale-checkout-modal]');
  await expect(sheet).toBeVisible();
  await sheet.locator(`[data-testid=sale-checkout-method-${methods.cash}]`).click();
  await sheet.locator('[data-testid=sale-checkout-keypad-5]').click();
  await sheet.locator('[data-testid=sale-checkout-confirm]').click();
  await expect(sheet).toBeHidden();

  // In the charge's own transaction: the receipt, with the order to open the drawer (cash came in).
  await expect(sentTo(page, TILL)).toBeVisible();
  const cash = await newestSaleOf(context, coffee.sku);
  const receipt = await newest(context, till, 1);
  expect([receipt.document_type, receipt.format, receipt.source_app, receipt.reference, receipt.printer_name, receipt.open_drawer]).toEqual([
    'receipt',
    'receipt',
    'sale',
    cash.invoice_number || cash.number,
    TILL,
    true,
  ]);
  const documentModal = page.locator('[data-testid=sale-document-modal]');
  await expect(documentModal).toBeVisible();
  await flowShots(page, 'PRINTING-F07', async (p) => {
    await expect(p.locator('[data-testid=sale-document-modal] [data-testid=sale-document-print]')).toBeEnabled();
  });

  // «Print» on the document: the queue takes a copy («DUPLICATE»), not the screen.
  await documentModal.locator('[data-testid=sale-document-print]').click();
  const copy = await newest(context, till, 2);
  expect([copy.document_type, copy.reference, copy.open_drawer]).toEqual(['receipt', cash.invoice_number || cash.number, false]);
  await documentModal.locator('[data-testid=sale-document-close]').click();
  await expect(documentModal).toBeHidden();

  // A card charge: the receipt, but the drawer stays shut.
  const card = await chargeByApi(context, { lines: [{ product: coffee.sku, quantity: '1' }], payments: [{ method: 'card' }] });
  const byCard = await newest(context, till, 3);
  expect([byCard.reference, byCard.open_drawer]).toEqual([card.invoice_number || card.number, false]);
});

test('PRINTING-F08: «Reprint» on a row of Sales queues a copy of its receipt', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/sales');
  const sale = await chargeByApi(context, { lines: [{ product: coffee.sku, quantity: '2' }], payments: [{ method: 'card' }] });
  const before = (await jobsOf(context, till)).length;
  const row = shown(page).locator(`[data-testid=sales-table-row][data-id="${sale.id}"]`);
  await expect(row.first()).toBeVisible();
  await rowAction(page, sale, 'reprint');
  await expect(sentTo(page, TILL)).toBeVisible();
  const copy = await newest(context, till, before + 1);
  expect([copy.document_type, copy.reference, copy.source_app]).toEqual(['receipt', sale.invoice_number || sale.number, 'sale']);
  await flowShots(page, 'PRINTING-F08', async (p) => {
    await expect(shown(p).locator(`[data-testid=sales-table-row][data-id="${sale.id}"]`).first()).toBeVisible();
  });
});

test('PRINTING-F09: «Print bill» of an open check queues the bill, each press one', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  const before = (await jobsOf(context, till)).length;
  await tillReady(page);
  await addCoffee(page);
  await shown(page).locator('[data-testid=pos-prebill]').click();
  const bill = page.locator('ion-modal[data-testid=pos-prebill]');
  await expect(bill).toBeVisible();
  await expect(bill.locator('[data-testid=pos-prebill-print]')).toBeEnabled();
  await bill.locator('[data-testid=pos-prebill-print]').click();
  await expect(sentTo(page, TILL)).toBeVisible();
  const queued = await newest(context, till, before + 1);
  expect([queued.document_type, queued.source_app, queued.open_drawer]).toEqual(['prebill', 'sale', false]);
  await flowShots(page, 'PRINTING-F09', async (p) => {
    await expect(p.locator('ion-modal[data-testid=pos-prebill] [data-testid=pos-prebill-print]')).toBeEnabled();
  });
  await bill.locator('[data-testid=pos-prebill-close]').click();
  await expect(bill).toBeHidden();
});

test('INVOICE-F18 → PRINTING-F08: «Print / PDF» of an invoice queues its A4 page for the system printer', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/invoice/invoices');
  const created = await api<{ id: string; number: string }>(context, A, 'POST', '/invoice/invoices', {
    customer_name: `e2e Talleres ${RUN}`,
    customer_tax_id: 'B12345674',
    customer_address: 'Calle Luna 3, Madrid',
    lines: [{ description: 'e2e Course', quantity: '1', unit_price: 10000, tax_rate: '21' }],
  });
  expect(created.status, JSON.stringify(created.data)).toBe(201);
  issuedIds.add(created.data.id);
  await page.goto(`${A}/invoice/invoices/${created.data.id}`);
  const detail = shown(page);
  await expect(detail.locator('[data-testid=invoice-detail-title]')).toHaveText(`Invoice ${created.data.number}`);
  await detail.locator('[data-testid=invoice-detail-print]').click();
  await expect(sentTo(page, OFFICE)).toBeVisible();
  const page_ = await newest(context, office, 1);
  expect([page_.document_type, page_.format, page_.reference, page_.source_app, page_.printer_name]).toEqual([
    'invoice',
    'a4',
    created.data.number,
    'invoice',
    OFFICE,
  ]);
  // The receipt printer never takes an A4 page.
  expect((await jobsOf(context, till)).some((job) => job.format === 'a4')).toBe(false);
  await flowShots(page, 'PRINTING-F08-invoice', async (p) => {
    await expect(shown(p).locator('[data-testid=invoice-detail-print]')).toBeEnabled();
  });
});

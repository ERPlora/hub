import { execFileSync } from 'node:child_process';

// INVOICE-F04: the customer opens the page of her ticket's code without a session, in Spanish, asks for the full
// invoice that replaces it and gets the same one when she comes back; a code that cannot open a ticket says why.
import { type Browser, expect, type Page, test } from '@playwright/test';

import { A, HUB_DIR, psql } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { cleanInvoices, deliver, ensureIssuer, FLOW_VIEWPORTS, flowShots, snapshotSeries } from './invoice-helpers';
import { chargeByApi, cleanSales, type SaleOut, stamp } from './sale-helpers';
import { noHorizontalScroll, ownerPage } from './service-helpers';

const RUN = stamp();
const UNKNOWN = '20261119-9999-000000000000';
let product: Product;
let sale: SaleOut;
let code: string;
let ticketNumber: string;

function receiptCode(saleId: string): string {
  const source = [
    'import os',
    'from apps.sale.models import Sale',
    'from apps.sale.queries.receipt_codes import receipt_code',
    "print(receipt_code(Sale.objects.get(id=os.environ['RECEIPT_SALE_ID'])))",
  ].join('; ');
  return execFileSync('uv', ['run', 'python', 'manage.py', 'shell', '--hub', 'a', '-c', source], {
    cwd: HUB_DIR,
    encoding: 'utf8',
    env: { ...process.env, RECEIPT_SALE_ID: saleId },
  }).trim().split('\n').at(-1) ?? '';
}

/** A customer without a session, in Spanish, on her phone. */
async function visitor(browser: Browser) {
  const [phone] = FLOW_VIEWPORTS;
  const context = await browser.newContext({ viewport: { width: phone.width, height: phone.height }, locale: 'es-ES' });
  const page = await context.newPage();
  return { context, page };
}

/** At each size, `testid` painted and nothing scrolling sideways. */
const fitting = (testid: string) => async (page: Page) => {
  await expect(page.locator(`[data-testid=${testid}]`)).toBeVisible();
  await noHorizontalScroll(page, `${testid} at ${page.viewportSize()?.width ?? 0} px`);
};

const addressOf = (value: string): string => `${A}/p/a/invoice/${value}`;
const error = (page: Page) => page.locator('[data-testid=invoice-public-error]');

test.beforeAll(async ({ browser }) => {
  const { context } = await ownerPage(browser, '/invoice/invoices');
  snapshotSeries();
  await ensureIssuer(context);
  product = await createProduct(context, { name: `E2E Public invoice ${RUN}`, sku: `E2E-INV-P-${RUN}`, price: 1210, tax_category_key: 'product.generic' });
  sale = await chargeByApi(context, { lines: [{ product: product.sku, quantity: '1' }], payments: [{ method: 'card' }] });
  ticketNumber = (await deliver(context, 'sale.sale.completed', sale.id)).number;
  code = receiptCode(sale.id);
  expect(code).toContain(`${sale.number}-`);
  await context.close();
});

test.afterAll(() => {
  try {
    cleanInvoices();
  } finally {
    cleanSales();
    cleanInventory();
  }
});

test('a customer asks for the full invoice and reopens the same one', async ({ browser }) => {
  const { context, page } = await visitor(browser);
  try {
    await page.goto(addressOf(code));
    await expect(page.locator('[data-testid=invoice-public-ticket]')).toContainText(ticketNumber);
    await expect(page.locator('[data-testid=invoice-public-business]')).toContainText('e2e Peluquería Ana SL');
    await expect(page.locator('ion-menu-button')).toBeHidden();
    await flowShots(page, 'F04-public-form', fitting('invoice-public-form'));

    await page.locator('[data-testid=invoice-recipient-name] input').fill('Ana López');
    await page.locator('[data-testid=invoice-recipient-tax-id] input').fill('123');
    await page.locator('[data-testid=invoice-recipient-address] input').fill('Calle Sol 1, Madrid');
    await page.locator('[data-testid=invoice-public-submit]').click();
    const taxId = page.locator('[data-testid=invoice-recipient-tax-id]');
    await expect(taxId).toHaveClass(/ion-invalid/);
    await expect(taxId.locator('.error-text')).toHaveText('Ese NIF no es válido.');
    await expect(page.locator('[data-testid=invoice-public-form-error]')).toContainText('Revisa los datos marcados.');

    await taxId.locator('input').fill('12345678Z');
    await expect(taxId).not.toHaveClass(/ion-invalid/);
    await page.locator('[data-testid=invoice-public-submit]').click();
    await expect(page.locator('[data-testid=invoice-public-ready]')).toContainText('Tu factura está lista.');
    await expect(page.locator('[data-testid=invoice-public-number]')).toContainText('Factura ');
    await expect(page.locator('[data-testid=invoice-public-invoice]')).toContainText('Ana López');
    await expect(page.locator('[data-testid=invoice-detail-total]')).toContainText('12,10');
    // The A4 that «Imprimir / PDF» prints, with the customer and VeriFactu's QR.
    await expect(page.locator('[data-testid=invoice-paper-bill-to]')).toContainText('Ana López');
    await expect(page.locator('[data-testid=invoice-paper-qr] img')).toHaveCount(1);
    expect(psql(`select count(*) from invoice_invoice where source_sale_id = '${sale.id}'`)).toBe('2');
    await flowShots(page, 'F04-public-issued', fitting('invoice-public-invoice'));

    await page.reload();
    await expect(page.locator('[data-testid=invoice-public-already]')).toContainText('Ya pediste esta factura.');
    await expect(page.locator('[data-testid=invoice-public-form]')).toHaveCount(0);
    expect(psql(`select count(*) from invoice_invoice where source_sale_id = '${sale.id}'`)).toBe('2');
  } finally {
    await context.close();
  }
});

test('an expired code sends the customer to the business', async ({ browser }) => {
  const { context, page } = await visitor(browser);
  try {
    psql(`update sale_sale set created_at = created_at - interval '5 years' where id = '${sale.id}'`);
    await page.goto(addressOf(code));
    await expect(error(page)).toContainText('Este código ha caducado: pide la factura en el establecimiento.');
    await expect(page.locator('[data-testid=invoice-public-retry]')).toHaveCount(0);
  } finally {
    psql(`update sale_sale set created_at = created_at + interval '5 years' where id = '${sale.id}'`);
    await context.close();
  }
});

test('a code that opens nothing says so without showing a ticket', async ({ browser }) => {
  const { context, page } = await visitor(browser);
  try {
    await page.goto(addressOf(UNKNOWN));
    await expect(error(page)).toContainText('Este código no abre ningún tique.');
    await expect(page.locator('[data-testid=invoice-public-retry]')).toHaveCount(0);
    await expect(page.locator('[data-testid=invoice-public-ticket]')).toHaveCount(0);
    await flowShots(page, 'F04-public-not-found', fitting('invoice-public-error'));
  } finally {
    await context.close();
  }
});

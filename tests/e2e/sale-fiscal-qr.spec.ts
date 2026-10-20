// flow: SALE-F29 — the document of a charged sale carries VeriFactu's QR (VERIFACTU-F19, sales#411), against the real
// Invoicing and VeriFactu, no mocks: the charge issues its ticket and VeriFactu seals its record in that emission (in
// the AEAT's testing environment: nothing is sent); in Sales, «Document» shows the paper with «Tax QR:», the QR,
// «VERI*FACTU» and how to check the receipt at the AEAT. In 390×844, 834×1194 and 1440×900. What a run creates — its
// product `E2E-SQR-<run>`, its sale, its ticket and VeriFactu's record of it — is deleted after it.
import { expect, type Page, test } from '@playwright/test';

import { A, api, login, shown } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { ensureIssuer, snapshotSeries } from './invoice-helpers';
import { chargeByApi, cleanSales, drawerOff, restoreDrawer, shots, stamp } from './sale-helpers';

const RUN = stamp();
let product: Product;

interface FiscalRecord {
  qr_url: string;
  qr_svg: string;
  csv: string;
  environment: string;
}

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/sales');
  snapshotSeries();
  await ensureIssuer(context);
  await drawerOff(context);
  product = await createProduct(context, { name: `E2E QR ${RUN}`, sku: `E2E-SQR-${RUN}`, price: 1210, tax_category_key: 'product.generic' });
  await context.close();
});

test.afterAll(() => {
  try {
    cleanSales();
    cleanInventory();
  } finally {
    restoreDrawer();
  }
});

async function documentReady(page: Page): Promise<void> {
  await page.locator('[data-testid=sale-document-modal] [data-testid=sale-receipt-qr] img').waitFor({ state: 'visible' });
}

test('SALE-F29: the ticket of a charged sale carries VeriFactu’s QR, «VERI*FACTU» and how to check it', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/sales');
  const sale = await chargeByApi(context, { lines: [{ product: product.sku }], payments: [{ method: 'card' }] });
  expect(sale.invoice_id, 'the charge issued its ticket').toBeTruthy();
  const found = await api<{ record: FiscalRecord | null }>(context, A, 'GET', `/verifactu/records/by_invoice?invoice_id=${sale.invoice_id}`);
  expect(found.status).toBe(200);
  const record = found.data.record;
  expect(record, 'VeriFactu sealed its record in the emission').not.toBeNull();
  // The AEAT's testing environment only: nothing here may point at the real one.
  expect(record?.environment).toBe('testing');
  expect(record?.qr_url).toContain('https://prewww2.aeat.es/');

  await shown(page).locator('[data-testid=sales-table-search] input').fill(sale.number);
  await shown(page).locator(`[data-testid=sales-table-row-${sale.id}-document]`).first().click();
  const document = page.locator('[data-testid=sale-document-modal]');
  const qr = document.locator('[data-testid=sale-receipt-qr]');
  await expect(qr).toBeVisible();
  await expect(qr).toContainText('Tax QR:');
  await expect(qr).toContainText('VERI*FACTU');
  await expect(document.locator('[data-testid=sale-receipt-qr-hint]')).toHaveText(
    record?.csv ? `CSV: ${record.csv}` : 'Scan it to check this receipt at the AEAT',
  );
  await expect(qr.locator('img')).toHaveAttribute('src', record?.qr_svg ?? '');
  await expect(document.locator('[data-testid=sale-receipt-number]')).toContainText(sale.invoice_number);
  await shots(page, 'APP-SALE-SALE-F29', documentReady, { width: 1440, height: 900 });
  await document.locator('[data-testid=sale-document-close]').click();
  await expect(qr).toBeHidden();
});

// flow: SALE-F29 — the document of a charged sale carries VeriFactu's QR (VERIFACTU-F19), against the real
// Invoicing and VeriFactu, no mocks: the charge issues its ticket and VeriFactu seals its record in that emission (in
// the AEAT's testing environment: nothing is sent); in Sales, «Document» shows the paper with «Tax QR:», the QR,
// «VERI*FACTU» and how to check the receipt at the AEAT. In 390×844, 834×1194 and 1440×900. What a run creates — its
// product `E2E-SQR-<run>`, its sale, its ticket and VeriFactu's record of it — is deleted after it.
import { type Browser, expect, type Page, test } from '@playwright/test';

import { A, api, capture, login, shown } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { ensureIssuer, snapshotSeries } from './invoice-helpers';
import { chargeByApi, cleanSales, drawerOff, numberRow, restoreDrawer, shots, stamp } from './sale-helpers';

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

/** The paper at the sizes a person charges and reads it: desk, tablet and phone (hub#695). */
const SIZES = [
  { label: '1440x900', width: 1440, height: 900 },
  { label: '820x1180', width: 820, height: 1180 },
  { label: '375x667', width: 375, height: 667 },
];

/** The owner on `a` in `language`, on «Sales». */
async function salesIn(browser: Browser, language: 'en' | 'es'): Promise<Page> {
  const context = await browser.newContext({ baseURL: A, locale: language === 'es' ? 'es-ES' : 'en-US' });
  const page = await context.newPage();
  await login(page, A, '/sale/sales');
  await context.addCookies([{ name: 'django_language', value: language, domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}/sale/sales`);
  await expect(page.locator('html')).toHaveAttribute('lang', new RegExp(`^${language}`));
  return page;
}

test('SALE-F29 (hub#695): the ticket number never splits — whole on one line, the date beside it or under it, on screen and on paper', async ({ browser }) => {
  let sale: Awaited<ReturnType<typeof chargeByApi>> | null = null;
  for (const language of ['es', 'en'] as const) {
    const page = await salesIn(browser, language);
    if (!sale) {
      sale = await chargeByApi(page.context(), { lines: [{ product: product.sku }], payments: [{ method: 'card' }] });
      // The ticket's series number, the long one: «TICKET-2026-000004».
      expect(sale.invoice_number).toMatch(/^TICKET-\d{4}-\d{6}$/);
    }
    await shown(page).locator('[data-testid=sales-table-search] input').fill(sale.number);
    await shown(page).locator(`[data-testid=sales-table-row-${sale.id}-document]`).first().click();
    const paper = page.locator('[data-testid=sale-document-modal] [data-testid=sale-receipt]');
    await expect(paper.locator('[data-testid=sale-receipt-number]')).toContainText(sale.invoice_number);
    await documentReady(page);
    for (const size of SIZES) {
      await page.setViewportSize({ width: size.width, height: size.height });
      await documentReady(page);
      const row = await numberRow(paper);
      expect(row.numberLines, `${language} ${size.label}: «${sale.invoice_number}» on one line`).toBe(1);
      expect(row.dateLines, `${language} ${size.label}: the date and time on one line`).toBe(1);
      expect(row.dateBeside || row.dateUnder, `${language} ${size.label}: the date beside the number or right under it`).toBe(true);
      expect(row.overflow, `${language} ${size.label}: nothing past the paper`).toBe(0);
      await capture(page, `APP-SALE-SALE-F29-number-${language}-${size.label}`);
    }
    // However little room the paper had, the number itself would stay whole: only its label may go above it.
    const squeezed = await paper.evaluate((el: HTMLElement) => {
      const width = el.style.width;
      el.style.width = '45mm';
      const strong = el.querySelector('[data-testid=sale-receipt-number] strong')!;
      const range = document.createRange();
      range.selectNodeContents(strong);
      const tops = [...range.getClientRects()].filter((box) => box.width > 0).map((box) => Math.round(box.top));
      el.style.width = width;
      return new Set(tops).size;
    });
    expect(squeezed, `${language}: on a 45 mm paper «${sale.invoice_number}» still on one line`).toBe(1);

    // On paper: the copy `printPaper` hands the browser, laid out for print (the print dialog itself stubbed).
    await page.evaluate(() => {
      const w = window as unknown as { __printed?: number; print: () => void };
      w.__printed = 0;
      w.print = () => {
        w.__printed! += 1;
      };
    });
    await page.locator('[data-testid=sale-document-print]').click();
    await expect.poll(() => page.evaluate(() => (window as unknown as { __printed: number }).__printed), {
      message: 'the browser printed the paper (no receipt printer queued it)',
    }).toBe(1);
    await page.emulateMedia({ media: 'print' });
    const printed = page.locator('body > .sale-print-root [data-testid=sale-receipt]');
    await expect(printed).toBeVisible();
    const row = await numberRow(printed);
    expect(row.numberLines, `${language} on paper: «${sale.invoice_number}» on one line`).toBe(1);
    expect(row.dateLines, `${language} on paper: the date and time on one line`).toBe(1);
    expect(row.dateBeside || row.dateUnder, `${language} on paper: the date beside the number or right under it`).toBe(true);
    expect(row.overflow, `${language} on paper: nothing past the paper`).toBe(0);
    await capture(page, `APP-SALE-SALE-F29-number-${language}-print`);
    await page.emulateMedia({ media: 'screen' });
    await page.context().close();
  }
});

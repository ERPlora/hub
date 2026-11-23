// INVOICE-F21 and INVOICE-F18 in the browser: the owner turns on «Registered in the ROI (intra-EU operations)» in
// Invoicing → Issuer and saves it; from then on an invoice's paper prints «Tax ID: ES…» while VeriFactu's record keeps
// the bare tax ID. What this file creates is deleted after it, and the hub's issuer and numbering are left as found.
import { expect, test } from '@playwright/test';

import { A, login, psql, saveSessionForTheSweep, shown } from './helpers';
import { cleanInvoices, ensureIssuer, flowShots, issueManualInvoice, issuerNow, type IssuerOut, restoreIssuer, snapshotSeries } from './invoice-helpers';
import { toastSaying } from './toast-helpers';

let original: IssuerOut;

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/invoice/issuer');
  snapshotSeries();
  original = await issuerNow(context);
  await ensureIssuer(context);
  await context.close();
});

test.afterAll(() => {
  cleanInvoices();
});

test('INVOICE-F21, F18: the owner marks the ROI on the issuer and the invoice prints the EU VAT number', async ({ page, context }) => {
  await page.setViewportSize({ width: 1280, height: 860 });
  await login(page, A, '/invoice/issuer');
  await saveSessionForTheSweep(context);
  const form = shown(page);
  const roi = form.locator('[data-testid=invoice-issuer-intra-eu-operator]');
  await expect(roi).toContainText('Registered in the ROI (intra-EU operations)');
  await expect(roi).not.toHaveJSProperty('checked', true);
  await roi.click();
  await expect(roi).toHaveJSProperty('checked', true);
  await form.locator('[data-testid=invoice-issuer-save]').click();
  await expect(toastSaying(page, 'Issuer saved.')).toBeVisible();
  const saved = await issuerNow(context);
  expect([saved.intra_eu_operator, saved.vat_number]).toEqual([true, `ES${saved.tax_id}`]);
  await flowShots(page, 'INVOICE-F21-roi', async (p) => {
    await expect(shown(p).locator('[data-testid=invoice-issuer-intra-eu-operator]')).toBeVisible();
  });

  try {
    const created = await issueManualInvoice(context);
    await page.goto(`${A}/invoice/invoices/${created.id}`);
    // The detail names the issuer as the document does; the A4 it prints (hidden until printing) says «Tax ID: ES…».
    await expect(shown(page).locator('[data-testid=invoice-detail-issuer]')).toContainText(`(ES${saved.tax_id})`);
    await expect(shown(page).locator('[data-testid=invoice-paper-issuer]')).toContainText(`Tax ID: ES${saved.tax_id}`);
    expect(psql(`select issuer_nif from verifactu_record where invoice_id = '${created.id}'`)).toBe(saved.tax_id);
    await flowShots(page, 'INVOICE-F17-roi', async (p) => {
      await expect(shown(p).locator('[data-testid=invoice-detail-issuer]')).toBeVisible();
    });
  } finally {
    await restoreIssuer(context, original);
  }
});

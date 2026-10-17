// The manual invoice of a business with a tax territory (INVOICE-F03 with TAX-F11;
// FIX-INVOICE-MANUAL-TAX-LABEL-REGION): the rate of a typed line is named by the tax of the business's
// territory and starts at its general rate. In the Canary Islands, with an IGIC 7 % rule on the generic
// goods, «New manual invoice» says «IGIC %» and proposes 7; the invoice is declared IGIC 7 % and its card
// names the column «IGIC %». On the peninsula it still says «VAT %» and proposes 21. The dialog is seen at
// 390×844, 834×1112 and 1440×900 (`FIX-INVOICE-MANUAL-TAX-LABEL-REGION-<width>.png`). What the run makes is
// deleted after it, and the business goes back to the whole country.
// flow: ninguno — FIX de INVOICE-F03 (factura manual): en Canarias, Ceuta o Melilla la columna del tipo dice «IVA %» y propone 21
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, login, psql, shot, shown } from './helpers';
import { cleanInvoices, ensureIssuer, invoiceOf, issuedIds, openDialog, snapshotSeries } from './invoice-helpers';
import { stamp } from './sale-helpers';
import { createRule, FLOW_VIEWPORTS, horizontalOverflow } from './tax-helpers';

const RUN = stamp();
/** The Canary rule of the generic goods this run plants (the catalogue ships none: TAX-F11). */
const CANARY_GENERIC = "region_code = 'ES-CN' and category_id in (select id from tax_taxcategory where key = 'product.generic')";

interface Breakdown {
  tax: string;
  rate: string;
}

/** The business's tax territory, as Taxes → Settings keeps it ('' = the whole country). */
async function territory(context: BrowserContext, region: string): Promise<void> {
  const res = await api(context, A, 'POST', '/tax/settings', { region_code: region || null });
  expect(res.status, `territory ${region || 'whole country'}`).toBe(200);
}

/** The business back to the whole country, and the run's Canary rule gone: the other specs sell at the VAT. */
function wholeCountry(): void {
  psql(["update tax_taxsettings set region_code = ''", `delete from tax_taxrule where ${CANARY_GENERIC}`].join('; '));
}

test.beforeAll(async ({ browser }) => {
  snapshotSeries();
  wholeCountry();
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/invoice/invoices');
  await ensureIssuer(context);
  await createRule(context, { country_code: 'ES', region_code: 'ES-CN', tax_category_key: 'product.generic', rate_pct: 7, tax_type: 'igic' });
  await context.close();
});

test.afterAll(() => {
  try {
    cleanInvoices();
  } finally {
    wholeCountry();
  }
});

/** «New manual invoice» opened from the list. */
async function newInvoice(page: Page): Promise<Locator> {
  await page.goto('/invoice/invoices');
  await shown(page).locator('[data-testid=invoice-list-add]').click();
  const dialog = openDialog(page, 'invoice-create');
  await expect(dialog).toBeVisible();
  return dialog;
}

test('INVOICE-F03 in the Canary Islands: the rate is «IGIC %», starts at 7 and the invoice declares IGIC', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/invoice/invoices');
  await territory(context, 'ES-CN');
  const customer = `e2e Cliente Canarias ${RUN}`;

  const dialog = await newInvoice(page);
  const rate = dialog.locator('[data-testid=invoice-line-1-tax-rate]');
  await expect(rate).toHaveJSProperty('label', 'IGIC %');
  await expect(rate.locator('input')).toHaveValue('7');
  // «+ Line» starts the new line at the same rate; the cross takes it away again.
  await dialog.locator('[data-testid=invoice-lines-add]').click();
  await expect(dialog.locator('[data-testid=invoice-line-2-tax-rate] input')).toHaveValue('7');
  await dialog.locator('[data-testid=invoice-line-2-remove]').click();
  await expect(dialog.locator('[data-testid=invoice-line-2]')).toHaveCount(0);

  await dialog.locator('[data-testid=invoice-recipient-name] input').fill(customer);
  await dialog.locator('[data-testid=invoice-recipient-tax-id] input').fill('12345678Z');
  await dialog.locator('[data-testid=invoice-recipient-address] input').fill('Calle Triana 5, 35002 Las Palmas');
  await dialog.locator('[data-testid=invoice-line-1-description] input').fill(`e2e Asesoría ${RUN}`);
  await dialog.locator('[data-testid=invoice-line-1-price] input').fill('100');

  for (const vp of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    const open = openDialog(page, 'invoice-create');
    await expect(open.locator('[data-testid=invoice-line-1-tax-rate]')).toHaveJSProperty('label', 'IGIC %');
    await open.locator('[data-testid=invoice-line-1-tax-rate]').scrollIntoViewIfNeeded();
    await expect.poll(() => horizontalOverflow(page), `dialog at ${vp.label}: sideways scroll`).toBeLessThanOrEqual(1);
    await page.screenshot({ path: shot(`FIX-INVOICE-MANUAL-TAX-LABEL-REGION-${vp.label}`) });
  }
  await page.setViewportSize({ width: 1440, height: 900 });

  await openDialog(page, 'invoice-create').locator('[data-testid=invoice-create-submit]').click();
  await expect(openDialog(page, 'invoice-create')).toBeHidden();

  // Server-side evidence: one invoice for the run's customer, 100.00 + IGIC 7 % = 107.00, declared as IGIC.
  const found = await api<{ rows: { id: string }[] }>(context, A, 'GET', `/invoice/invoices?search=${encodeURIComponent(customer)}&limit=10`);
  expect(found.data.rows, `one invoice for ${customer}`).toHaveLength(1);
  issuedIds.add(found.data.rows[0].id);
  const invoice = await invoiceOf(context, found.data.rows[0].id);
  const breakdown = (invoice as unknown as { tax_breakdown: Breakdown[] }).tax_breakdown;
  expect([invoice.total_amount, breakdown.map((entry) => [entry.tax, entry.rate])]).toEqual([10700, [['igic', '7.00']]]);

  // Its card names the rate column by the tax it declares, and the breakdown says IGIC 7 %.
  await page.goto(`/invoice/invoices/${invoice.id}`);
  const detail = shown(page);
  await expect(detail.locator('[data-testid=invoice-detail-lines] th').nth(4)).toHaveText('IGIC %');
  await expect(detail.locator('[data-testid=invoice-detail-tax-label]').first()).toContainText('IGIC 7');
  await expect(detail.locator('[data-testid=invoice-detail-total]')).toContainText(/107[.,]00/);
});

test('INVOICE-F03 on the peninsula: the rate is still «VAT %» and starts at 21', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/invoice/invoices');
  await territory(context, '');

  const dialog = await newInvoice(page);
  const rate = dialog.locator('[data-testid=invoice-line-1-tax-rate]');
  await expect(rate).toHaveJSProperty('label', 'VAT %');
  await expect(rate.locator('input')).toHaveValue('21');
  await dialog.locator('[data-testid=invoice-create-cancel]').click();
  await expect(openDialog(page, 'invoice-create')).toBeHidden();
});

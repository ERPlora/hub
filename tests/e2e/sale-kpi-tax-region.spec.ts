// The tax figure of Sales → Sales of a business with a tax territory (SALE-F28 with TAX-F11;
// FIX-SALE-KPI-TAX-LABEL-REGION): the figure is named by the tax the business's sales are declared with,
// its territory's. In the Canary Islands, with an IGIC 7 % rule on the generic goods, a sale charged at the
// till is declared IGIC 7 % and the figures of the period say «IGIC», never «VAT»; back to the whole
// country, the open screen renames it «VAT» by itself (live), and on the peninsula it still says «VAT». The
// figures are seen at 390×844, 834×1112 and 1440×900 (`FIX-SALE-KPI-TAX-LABEL-REGION-<width>.png`). What
// the run makes is deleted after it, and the business goes back to the whole country.
// flow: ninguno — FIX de SALE-F28 (cifras de ventas): en Canarias, Ceuta o Melilla la cifra de impuestos dice «IVA»
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, login, psql, shot, shown } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { snapshotSeries } from './invoice-helpers';
import { cleanSales, drawerOff, newestSaleOf, restoreDrawer, stamp } from './sale-helpers';
import { createRule, FLOW_VIEWPORTS, horizontalOverflow } from './tax-helpers';

const RUN = stamp();
/** The Canary rule of the generic goods this run plants (the catalogue ships none: TAX-F11). */
const CANARY_GENERIC = "region_code = 'ES-CN' and category_id in (select id from tax_taxcategory where key = 'product.generic')";
let shirt: Product;

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
  await login(page, A, '/sale/sales');
  // Cash without a cash session: the drawer's lock is sale-cash-gate.spec.ts's.
  await drawerOff(context);
  await createRule(context, { country_code: 'ES', region_code: 'ES-CN', tax_category_key: 'product.generic', rate_pct: 7, tax_type: 'igic' });
  shirt = await createProduct(context, { name: `E2E Canary KPI shirt ${RUN}`, sku: `E2E-KPI-${RUN}`, price: 1070, tax_category_key: 'product.generic' });
  await context.close();
});

test.afterAll(() => {
  try {
    cleanSales();
    cleanInventory();
    restoreDrawer();
  } finally {
    wholeCountry();
  }
});

/** Sales → Sales with its figures read (no figure is «—» any more). */
async function figures(page: Page) {
  await page.goto('/sale/sales');
  const kpis = shown(page).locator('[data-testid=sales-kpis]');
  await expect(kpis).toBeVisible();
  const label = kpis.locator('[data-testid=sales-kpi-tax-label]');
  const value = kpis.locator('[data-testid=sales-kpi-tax]');
  await expect(value).toHaveText(/\d/);
  return { kpis, label, value };
}

test('SALE-F28 in the Canary Islands: a sale charged at the till is declared IGIC and the figure says «IGIC»', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  await territory(context, 'ES-CN');

  // The till, as a cashier sells: the shirt found by its SKU, charged in cash with an 11 € note.
  await page.goto('/sale/pos');
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid=pos-search-trigger]').click();
  const search = page.locator('[data-testid=pos-search]');
  await search.locator('input').fill(shirt.sku);
  await search.locator(`[data-testid=pos-search-${shirt.id}]`).click();
  await expect(shown(page).locator('[data-testid=pos-total]')).toContainText(/10[.,]70/);
  await shown(page).locator('[data-testid=pos-charge]').click();
  const sheet = page.locator('[data-testid=sale-checkout-modal]');
  await expect(sheet).toBeVisible();
  for (const key of ['1', '1']) await sheet.locator(`[data-testid=sale-checkout-keypad-${key}]`).click();
  await sheet.locator('[data-testid=sale-checkout-confirm]').click();
  await expect(sheet).toBeHidden();

  // Server-side evidence: the sale is declared at the Canary IGIC 7 %, 10.00 + 0.70.
  const sale = await newestSaleOf(context, shirt.sku);
  expect([sale.subtotal, sale.tax_total, sale.total]).toEqual([1000, 70, 1070]);
  expect(sale.lines.map((line) => line.tax_rate)).toEqual(['7.00']);

  // Sales → Sales: the tax figure is named «IGIC», at every width, with nothing pushed sideways.
  const { label } = await figures(page);
  await expect(label).toHaveText('IGIC');
  for (const vp of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    const kpis = shown(page).locator('[data-testid=sales-kpis]');
    await expect(kpis.locator('[data-testid=sales-kpi-tax-label]')).toHaveText('IGIC');
    await expect(kpis).not.toContainText(/\bVAT\b|\bIVA\b/);
    await expect.poll(() => horizontalOverflow(page), `figures at ${vp.label}: sideways scroll`).toBeLessThanOrEqual(1);
    // On a phone the figures are one row that scrolls sideways: the tax is brought into view.
    await kpis.locator('[data-testid=sales-kpi-tax]').scrollIntoViewIfNeeded();
    await page.screenshot({ path: shot(`FIX-SALE-KPI-TAX-LABEL-REGION-${vp.label}`) });
  }
  await page.setViewportSize({ width: 1440, height: 900 });

  // Back to the whole country with the screen open: the figure is renamed «VAT» by itself (live).
  await territory(context, '');
  await expect(shown(page).locator('[data-testid=sales-kpi-tax-label]')).toHaveText('VAT');
});

test('SALE-F28 on the peninsula: the tax figure still says «VAT»', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/sales');
  await territory(context, '');
  const { label } = await figures(page);
  await expect(label).toHaveText('VAT');
});

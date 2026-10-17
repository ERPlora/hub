// A business of the Canary Islands with a category that only has its national VAT (TAX-F11, TAX-F04;
// FIX-TAX-REGION-NATIONAL-FALLBACK): the owner keeps «Canary Islands (IGIC)» in Taxes → Settings, the category has
// the national 21 % VAT and no IGIC rule, and the till never charges it at the VAT — as a category without any
// rule in the peninsula, the cart has no total and «Charge» says why and cannot charge. The refusal is seen at
// 390×844, 834×1112 and 1440×900 (`FIX-TAX-REGION-NATIONAL-FALLBACK-<width>.png`). What the run makes is deleted
// after it, and the business goes back to the whole country.
import { expect, type Page, test } from '@playwright/test';

import { A, login, psql, shot, shown } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { snapshotSeries } from './invoice-helpers';
import { cleanSales, drawerOff, newestSaleOf, restoreDrawer, stamp } from './sale-helpers';
import { cleanUp as cleanTaxes, createRule, FLOW_VIEWPORTS, freshCategory, horizontalOverflow, pickSelect } from './tax-helpers';

const RUN = stamp();
let shirt: Product;

/** The business back to the whole country: the other specs of the stack sell at the national VAT. */
function wholeCountry(): void {
  psql("update tax_taxsettings set region_code = ''");
}

test.beforeAll(async ({ browser }) => {
  snapshotSeries();
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/tax/settings');
  // Cash without a cash session: the drawer's lock is sale-cash-gate.spec.ts's.
  await drawerOff(context);
  const key = await freshCategory(context, 'novat');
  // Only the national VAT: no IGIC rule for this category.
  await createRule(context, { country_code: 'ES', tax_category_key: key, rate_pct: 21 });
  shirt = await createProduct(context, { name: `E2E VAT-only shirt ${RUN}`, sku: `E2E-NOVAT-${RUN}`, price: 1210, tax_category_key: key });
  await context.close();
});

test.afterAll(() => {
  wholeCountry();
  cleanSales();
  cleanInventory();
  cleanTaxes();
  restoreDrawer();
});

async function settingsReady(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=tax-settings-form]').waitFor({ state: 'visible' });
}

// flow: ninguno — FIX fiscal: en Canarias/Ceuta/Melilla sin regla propia se cobraría el IVA nacional (TAX-F11, TAX-F04)
test('FIX-TAX-REGION-NATIONAL-FALLBACK: in the Canary Islands a category with only the national VAT is not charged at the VAT, and the till says why', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/tax/settings');
  await settingsReady(page);
  const form = shown(page).locator('[data-testid=tax-settings-form]');
  await pickSelect(page, form.locator('[data-testid=tax-settings-region]'), 'Canary Islands (IGIC)');
  await form.locator('[data-testid=tax-settings-save]').click();
  await expect(page.locator('ion-toast').filter({ hasText: 'Tax region saved.' })).toBeVisible();
  await expect(form.locator('[data-testid=tax-settings-save]')).toHaveAttribute('aria-disabled', 'true');

  // The till, as a cashier sells: the product found by its SKU. Its 21 % VAT never prices it here: no total.
  await page.goto('/sale/pos');
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid=pos-search-trigger]').click();
  const search = page.locator('[data-testid=pos-search]');
  await search.locator('input').fill(shirt.sku);
  await search.locator(`[data-testid=pos-search-${shirt.id}]`).click();
  await expect(shown(page).locator('[data-testid=pos-total]')).toHaveText('—');

  // «Charge»: the server's reason, in sight, and nothing to confirm.
  await shown(page).locator('[data-testid=pos-charge]').click();
  const sheet = page.locator('[data-testid=sale-checkout-modal]');
  await expect(sheet).toBeVisible();
  const refusal = sheet.locator('[data-testid=sale-checkout-read-error]');
  await expect(refusal).toContainText(`«${shirt.name}» cannot be charged: no tax rule applies to its tax category`);
  await expect(sheet.locator('[data-testid=sale-checkout-confirm]')).toHaveAttribute('aria-disabled', 'true');
  await expect(sheet).not.toContainText(/12[.,]10/);

  for (const vp of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(refusal, `refusal at ${vp.label}`).toBeInViewport();
    await expect.poll(() => horizontalOverflow(page), `checkout at ${vp.label}: sideways scroll`).toBeLessThanOrEqual(1);
    await page.screenshot({ path: shot(`FIX-TAX-REGION-NATIONAL-FALLBACK-${vp.label}`) });
  }

  // Server-side evidence: nothing was charged, at the VAT or at anything else.
  await expect(newestSaleOf(context, shirt.sku)).rejects.toThrow(`no recent sale sold ${shirt.sku}`);
});

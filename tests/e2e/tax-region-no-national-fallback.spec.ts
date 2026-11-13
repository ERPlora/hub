// A business of the Canary Islands with a category that only has its national VAT (TAX-F11, TAX-F04): the
// owner keeps «Canary Islands (IGIC)» in Taxes → Settings, the category has the national 21 % VAT and no IGIC rule,
// and the till never charges it at the VAT — as a category without any rule in the peninsula, the cart has no total
// and «Charge» says why and cannot charge. The refusal is seen at 390×844, 834×1112 and 1440×900. What the run makes
// is deleted after it, and the business goes back to the whole country.
import { expect, test } from '@playwright/test';

import { shot, shown } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import {  } from './invoice-helpers';
import { cleanSales, newestSaleOf, restoreDrawer, stamp } from './sale-helpers';
import { cleanUp as cleanTaxes, createRule, FLOW_VIEWPORTS, freshCategory, horizontalOverflow, pickSelect, regionSaleContext, taxSettingsForm, wholeCountry } from './tax-helpers';

const RUN = stamp();
let shirt: Product;

test.beforeAll(async ({ browser }) => {
  const context = await regionSaleContext(browser);
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

// flow: TAX-F11, TAX-F04 — in the Canary Islands, Ceuta or Melilla a category without a rule of its own is never
// charged at the national VAT
test('in the Canary Islands a category with only the national VAT is not charged at the VAT, and the till says why', async ({ page, context }) => {
  const form = await taxSettingsForm(page);
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

// A business of the Canary Islands, end to end (TAX-F11, pm#629 VF-17; FIX-TAX-REGION-IGIC): the owner keeps
// «Canary Islands (IGIC)» in Taxes → Settings, the category has its national 21 % VAT and a Canary IGIC 7 % rule,
// and the till charges the product at the IGIC 7 %: the ticket and its breakdown say IGIC 7 %, never VAT. The
// settings screen is seen at 390×844, 834×1112 and 1440×900 (`FIX-TAX-REGION-IGIC-<width>.png`). What the run
// makes is deleted after it, and the business goes back to the whole country.
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
  const key = await freshCategory(context, 'igic');
  await createRule(context, { country_code: 'ES', tax_category_key: key, rate_pct: 21 });
  await createRule(context, { country_code: 'ES', region_code: 'ES-CN', tax_category_key: key, rate_pct: 7, tax_type: 'igic' });
  shirt = await createProduct(context, { name: `E2E Canary shirt ${RUN}`, sku: `E2E-IGIC-${RUN}`, price: 1070, tax_category_key: key });
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

// flow: TAX-F11 (Montar un negocio de Canarias, Ceuta o Melilla) — FIX: el negocio no guarda su país ni su región y Ventas cobra sin ella
test('TAX-F11: a business of the Canary Islands keeps its region and the till charges the IGIC 7 %, not the VAT', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/tax/settings');
  await settingsReady(page);
  const form = shown(page).locator('[data-testid=tax-settings-form]');
  await expect(form.locator('[data-testid=tax-settings-country]')).toContainText('Spain');
  await pickSelect(page, form.locator('[data-testid=tax-settings-region]'), 'Canary Islands (IGIC)');
  await form.locator('[data-testid=tax-settings-save]').click();
  await expect(page.locator('ion-toast').filter({ hasText: 'Tax region saved.' })).toBeVisible();
  // Kept: nothing left to save (ion-button says it with aria-disabled).
  await expect(form.locator('[data-testid=tax-settings-save]')).toHaveAttribute('aria-disabled', 'true');

  for (const vp of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await settingsReady(page);
    await expect(form.locator('[data-testid=tax-settings-region]')).toContainText('Canary Islands (IGIC)');
    await expect.poll(() => horizontalOverflow(page), `settings at ${vp.label}: sideways scroll`).toBeLessThanOrEqual(1);
    await page.screenshot({ path: shot(`FIX-TAX-REGION-IGIC-${vp.label}`) });
  }

  // The till, as a cashier sells: the product found by its SKU, charged in cash with an 11 € note.
  await page.setViewportSize({ width: 1440, height: 900 });
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
  await expect(sheet.locator('[data-testid=sale-checkout-total]')).toContainText(/10[.,]70/);
  for (const key of ['1', '1']) await sheet.locator(`[data-testid=sale-checkout-keypad-${key}]`).click();
  await expect(sheet.locator('[data-testid=sale-checkout-change]')).toContainText(/0[.,]30/);
  await sheet.locator('[data-testid=sale-checkout-confirm]').click();
  await expect(sheet).toBeHidden();

  // The ticket: its tax row is the IGIC at 7 %, and no VAT at all.
  const receipt = page.locator('[data-testid=sale-document-modal] [data-testid=sale-receipt]');
  await expect(receipt).toBeVisible();
  await expect(receipt).toContainText(/IGIC/);
  await expect(receipt).toContainText(/7\s?%/);
  await expect(receipt).not.toContainText(/\bVAT\b|\bIVA\b/);
  await page.screenshot({ path: shot('FIX-TAX-REGION-IGIC-ticket-1440') });

  // Server-side evidence: the line kept the Canary rule, and the breakdown is one IGIC key.
  const sale = await newestSaleOf(context, shirt.sku);
  expect([sale.subtotal, sale.tax_total, sale.total]).toEqual([1000, 70, 1070]);
  expect(sale.lines.map((line) => line.tax_rate)).toEqual(['7.00']);
});

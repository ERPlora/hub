// Inventory → Products in Chrome against the real Taxes app (apps/inventory/WORKBOOK.md):
//   - INVENTORY-F01: «+» → «New product», the tax category picked among those Taxes seeds; the
//     product arrives live, active, not «Not configured»;
//   - the form's refusals under their field: 422 (a price over the limit) and 409 (a SKU taken);
//   - INVENTORY-F05: a product whose tax category Taxes deactivated is «Not configured», the sale
//     catalog says it cannot be sold, and saving it with that category is refused; picking another
//     one in the form fixes it;
//   - INVENTORY-F11: the export downloads the filtered catalog with the headers the import reads;
//   - `/inventory` lands on the dashboard and the tabs walk the five sections; screenshots of every page in three
//     viewports;
//   - the list filters behind the table's funnel (price in euros), with its count, at every width; an
//     amount it cannot read is said under its field and does not filter.
import { expect, test } from '@playwright/test';

import { A, api, login, psql, shot, shown } from './helpers';
import {
  cleanInventory,
  createProduct,
  dialog,
  fill,
  GENERIC,
  pickCombo,
  productBySku,
  productRow,
  productsReady,
  searchProducts,
  shoot,
  shootFlow,
  stamp,
} from './inventory-helpers';

test.afterAll(() => {
  cleanInventory();
});

/** The widths of the filter panel's screenshots: a phone (the panel is a sheet), a tablet and a desk
 *  (two columns), as the SaaS panel's `VIEWPORTS`. */
const FILTER_VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

test('INVENTORY-F01: a new product with a tax category of Taxes arrives live, active and configured', async ({ page, context }) => {
  const sku = `E2E-NEW-${stamp()}`;
  await login(page, A, '/inventory/products');
  await productsReady(page);

  await shown(page).locator('[data-testid=inventory-products-add]').click();
  const form = dialog(page, 'inventory-product-form');
  await expect(form).toBeVisible();
  await expect(form.locator('[data-testid=inventory-product-form-submit]')).toHaveJSProperty('disabled', true);
  await fill(form, 'inventory-product-name', 'E2E Coffee');
  await fill(form, 'inventory-product-sku', sku);
  await fill(form, 'inventory-product-price', '2,20');
  await fill(form, 'inventory-product-initial-stock', '5');
  // The picker offers what Taxes seeds, by name and rate («Product — generic · 21%»).
  await pickCombo(page, form.locator('[data-testid=inventory-product-tax]'), 'generic', /(Product — generic|Producto — general).*21/);
  await page.screenshot({ path: shot('inventory-product-new-1280') });
  await shootFlow(page, 'INVENTORY-F01');
  await form.locator('[data-testid=inventory-product-form-submit]').click();
  await expect(form).toBeHidden();

  await searchProducts(page, sku);
  const row = productRow(page, sku);
  await expect(row).toBeVisible();
  await expect(row.locator('ion-toggle')).toHaveCount(1);
  await expect(shown(page).locator('[data-testid^=inventory-products-unconfigured-]')).toHaveCount(0);
  const saved = await productBySku(context, sku);
  expect([saved.tax_category_key, saved.needs_tax_setup, saved.is_active, saved.stock]).toEqual([GENERIC, false, true, '5.000']);
});

test('selectores de Inventario (Combo compartido): the product form searches its tax category and its categories on the server, at every width', async ({
  page,
  context,
}) => {
  // flow: selectores de Inventario (Combo compartido) — INVENTORY-F01, INVENTORY-F08
  await login(page, A, '/inventory/products');
  const category = async (name: string) => {
    const res = await api<{ id: string; name: string }>(context, A, 'POST', '/inventory/categories', { name });
    expect(res.status).toBe(201);
    return res.data;
  };
  const drinks = await category(`E2E Combo drinks ${stamp()}`);
  const food = await category(`E2E Combo food ${stamp()}`);
  for (const { label, width, height } of FILTER_VIEWPORTS) {
    await page.setViewportSize({ width, height });
    const sku = `E2E-COMBO-${label}-${stamp()}`;
    await page.goto(`${A}/inventory/products`);
    await productsReady(page);
    await shown(page).locator('[data-testid=inventory-products-add]').click();
    const form = dialog(page, 'inventory-product-form');
    await fill(form, 'inventory-product-name', `E2E Combo ${label}`);
    await fill(form, 'inventory-product-sku', sku);
    await fill(form, 'inventory-product-price', '1');
    await pickCombo(page, form.locator('[data-testid=inventory-product-tax]'), 'generic', /(Product — generic|Producto — general).*21/);
    await expect(form.locator('[data-testid=inventory-product-tax] input')).toHaveValue(/(Product — generic|Producto — general).*21/);

    // «Categories»: each one found by typing and added under the field as a chip.
    const categories = form.locator('[data-testid=inventory-product-categories]');
    await pickCombo(page, categories, drinks.name, drinks.name);
    await categories.locator('input').fill(food.name);
    const offered = page.locator('[data-testid^="inventory-product-categories-option-"]');
    await expect(offered).toHaveText([food.name]);
    await offered.first().click();
    const chips = form.locator('[data-testid^="inventory-product-categories-chip-"]');
    await expect(chips).toHaveText([drinks.name, food.name]);
    await expect(offered).toHaveCount(0);
    await chips.last().scrollIntoViewIfNeeded();
    await page.screenshot({ path: shot(`FIX-INVENTORY-SEARCHSELECT-TO-COMBO-${label}`) });

    // A chosen category is not offered again; the button of its chip takes it away.
    await categories.locator('input').fill(drinks.name);
    await expect(page.locator('[data-testid=inventory-product-categories-empty]')).toBeVisible();
    await expect(offered).toHaveCount(0);
    await categories.locator('input').press('Escape');
    await expect(form).toBeVisible();
    await form.locator(`[data-testid=inventory-product-categories-remove-${drinks.id}]`).click();
    await expect(chips).toHaveText([food.name]);

    await form.locator('[data-testid=inventory-product-form-submit]').click();
    await expect(form).toBeHidden();
    const saved = await productBySku(context, sku);
    expect([saved.tax_category_key, saved.category_ids]).toEqual([GENERIC, [food.id]]);
  }
});

test('the form keeps a refusal under its field: 422 for a price over the limit, 409 for a SKU taken', async ({ page, context }) => {
  await login(page, A, '/inventory/products');
  await productsReady(page);
  const taken = await createProduct(context, { name: 'E2E Taken', sku: `E2E-TAKEN-${stamp()}` });

  await shown(page).locator('[data-testid=inventory-products-add]').click();
  const form = dialog(page, 'inventory-product-form');
  await fill(form, 'inventory-product-name', 'E2E Too dear');
  await fill(form, 'inventory-product-sku', `E2E-DEAR-${stamp()}`);
  await fill(form, 'inventory-product-price', '99999999999999');
  await pickCombo(page, form.locator('[data-testid=inventory-product-tax]'), 'generic', /(Product — generic|Producto — general)/);
  await form.locator('[data-testid=inventory-product-form-submit]').click();
  const price = form.locator('[data-testid=inventory-product-price]');
  await expect(price).toHaveClass(/ion-invalid/);
  await expect(price.locator('.error-text')).not.toBeEmpty();
  await expect(form).toBeVisible();
  await page.screenshot({ path: shot('inventory-product-422-1280') });

  await fill(form, 'inventory-product-price', '3');
  await fill(form, 'inventory-product-sku', taken.sku);
  await form.locator('[data-testid=inventory-product-form-submit]').click();
  const skuField = form.locator('[data-testid=inventory-product-sku]');
  await expect(skuField.locator('.error-text')).toContainText(/SKU/);
  await expect(form.locator('[data-testid=inventory-product-form-error]')).toBeVisible();
  await page.screenshot({ path: shot('inventory-product-409-1280') });
});

test('INVENTORY-F05: a product whose tax category Taxes deactivated is «Not configured», cannot be sold, and is fixed in its form', async ({ page, context }) => {
  await login(page, A, '/inventory/dashboard');
  const key = `e2e.inv_${stamp().toLowerCase()}`;
  const created = await api(context, A, 'POST', '/tax/categories', { key, name: 'E2E inventory tax' });
  expect(created.status).toBe(201);
  const sku = `E2E-UNSET-${stamp()}`;
  const product = await createProduct(context, { name: 'E2E Old wine', sku, tax_category_key: key });
  // Taxes deactivates it (there is no screen for it yet): the product cannot be sold any more.
  psql(`update tax_taxcategory set is_active = false where key = '${key}'`);
  try {
    const forSale = await api<{ rows: Array<{ id: string; needs_tax_setup: boolean }> }>(context, A, 'GET', `/inventory/products/for_sale?search=${sku}`);
    expect(forSale.data.rows.find((row) => row.id === product.id)?.needs_tax_setup).toBe(true);
    // Saving it with that category is refused, by the API as by the form.
    const refused = await api<{ error: { code: string; fields?: Record<string, string> } }>(context, A, 'POST', '/inventory/products/update', {
      id: product.id,
      tax_category_key: key,
    });
    expect(refused.status).toBe(422);
    expect(Object.keys(refused.data.error.fields ?? {})).toContain('tax_category_key');

    await page.goto(`${A}/inventory/products?status=unconfigured`);
    await productsReady(page);
    const marker = shown(page).locator(`[data-testid=inventory-products-unconfigured-${product.id}]`);
    await expect(marker).toBeVisible();
    await expect(marker).toContainText(/Not configured|Sin configurar/);
    await page.screenshot({ path: shot('inventory-products-unconfigured-1280') });
    await shootFlow(page, 'INVENTORY-F05');

    await marker.click();
    const form = dialog(page, 'inventory-product-form');
    await expect(form.locator('[data-testid=inventory-product-tax-unconfigured]')).toBeVisible();
    await expect(form.locator('[data-testid=inventory-product-form-submit]')).toHaveJSProperty('disabled', true);
    await pickCombo(page, form.locator('[data-testid=inventory-product-tax]'), 'generic', /(Product — generic|Producto — general)/);
    await form.locator('[data-testid=inventory-product-form-submit]').click();
    await expect(form).toBeHidden();
    await expect(marker).toHaveCount(0);
    await expect.poll(async () => (await productBySku(context, sku)).needs_tax_setup).toBe(false);
  } finally {
    psql(`update tax_taxcategory set is_active = true where key = '${key}'`);
  }
});

test('INVENTORY-F11: the export downloads what the search finds, with the headers the import reads', async ({ page, context }) => {
  const sku = `E2E-EXP-${stamp()}`;
  await login(page, A, '/inventory/products');
  await productsReady(page);
  await createProduct(context, { name: 'E2E Exported', sku, price: 220 });
  await searchProducts(page, sku);
  // The search is the server's (debounced): wait until the list holds only what it finds.
  await expect(shown(page).locator('[data-testid=inventory-products-row]')).toHaveCount(1);
  await expect(productRow(page, sku)).toBeVisible();
  await shootFlow(page, 'INVENTORY-F11');
  const [download] = await Promise.all([page.waitForEvent('download'), shown(page).locator('[data-testid=inventory-products-csv-export]').click()]);
  expect(download.suggestedFilename()).toMatch(/^inventor(y|io)-product(s|os)\.csv$/);
  const path = await download.path();
  const { readFileSync } = await import('node:fs');
  const text = readFileSync(path, 'utf8');
  const [header, ...lines] = text.replace(/^﻿/, '').trim().split(/\r?\n/);
  expect(header).toMatch(/^(Name|Nombre)[;,]SKU[;,]/);
  expect(lines).toHaveLength(1);
  expect(lines[0]).toContain(sku);
});

test('the tabs walk the five sections, each on its address; screenshots of every page in three viewports', async ({ page }) => {
  // `/inventory` is no page: the SPA's router sends it to the dashboard. `login` lands on a page (it timed out here
  // with a session kept by the tests above, FIX-HUB-E2E-INVENTORY-TABS-WALK-TIMEOUT-AFTER-OTHERS), so the walk signs
  // in on another tab and then asks for `/inventory`, as a person who types it.
  await login(page, A, '/inventory/settings');
  await page.goto(`${A}/inventory`);
  await page.waitForURL(/\/inventory\/dashboard$/);
  await shown(page).locator('[data-testid=inventory-dashboard-kpi-tracked]').waitFor();
  const shots: string[] = [];
  shots.push(...(await shoot(page, 'inventory-dashboard')));
  for (const [tab, path, ready] of [
    ['products', '/inventory/products', '[data-testid=inventory-products-row], [data-testid=inventory-products-empty]'],
    ['movements', '/inventory/movements', '[data-testid=inventory-movements-row], .data-table__empty'],
    ['categories', '/inventory/categories', '[data-testid=inventory-categories-row], [data-testid=inventory-categories-empty]'],
    ['settings', '/inventory/settings', '[data-testid=inventory-settings-form]'],
  ] as const) {
    await shown(page).locator(`[data-testid=tab-${tab}]`).click();
    await page.waitForURL(new RegExp(`${path}$`));
    await shown(page).locator(ready).first().waitFor({ state: 'visible' });
    shots.push(...(await shoot(page, `inventory-${tab}`)));
  }
  await shown(page).locator('[data-testid=tab-dashboard]').click();
  await page.waitForURL(/\/inventory\/dashboard$/);
  expect(shots).toHaveLength(15);
});

// flow: ninguno — FIX DataTable parte 2b-2 (PLAN-MIGRATIONS §13: filtros como en la vieja)
test('FIX-DATATABLE-HUB-FILTERS-2A: Products filter by price in euros behind the funnel, with its count; an amount it cannot read is said under it', async ({ page, context }) => {
  const run = stamp();
  await login(page, A, '/inventory/products');
  // 2,20 € and 15,00 €: «Price from 10» is ten euros (inventory#115), never ten cents.
  const cheap = await createProduct(context, { name: `E2E Cheap ${run}`, sku: `E2E-FIL-C-${run}`, price: 220 });
  const dear = await createProduct(context, { name: `E2E Dear ${run}`, sku: `E2E-FIL-D-${run}`, price: 1500 });
  const panel = shown(page).locator('[data-testid=inventory-products-filters-panel]');
  const toggle = shown(page).locator('[data-testid=inventory-products-filters-toggle]');
  const count = shown(page).locator('[data-testid=inventory-products-filters-count]');
  const priceFrom = panel.locator('[data-testid=inventory-products-filter-price_min]');
  for (const vp of FILTER_VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto(`${A}/inventory/products`);
    await productsReady(page);
    await searchProducts(page, run);
    await expect(productRow(page, cheap.sku)).toBeVisible();
    await expect(productRow(page, dear.sku)).toBeVisible();
    await toggle.click();
    await expect(panel).toBeVisible();
    await priceFrom.locator('input').fill('10');
    await panel.locator('[data-testid=inventory-products-filters-apply]').click();
    await expect(panel).toBeHidden();
    await expect(count).toHaveText('1');
    await expect(productRow(page, dear.sku)).toBeVisible();
    await expect(productRow(page, cheap.sku)).toHaveCount(0);
    await toggle.click();
    await expect(panel).toBeVisible();
    await page.waitForTimeout(400);
    await page.screenshot({ path: shot(`FIX-DATATABLE-HUB-FILTERS-2A-inventory-${vp.label}`) });
    await panel.locator('[data-testid=inventory-products-filters-clear]').click();
    await expect(count).toHaveCount(0);
    await panel.locator('[data-testid=inventory-products-filters-close]').click();
    await expect(panel).toBeHidden();
    await expect(productRow(page, cheap.sku)).toBeVisible();
  }

  // «doce» is not an amount: said under «Price from», the funnel turns red, and nothing is filtered.
  await toggle.click();
  await priceFrom.locator('input').fill('doce');
  await panel.locator('[data-testid=inventory-products-filters-apply]').click();
  await expect(toggle).toHaveAttribute('data-invalid', 'true');
  await expect(productRow(page, cheap.sku)).toBeVisible();
  await expect(productRow(page, dear.sku)).toBeVisible();
  await toggle.click();
  await expect(priceFrom).toHaveClass(/ion-invalid/);
  await expect(priceFrom.locator('.error-text')).toHaveText(/This is not an amount|Esto no es un importe/);
  await page.screenshot({ path: shot('FIX-DATATABLE-HUB-FILTERS-2A-inventory-error-1440') });
});

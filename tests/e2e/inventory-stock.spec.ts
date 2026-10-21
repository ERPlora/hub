// Inventory stock in Chrome (apps/inventory/WORKBOOK.md):
//   - INVENTORY-F13/F14/F16: «Receive stock» and «Count stock» from a product's row change its stock,
//     and each movement shows up in Movements, open in another tab, without reloading;
//   - INVENTORY-F15: «Write off stock» lowers it with its reason; more than there is is refused under
//     the quantity;
//   - INVENTORY-F17: a product at or under its threshold is in the dashboard's «Low stock products»
//     and in the «Low stock» figure, live.
import { expect, test } from '@playwright/test';

import { A, login, shot, shown } from './helpers';
import { cleanInventory, createProduct, dialog, fill, productBySku, productRow, productsReady, rowAction, searchProducts, shootFlow, stamp } from './inventory-helpers';

test.afterAll(() => {
  cleanInventory();
});

test('INVENTORY-F13/F14/F16: receiving and counting change the stock and show up in Movements without reloading', async ({ page, context }) => {
  const sku = `E2E-STK-${stamp()}`;
  await login(page, A, '/inventory/products');
  await productsReady(page);
  const flour = await createProduct(context, { name: 'E2E Flour', sku, initial_stock: '5', low_stock_threshold: '2' });
  await searchProducts(page, sku);
  await expect(productRow(page, sku)).toBeVisible();

  // Movements, open in a second tab of the same session, filtered on this product.
  const ledger = await context.newPage();
  await ledger.goto(`${A}/inventory/movements`);
  await shown(ledger).locator('[data-testid=inventory-movements-search] input').fill(sku);
  await expect(shown(ledger).locator('[data-testid=inventory-movements-row]')).toHaveCount(1); // the «Initial» 5

  // Receive 3.
  await rowAction(page, flour.id, 'receive');
  const receive = dialog(page, 'inventory-stock-form');
  await expect(receive).toBeVisible();
  await expect(receive.locator('[data-testid=inventory-stock-current] ion-note')).toHaveText('5');
  await fill(receive, 'inventory-stock-qty', '3');
  await fill(receive, 'inventory-stock-cost', '0,75');
  await page.screenshot({ path: shot('inventory-receive-1280') });
  await shootFlow(page, 'INVENTORY-F13');
  await receive.locator('[data-testid=inventory-stock-form-submit]').click();
  await expect(receive).toBeHidden();
  // The Stock cell, exact: the SKU's random suffix may contain the same figure.
  await expect(productRow(page, sku).locator('[data-testid=inventory-product-stock]')).toHaveText('8');
  await expect(shown(ledger).locator('[data-testid=inventory-movements-row]')).toHaveCount(2);
  await expect(shown(ledger).locator('[data-testid=inventory-movements-row]').first().locator('[data-testid=inventory-movement-type]')).toHaveText(/^(Reception|Recepción)$/);

  // Count 6 (the total, not the difference): «Difference −2», the reason required.
  await rowAction(page, flour.id, 'count');
  const count = dialog(page, 'inventory-stock-form');
  await fill(count, 'inventory-stock-qty', '6');
  await expect(count.locator('[data-testid=inventory-stock-diff] ion-note')).toHaveText('-2');
  await expect(count.locator('[data-testid=inventory-stock-form-submit]')).toHaveJSProperty('disabled', true);
  await fill(count, 'inventory-stock-reason', 'E2E monthly count');
  await page.screenshot({ path: shot('inventory-count-1280') });
  await shootFlow(page, 'INVENTORY-F14');
  await count.locator('[data-testid=inventory-stock-form-submit]').click();
  await expect(count).toBeHidden();
  await expect(productRow(page, sku).locator('[data-testid=inventory-product-stock]')).toHaveText('6');
  await expect(shown(ledger).locator('[data-testid=inventory-movements-row]')).toHaveCount(3);
  const latest = shown(ledger).locator('[data-testid=inventory-movements-row]').first();
  await expect(latest.locator('[data-testid=inventory-movement-type]')).toHaveText(/^(Count|Recuento)$/);
  await expect(latest).toContainText('E2E monthly count');
  await ledger.screenshot({ path: shot('inventory-movements-live-1280') });
  expect((await productBySku(context, sku)).stock).toBe('6.000');
  await ledger.close();
});

test('INVENTORY-F15: writing off stock lowers it with its reason; more than there is is refused under the quantity', async ({ page, context }) => {
  const sku = `E2E-WOF-${stamp()}`;
  await login(page, A, '/inventory/products');
  await productsReady(page);
  await createProduct(context, { name: 'E2E Wine', sku, initial_stock: '4' });
  await searchProducts(page, sku);
  // The sheet carries the stock buttons with their names.
  await productRow(page, sku).click();
  const sheet = dialog(page, 'inventory-product-detail');
  await expect(sheet).toBeVisible();
  await page.screenshot({ path: shot('inventory-product-detail-1280') });
  await sheet.locator('[data-testid=inventory-product-detail-write-off]').click();
  const form = dialog(page, 'inventory-stock-form');
  await fill(form, 'inventory-stock-qty', '9');
  await fill(form, 'inventory-stock-reason', 'E2E breakage');
  await form.locator('[data-testid=inventory-stock-form-submit]').click();
  await expect(form.locator('[data-testid=inventory-stock-qty] .error-text')).not.toBeEmpty();
  await shootFlow(page, 'INVENTORY-F15');
  await expect(form).toBeVisible();
  await fill(form, 'inventory-stock-qty', '1');
  await form.locator('[data-testid=inventory-stock-form-submit]').click();
  await expect(form).toBeHidden();
  await expect.poll(async () => (await productBySku(context, sku)).stock).toBe('3.000');
});

test('INVENTORY-F17: a product at or under its threshold is in «Low stock products» and in the figure, live', async ({ page, context }) => {
  const sku = `E2E-LOW-${stamp()}`;
  await login(page, A, '/inventory/dashboard');
  const figure = shown(page).locator('[data-testid=inventory-dashboard-kpi-low-stock]');
  await expect(figure).toBeVisible();
  const before = Number(await figure.getAttribute('data-value'));
  await createProduct(context, { name: 'E2E Milk', sku, initial_stock: '1', low_stock_threshold: '10' });
  await expect.poll(async () => Number(await figure.getAttribute('data-value'))).toBe(before + 1);
  const table = shown(page).locator('[data-testid=inventory-dashboard-low-stock-row]', { hasText: sku });
  await expect(table).toBeVisible();
  await expect(table.locator('[data-testid=inventory-low-stock-stock]')).toHaveText('1');
  await expect(table.locator('[data-testid=inventory-low-stock-threshold]')).toHaveText('10');
  await page.screenshot({ path: shot('inventory-dashboard-low-stock-1280') });
  await shootFlow(page, 'INVENTORY-F17');
});

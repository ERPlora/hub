import { writeFileSync } from 'node:fs';

import { expect, type Locator, type Page, test } from '@playwright/test';

import { A, capture, login, shown } from './helpers';
import {
  cleanInventory,
  dialog,
  fill,
  GENERIC,
  pickCombo,
  productBySku,
  productsReady,
  searchProducts,
  stamp,
} from './inventory-helpers';
import { rowAction } from './service-helpers';

test.afterAll(() => {
  cleanInventory();
});

const UI_VIEWPORTS = [
  { label: '1440x900', width: 1440, height: 900 },
  { label: '820x1180', width: 820, height: 1180 },
  { label: '375x667', width: 375, height: 667 },
];

async function captureAtUiSizes(page: Page, name: string, required: Locator): Promise<void> {
  for (const viewport of UI_VIEWPORTS) {
    await page.setViewportSize(viewport);
    await expect(required).toBeVisible();
    await capture(page, `${name}-${viewport.label}`);
  }
  await page.setViewportSize({ width: 1280, height: 860 });
}

test('INVENTORY-F35: a product saves its allergens and its sheet shows them or the empty declaration', async ({ page, context }) => {
  const sku = `E2E-ALLERGENS-${stamp()}`;
  await login(page, A, '/inventory/products');
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  await productsReady(page);

  await shown(page).locator('[data-testid=inventory-products-add]').click();
  const form = dialog(page, 'inventory-product-form');
  await fill(form, 'inventory-product-name', 'E2E Allergen dessert');
  await fill(form, 'inventory-product-sku', sku);
  await fill(form, 'inventory-product-price', '3,50');
  await pickCombo(page, form.locator('[data-testid=inventory-product-tax]'), 'generic', /(Product — generic|Producto — general)/);
  const block = form.locator('[data-testid=inventory-product-allergens]');
  await expect(block.locator('ion-checkbox')).toHaveCount(14);
  await block.locator('[data-testid=inventory-product-allergens-milk] ion-checkbox').click();
  await block.locator('[data-testid=inventory-product-allergens-gluten] ion-checkbox').click();
  await captureAtUiSizes(page, 'INVENTORY-F35-form', block);
  await form.locator('[data-testid=inventory-product-form-submit]').click();
  await expect(form).toBeHidden();

  const created = await productBySku(context, sku);
  expect(created.allergens).toEqual(['gluten', 'milk']);
  await searchProducts(page, sku);
  await rowAction(page, 'inventory-products', created.id, 'detail');
  const sheet = dialog(page, 'inventory-product-detail');
  await expect(sheet.locator('[data-testid=inventory-product-detail-allergens] ion-note')).toHaveText('Gluten, Milk');
  await captureAtUiSizes(page, 'INVENTORY-F35-detail', sheet.locator('[data-testid=inventory-product-detail-allergens]'));
  await sheet.locator('[data-testid=inventory-product-detail-close-button]').click();

  await rowAction(page, 'inventory-products', created.id, 'edit');
  await block.locator('[data-testid=inventory-product-allergens-milk] ion-checkbox').click();
  await block.locator('[data-testid=inventory-product-allergens-gluten] ion-checkbox').click();
  await form.locator('[data-testid=inventory-product-form-submit]').click();
  await expect(form).toBeHidden();
  expect((await productBySku(context, sku)).allergens).toEqual([]);

  await rowAction(page, 'inventory-products', created.id, 'detail');
  await expect(sheet.locator('[data-testid=inventory-product-detail-allergens] ion-note')).toHaveText('No allergens declared');
});

test('INVENTORY-F35: the product import reads the Allergens column and sends its values', async ({ page, context }) => {
  const sku = `E2E-CSV-ALLERGENS-${stamp()}`;
  await login(page, A, '/inventory/products');
  await productsReady(page);
  const file = test.info().outputPath('allergens.csv');
  writeFileSync(file, `Nombre;Código;Precio;Alérgenos;IVA\r\nE2E CSV dessert;${sku};3,50;Leche, Gluten;${GENERIC}\r\n`);

  await shown(page).locator('[data-testid=inventory-products-csv-import]').setInputFiles(file);
  const preview = dialog(page, 'inventory-import-preview');
  await expect(preview.locator('[data-testid=inventory-import-column]').nth(3)).toHaveJSProperty('value', 'allergens');
  await expect(preview.locator('[data-testid=inventory-import-summary]')).toContainText(/1 (row ready|fila lista)/);
  await preview.locator('[data-testid=inventory-import-preview-submit]').click();
  const report = dialog(page, 'inventory-import-report');
  await expect(report.locator('[data-testid=inventory-import-report-count-created] ion-note')).toHaveText('1');
  await expect(report.locator('[data-testid=inventory-import-report-count-failed] ion-note')).toHaveText('0');

  expect((await productBySku(context, sku)).allergens).toEqual(['gluten', 'milk']);
});

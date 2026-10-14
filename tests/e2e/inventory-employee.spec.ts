// Inventory for an employee and on a phone (apps/inventory/WORKBOOK.md «Quién puede qué», «Ajustes»):
//   - the employee (`hub_employee`) sees products, movements and categories, but nothing that writes:
//     no «+», no CSV, «Yes»/«No» instead of the switch, only «Details»; no Settings tab, and its
//     address says «This page does not exist»; the API refuses every write with 403;
//   - on a phone (390×844) the products list is cards with «Load more», a product's sheet opens, and
//     the form fits as a sheet.
import { expect, test } from '@playwright/test';

import { A, api, EMPLOYEE, hostPage, shot, shown } from './helpers';
import { cleanInventory, createProduct, dialog, productRow, productsReady, searchProducts, stamp } from './inventory-helpers';

test.afterAll(() => {
  cleanInventory();
});

test('an employee sees the inventory but writes nothing, by the screens or by the API', async ({ browser }) => {
  const owner = await hostPage(browser, A, { next: '/inventory/products' });
  const sku = `E2E-EMP-${stamp()}`;
  const product = await createProduct(owner.context, { name: 'E2E Shampoo', sku, initial_stock: '2' });
  const employee = await hostPage(browser, A, { next: '/inventory/products', credentials: EMPLOYEE });
  const { page } = employee;
  try {
    // Positive control: the owner has what the employee must not.
    await productsReady(owner.page);
    await expect(shown(owner.page).locator('[data-testid=inventory-products-add]')).toBeVisible();
    await expect(shown(owner.page).locator('[data-testid=tab-settings]')).toBeVisible();

    await productsReady(page);
    await searchProducts(page, sku);
    const row = productRow(page, sku);
    await expect(row).toBeVisible();
    await expect(row.locator(`[data-testid=inventory-products-active-text-${product.id}]`)).toHaveText(/Yes|Sí/);
    await expect(row.locator('ion-toggle')).toHaveCount(0);
    for (const hook of ['inventory-products-add', 'inventory-products-csv-import', 'inventory-products-csv-export', 'tab-settings']) {
      await expect(shown(page).locator(`[data-testid=${hook}]`), hook).toHaveCount(0);
    }
    await expect(shown(page).locator(`[data-testid=inventory-products-row-${product.id}-edit]`)).toHaveCount(0);
    await page.screenshot({ path: shot('inventory-employee-products') });

    // The sheet opens, without stock buttons.
    await row.click();
    const sheet = dialog(page, 'inventory-product-detail');
    await expect(sheet).toBeVisible();
    await expect(sheet.locator('[data-testid=inventory-product-detail-receive]')).toHaveCount(0);
    await sheet.locator('[data-testid=inventory-product-detail-close-button]').click();

    // Movements and categories are readable.
    await shown(page).locator('[data-testid=tab-movements]').click();
    await page.waitForURL(/\/inventory\/movements$/);
    await shown(page).locator('[data-testid=inventory-movements-search]').waitFor();
    await shown(page).locator('[data-testid=tab-categories]').click();
    await page.waitForURL(/\/inventory\/categories$/);
    await expect(shown(page).locator('[data-testid=inventory-categories-add]')).toHaveCount(0);

    // Settings by its address: «This page does not exist».
    await page.goto(`${A}/inventory/settings`);
    await expect(shown(page).locator('[data-testid=inventory-settings-not-found]')).toBeVisible();
    await expect(shown(page).locator('[data-testid=inventory-settings-form]')).toHaveCount(0);
    await page.screenshot({ path: shot('inventory-employee-settings') });

    // The API refuses every write.
    const writes: Array<[string, unknown]> = [
      ['/inventory/products', { name: 'E2E No', sku: `E2E-NO-${stamp()}`, price: 1, tax_category_key: 'product.generic' }],
      ['/inventory/products/update', { id: product.id, is_active: false }],
      ['/inventory/stock/receive', { items: [{ product_id: product.id, qty: '1' }] }],
      ['/inventory/stock/count', { product_id: product.id, stock: '9', reason: 'E2E nope' }],
      ['/inventory/products/delete', { id: product.id }],
      ['/inventory/config', { track_stock: false }],
    ];
    for (const [path, body] of writes) {
      const res = await api<{ error?: { code: string } }>(employee.context, A, 'POST', path, body);
      expect(res.status, path).toBe(403);
      expect(res.data.error?.code, path).toBe('permission_denied');
    }
    const after = await api<{ stock: string; is_active: boolean }>(owner.context, A, 'GET', `/inventory/products/detail?id=${product.id}`);
    expect([after.data.stock, after.data.is_active]).toEqual(['2.000', true]);
  } finally {
    await employee.context.close();
    await owner.context.close();
  }
});

test('on a phone the products are cards, a sheet opens and the form is a sheet', async ({ browser }) => {
  const owner = await hostPage(browser, A, { next: '/inventory/products', viewport: { width: 390, height: 844 } });
  const { page } = owner;
  const sku = `E2E-PHONE-${stamp()}`;
  await createProduct(owner.context, { name: 'E2E Phone soap', sku });
  try {
    await productsReady(page);
    await searchProducts(page, sku);
    const card = productRow(page, sku);
    await expect(card).toBeVisible();
    await expect(shown(page).locator('.data-table__cards')).toBeVisible();
    await page.screenshot({ path: shot('inventory-products-phone-cards') });
    await card.click();
    await expect(dialog(page, 'inventory-product-detail')).toBeVisible();
    await page.screenshot({ path: shot('inventory-product-detail-phone') });
    await dialog(page, 'inventory-product-detail').locator('[data-testid=inventory-product-detail-close-button]').click();
    await shown(page).locator('[data-testid=inventory-products-add]').click();
    const form = dialog(page, 'inventory-product-form');
    await expect(form).toBeVisible();
    await expect(form.locator('[data-testid=inventory-product-form-submit]')).toBeVisible();
    await page.screenshot({ path: shot('inventory-product-form-phone') });
    // The tabbar walks the sections on a phone too.
    await form.locator('[data-testid=inventory-product-form-cancel]').click();
    await shown(page).locator('[data-testid=tab-dashboard]').click();
    await page.waitForURL(/\/inventory\/dashboard$/);
    await shown(page).locator('[data-testid=inventory-dashboard-kpi-tracked]').waitFor();
    await page.screenshot({ path: shot('inventory-dashboard-phone') });
  } finally {
    await owner.context.close();
  }
});

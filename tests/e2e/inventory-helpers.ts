// Shared steps of the inventory specs (apps/inventory/WORKBOOK.md) against hub `a` and the real Taxes
// app (no doubles): its data are named `E2E …` / `E2E-…` / `e2e …` so `cleanInventory()` (in each
// spec's `afterAll`) removes exactly them from the hub's database, with their movements and links.
import { type BrowserContext, expect, type Locator, type Page } from '@playwright/test';

import { A, api, psql, shot, shown } from './helpers';

export const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1194 },
  { label: '1440', width: 1440, height: 900 },
] as const;

/** A tax category of Taxes' Spanish factory catalogue. */
export const GENERIC = 'product.generic';

/** A unique suffix for this run's data. */
export const stamp = (): string => Date.now().toString(36).toUpperCase();

export interface Product {
  id: string;
  sku: string;
  name: string;
  stock: string;
  tax_category_key: string | null;
  needs_tax_setup: boolean;
  is_active: boolean;
  is_sold_out: boolean;
}

/** Deletes every `E2E` product, movement, category, link and learned text and `e2e.inv_*` tax category. */
export function cleanInventory(): void {
  const products = `select id from inventory_product where sku like 'E2E-%'`;
  const categories = `select id from inventory_category where name like 'E2E %'`;
  psql(`delete from inventory_stockmovement where product_id in (${products})`);
  psql(`delete from inventory_productcategory where product_id in (${products}) or category_id in (${categories})`);
  psql(`delete from inventory_product where sku like 'E2E-%'`);
  psql(`delete from inventory_category where name like 'E2E %'`);
  psql(`delete from tax_taxalias where alias like 'e2e %'`);
  psql(
    `delete from tax_taxcategory where key like 'e2e.inv%' and id not in (select tax_category_id from inventory_product where tax_category_id is not null) and id not in (select tax_category_id from inventory_category where tax_category_id is not null)`,
  );
}

/** A product made through the API (setup, never the check). */
export async function createProduct(context: BrowserContext, fields: Record<string, unknown>): Promise<Product> {
  const res = await api<Product>(context, A, 'POST', '/inventory/products', { price: 100, tax_category_key: GENERIC, ...fields });
  expect(res.status, `create ${String(fields.sku)}`).toBe(201);
  return res.data;
}

export async function productBySku(context: BrowserContext, sku: string): Promise<Product> {
  const res = await api<Product>(context, A, 'GET', `/inventory/products/detail?product=${encodeURIComponent(sku)}`);
  expect(res.status, `detail ${sku}`).toBe(200);
  return res.data;
}

/** Opens an `ion-select` and picks the option whose text matches (popover, or alert + OK for a multiple one). */
export async function pick(page: Page, select: Locator, text: string | RegExp): Promise<void> {
  await select.click();
  const overlay = page.locator('ion-popover:visible, ion-alert:visible').last();
  await overlay.waitFor({ state: 'visible' });
  const isAlert = await overlay.evaluate((el) => el.tagName === 'ION-ALERT');
  if (isAlert) {
    await overlay.locator('button.alert-tappable, button.alert-radio-button, button.alert-checkbox-button').filter({ hasText: text }).first().click();
    await overlay.locator('.alert-button-group button').last().click();
  } else {
    await overlay.locator('ion-radio, ion-item, ion-checkbox').filter({ hasText: text }).first().click();
  }
  await expect(overlay).toBeHidden();
}

/** The dialog of a FormModal (Ionic moves it to ion-app). */
export const dialog = (page: Page, testid: string): Locator => page.locator(`ion-modal[data-testid=${testid}]`);

/** Types into an Ionic field. */
export async function fill(scope: Locator, testid: string, value: string): Promise<void> {
  const input = scope.locator(`[data-testid=${testid}] input, [data-testid=${testid}] textarea`).first();
  await input.fill(value);
  await input.blur();
}

export const productsReady = (page: Page) =>
  shown(page).locator('[data-testid=inventory-products-row], [data-testid=inventory-products-empty]').first().waitFor({ state: 'visible' });

/** The row (or card) of the product with this SKU on the products list shown. */
export const productRow = (page: Page, sku: string): Locator =>
  shown(page).locator('[data-testid=inventory-products-row]', { hasText: sku });

/** Narrows the products list to `text` with its search box. */
export async function searchProducts(page: Page, text: string): Promise<void> {
  await shown(page).locator('[data-testid=inventory-products-search] input').fill(text);
}

/** Screenshots of the page shown at the three viewports, then back to `restore`. */
export async function shoot(page: Page, name: string, restore = { width: 1280, height: 860 }): Promise<string[]> {
  const files: string[] = [];
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    // The table refits to its box; wait for a frame rather than a fixed time.
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    const file = shot(`${name}-${viewport.label}`);
    await page.screenshot({ path: file });
    files.push(file);
  }
  await page.setViewportSize(restore);
  return files;
}

/** Runs a row action of the products list: its inline button, or the row's «⋮» menu when it folded there. */
export async function rowAction(page: Page, id: string, action: string): Promise<void> {
  const hook = `inventory-products-row-${id}-${action}`;
  const inline = shown(page).locator(`[data-testid=${hook}]`);
  if ((await inline.count()) > 0 && (await inline.first().isVisible())) {
    await inline.first().click();
    return;
  }
  await shown(page).locator(`[data-testid=inventory-products-row-${id}-menu]`).first().click();
  await page.locator(`ion-popover [data-testid=${hook}]`).click();
}

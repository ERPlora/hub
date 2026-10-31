// flow: INVENTORY-F12 — load the menu of a sector template (apps/inventory/WORKBOOK.md), in Chrome, as the owner of
// hub `a`, against the real Hub (Settings › Data and backups › Import, BASE-F29 and BASE-F31) and the real Inventory,
// no doubles, in the three viewports:
//   - «Use template» on the restaurant's (`restaurant.en`), «Review what it brings» with Inventory ticked and Tables
//     unticked, «Import»: «Everything went in.», and Inventory «Applied»;
//   - Inventory › Products: every product of the template is there with its price and its tax category (none «Not
//     configured»), each in its category; Categories has the template's categories; the stock the template brings is
//     in Movements as «Initial»;
//   - loading it again changes nothing: a price changed by hand stays, nothing is duplicated, and the report says
//     «You had it already».
// What the template brings to Inventory (its SKUs and its category names, read from the template itself) is taken out
// of `a` before each test and after the last one, through Inventory's own operations (phase 1: `a` and `b` share these
// rows). Tables are never loaded. Each viewport leaves its capture `CLOSE-INVENTORY-<width>`.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, capture, HUB_DIR, hostPage, shown } from './helpers';
import { productRow, productsReady, searchProducts, VIEWPORTS } from './inventory-helpers';

test.use({ actionTimeout: 30_000 });

const TEMPLATE = 'restaurant.en';

interface SeedProduct {
  name: string;
  sku: string;
  price: number;
  stock: string;
  tax_category_key: string;
  categories: string[];
}

/** What the template brings to Inventory, read from the template the Hub serves. */
const seed = JSON.parse(readFileSync(join(HUB_DIR, 'base', 'seeds', `${TEMPLATE}.json`), 'utf8')) as {
  data: { 'inventory.product': SeedProduct[]; 'inventory.category': { name: string }[] };
};
const PRODUCTS = seed.data['inventory.product'];
const CATEGORIES = seed.data['inventory.category'].map((row) => row.name);
const STOCKED = PRODUCTS.find((row) => row.stock !== '' && Number(row.stock) > 0);

interface Row {
  id: string;
  name: string;
  sku: string;
  price: number;
  stock: string;
  tax_category_key: string | null;
  category_ids: string[];
}

const testid = (page: Page, id: string) => shown(page).locator(`[data-testid="${id}"]`);

async function list<T>(context: BrowserContext, path: string): Promise<T[]> {
  const rows: T[] = [];
  for (let offset = 0; ; offset += 100) {
    const res = await api<{ rows: T[]; total: number }>(context, A, 'GET', `${path}${path.includes('?') ? '&' : '?'}limit=100&offset=${offset}`);
    expect(res.status, path).toBe(200);
    rows.push(...res.data.rows);
    if (rows.length >= res.data.total || res.data.rows.length === 0) return rows;
  }
}

/** Takes out of `a` what the template brings to Inventory: its products (by SKU), then its categories (by name). */
async function withoutTemplate(context: BrowserContext): Promise<void> {
  const skus = new Set(PRODUCTS.map((row) => row.sku));
  for (const row of await list<Row>(context, '/inventory/products')) {
    if (!skus.has(row.sku)) continue;
    const res = await api(context, A, 'POST', '/inventory/products/delete', { id: row.id });
    expect(res.status, `delete ${row.sku}`).toBeLessThan(300);
  }
  for (const row of await list<{ id: string; name: string }>(context, '/inventory/categories')) {
    if (!CATEGORIES.includes(row.name)) continue;
    const res = await api(context, A, 'POST', '/inventory/categories/delete', { id: row.id });
    expect(res.status, `delete ${row.name}`).toBeLessThan(300);
  }
}

async function templateRows(context: BrowserContext): Promise<Map<string, Row>> {
  const skus = new Set(PRODUCTS.map((row) => row.sku));
  return new Map((await list<Row>(context, '/inventory/products')).filter((row) => skus.has(row.sku)).map((row) => [row.sku, row]));
}

/** Settings › Data and backups › Import: «Use template» on the restaurant's, only Inventory ticked, «Import». */
async function loadTemplate(page: Page): Promise<void> {
  await page.goto(`${A}/settings#data`);
  const row = shown(page).locator(`[data-testid="templates-row"][data-id="${TEMPLATE}"]`);
  // Import opens on the report of a last load that did not go in whole (BASE-F33): «See the templates» goes back.
  const back = testid(page, 'report-templates');
  await expect(row.or(back)).toBeVisible();
  if (await back.isVisible()) await back.click();
  await expect(row).toBeVisible();
  await row.locator('[data-testid$="-use"]').click();
  const review = testid(page, 'review');
  await expect(review).toBeVisible();
  const inventory = review.locator('[data-testid="review-app"][data-id="inventory"] ion-checkbox');
  await expect(inventory).toHaveJSProperty('checked', true);
  const tables = review.locator('[data-testid="review-app"][data-id="table"] ion-checkbox');
  if ((await tables.count()) > 0 && (await tables.evaluate((box) => (box as HTMLInputElement).checked))) await tables.click();
  await review.locator('[data-testid="review-import"]').click();
  await expect(testid(page, 'report-status')).toBeVisible();
}

const inventoryReport = (page: Page) => testid(page, 'report').locator('[data-testid="report-app"][data-id="inventory"]');

test.beforeEach(async ({ browser }) => {
  const { context } = await hostPage(browser, A, { next: '/inventory/products' });
  await withoutTemplate(context);
  await context.close();
});

test.afterAll(async ({ browser }) => {
  const { context } = await hostPage(browser, A, { next: '/inventory/products' });
  await withoutTemplate(context);
  await context.close();
});

for (const viewport of VIEWPORTS) {
  test(`INVENTORY-F12: the restaurant's template loads its menu into Inventory at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(240_000);
    const { context, page } = await hostPage(browser, A, { viewport, next: '/inventory/products' });

    await loadTemplate(page);
    await expect(testid(page, 'report-status')).toHaveText('Everything went in.');
    await expect(inventoryReport(page).locator('[data-testid="report-app-status"]')).toContainText('Applied');
    const tablesReport = testid(page, 'report').locator('[data-testid="report-app"][data-id="table"]');
    if ((await tablesReport.count()) > 0) await expect(tablesReport.locator('[data-testid="report-app-status"]')).toContainText('Not chosen');

    // Every product of the template, with its price, its tax category and its category; the stock it brings.
    const loaded = await templateRows(context);
    const categories = new Map(
      (await list<{ id: string; name: string }>(context, '/inventory/categories')).map((row) => [row.id, row.name]),
    );
    expect([...loaded.keys()].sort()).toEqual(PRODUCTS.map((row) => row.sku).sort());
    for (const product of PRODUCTS) {
      const row = loaded.get(product.sku)!;
      expect([row.name, row.price, row.tax_category_key], product.sku).toEqual([product.name, product.price, product.tax_category_key]);
      expect(row.category_ids.map((id) => categories.get(id)), product.sku).toEqual(product.categories);
    }
    expect(STOCKED, 'the template brings some stock').toBeDefined();
    expect(Number(loaded.get(STOCKED!.sku)!.stock)).toBe(Number(STOCKED!.stock));

    // Inventory › Products: each one, none «Not configured».
    await page.goto(`${A}/inventory/products`);
    await productsReady(page);
    for (const product of PRODUCTS.slice(0, 3)) {
      await searchProducts(page, product.sku);
      await expect(productRow(page, product.sku)).toContainText(product.name);
      await expect(productRow(page, product.sku)).not.toContainText('Not configured');
    }
    await searchProducts(page, '');
    await expect(shown(page).locator('[data-testid=inventory-products-row]').first()).toBeVisible();
    await capture(page, `CLOSE-INVENTORY-${viewport.label}`);

    // Inventory › Categories: the template's.
    await page.goto(`${A}/inventory/categories`);
    for (const name of CATEGORIES) {
      await expect(shown(page).locator('[data-testid=inventory-categories-row]', { hasText: name }).first()).toBeVisible();
    }

    // Inventory › Movements: the stock it brings, as «Initial» (one movement of the new product, the most recent of its
    // SKU: a product deleted before keeps its own, INVENTORY-F04).
    const stocked = loaded.get(STOCKED!.sku)!;
    const own = await list<{ movement_type: string; qty: string }>(context, `/inventory/movements?product_id=${stocked.id}`);
    expect(own.map((row) => [row.movement_type, Number(row.qty)])).toEqual([['initial', Number(STOCKED!.stock)]]);
    await page.goto(`${A}/inventory/movements`);
    await shown(page).locator('[data-testid=inventory-movements-search] input').fill(STOCKED!.sku);
    const newest = shown(page).locator('[data-testid=inventory-movements-row]').first();
    await expect(newest).toContainText(STOCKED!.name);
    await expect(newest.locator('[data-testid=inventory-movement-type]')).toHaveText('Initial');

    await context.close();
  });
}

test('INVENTORY-F12: loading the template again skips what is there: a price changed by hand stays', async ({ browser }) => {
  test.setTimeout(240_000);
  const { context, page } = await hostPage(browser, A, { viewport: { width: 1440, height: 900 }, next: '/inventory/products' });
  await loadTemplate(page);
  await expect(testid(page, 'report-status')).toHaveText('Everything went in.');
  const first = PRODUCTS[0];
  const before = (await templateRows(context)).get(first.sku)!;
  const changed = await api(context, A, 'POST', '/inventory/products/update', { id: before.id, price: first.price + 111 });
  expect(changed.status, JSON.stringify(changed.data)).toBe(200);

  await loadTemplate(page);

  await expect(testid(page, 'report-status')).toHaveText('Everything went in.');
  await expect(inventoryReport(page).locator('[data-testid="report-app-status"]')).toContainText('You had it already');
  const after = await templateRows(context);
  expect(after.size).toBe(PRODUCTS.length);
  expect(after.get(first.sku)!.id).toBe(before.id);
  expect(after.get(first.sku)!.price).toBe(first.price + 111);
  if (STOCKED) expect(Number(after.get(STOCKED.sku)!.stock)).toBe(Number(STOCKED.stock));
  const named = (await list<{ name: string }>(context, '/inventory/categories')).filter((row) => CATEGORIES.includes(row.name));
  expect(named.map((row) => row.name).sort()).toEqual([...CATEGORIES].sort());
  await context.close();
});

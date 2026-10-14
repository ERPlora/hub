// Taxes → Categories in Chrome (TAX-F01, TAX-F02; apps/tax/WORKBOOK.md): the owner of hub `a` opens
// Taxes from its address and finds the Spanish factory catalogue (the 11 «System» categories with
// their rate in force today), the tabbar of the three sections that walks to Rules and Aliases, and
// «+» → «New tax category»: a malformed key is refused under Key (422), a good one closes the dialog
// and the row arrives live as «Custom». Screenshots of the page in the three viewports. What it creates
// is deleted after the file (`afterAll`).
import { expect, type Page, test } from '@playwright/test';

import { A, api, login, psql, shot, shown } from './helpers';

const SEED = [
  'product.generic',
  'product.reduced',
  'product.super_reduced',
  'restaurant.alcohol',
  'restaurant.delivery',
  'restaurant.drink',
  'restaurant.food',
  'retail.alcohol',
  'service.education',
  'service.generic',
  'service.health',
];

/** Categories are never deleted by the app: what this file made goes with the database's own hand
 *  (the hub `a`'s), components first, then rules, aliases and the categories. */
const CLEANUP = [
  "delete from tax_taxalias where category_id in (select id from tax_taxcategory where key like 'e2e.%')",
  "delete from tax_taxrule where parent_id is not null and category_id in (select id from tax_taxcategory where key like 'e2e.%')",
  "delete from tax_taxrule where category_id in (select id from tax_taxcategory where key like 'e2e.%')",
  "delete from tax_taxcategory where key like 'e2e.%'",
].join('; ');

test.afterAll(() => {
  psql(CLEANUP);
});

/** No horizontal scroll: the page is not wider than the window (polled while the layout settles). */
async function noHorizontalScroll(page: Page, label: string): Promise<void> {
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth), { message: `no horizontal scroll at ${label}` })
    .toBeLessThanOrEqual(0);
}

const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1194 },
  { label: '1440', width: 1440, height: 900 },
];

/** Waits for the categories list to paint its first result (rows or the empty state). */
async function listReady(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=tax-categories-row], [data-testid=tax-categories-empty]').first().waitFor({ state: 'visible' });
}

const rowIds = (page: Page) => shown(page).locator('[data-testid=tax-categories-row]').evaluateAll((rows) => rows.map((r) => r.getAttribute('data-id')));

test('TAX-F01: the owner sees the Spanish factory categories, filters them by Origin and walks the tabs', async ({ page }) => {
  await login(page, A, '/tax/categories');
  await listReady(page);
  await expect(shown(page).locator('ion-title, .app-topbar__title').first()).toBeVisible();

  // Origin «System»: exactly the eleven categories of the factory catalogue, with their rate.
  await shown(page).locator('[data-testid=tax-categories-filters]').click();
  const origin = page.locator('[data-testid=tax-categories-filter-is_system]');
  await origin.click();
  await page.locator('ion-popover ion-item, ion-popover .select-interface-option').filter({ hasText: /^(System|Sistema)$/ }).first().click();
  await page.locator('[data-testid=tax-categories-filters-done]').click();
  await expect(shown(page).locator('[data-testid=tax-categories-filters-count]')).toHaveText('1');
  await expect.poll(async () => (await rowIds(page)).sort()).toEqual(SEED);
  const food = shown(page).locator('[data-testid=tax-categories-row][data-id="restaurant.food"]');
  await expect(food).toContainText('10.00%');
  await expect(shown(page).locator('[data-testid=tax-categories-row][data-id="service.health"]')).toContainText(/Exempt|Exenta/);
  await page.screenshot({ path: shot('tax-categories-seed-1280') });

  // The tabbar walks the three sections (each on its own address).
  await shown(page).locator('[data-testid=tab-rules]').click();
  await page.waitForURL(/\/tax\/rules$/);
  await shown(page).locator('[data-testid=tax-rules-row], [data-testid=tax-rules-empty]').first().waitFor();
  await shown(page).locator('[data-testid=tab-aliases]').click();
  await page.waitForURL(/\/tax\/aliases$/);
  await shown(page).locator('[data-testid=tax-aliases-row]').first().waitFor();
  await shown(page).locator('[data-testid=tab-categories]').click();
  await page.waitForURL(/\/tax\/categories$/);
  await listReady(page);
});

test('TAX-F02: a malformed key is refused under Key; a good category closes the dialog and arrives live as «Custom»', async ({ page, context }) => {
  await login(page, A, '/tax/categories');
  await listReady(page);
  const key = `e2e.cat_${Date.now().toString(36)}`;

  await shown(page).locator('[data-testid=tax-categories-add]').click();
  const dialog = page.locator('ion-modal[data-testid=tax-category-form]');
  await expect(dialog).toBeVisible();
  await dialog.locator('[data-testid=tax-category-form-key] input').fill('Bad Key!');
  await dialog.locator('[data-testid=tax-category-form-name] input').fill('E2E books');
  await page.screenshot({ path: shot('tax-categories-new-1280') });
  await dialog.locator('[data-testid=tax-category-form-submit]').click();
  // 422: the message under Key, the dialog open with what was typed.
  const keyField = dialog.locator('[data-testid=tax-category-form-key]');
  await expect(keyField).toHaveClass(/ion-invalid/);
  await expect(keyField.locator('.error-text')).not.toBeEmpty();
  await expect(dialog.locator('[data-testid=tax-category-form-key] input')).toHaveValue('Bad Key!');
  await page.screenshot({ path: shot('tax-categories-new-422-1280') });

  await dialog.locator('[data-testid=tax-category-form-key] input').fill(key);
  await dialog.locator('[data-testid=tax-category-form-submit]').click();
  await expect(dialog).toBeHidden();
  const search = shown(page).locator('[data-testid=tax-categories-search] input');
  await search.fill(key);
  const row = shown(page).locator(`[data-testid=tax-categories-row][data-id="${key}"]`);
  await expect(row).toBeVisible();
  await expect(row).toContainText(/Custom|Propia/);
  await expect(row).toContainText('—');

  // The same key again: the 409 under Key, with the server's words.
  await shown(page).locator('[data-testid=tax-categories-add]').click();
  await dialog.locator('[data-testid=tax-category-form-key] input').fill(key);
  await dialog.locator('[data-testid=tax-category-form-name] input').fill('Again');
  await dialog.locator('[data-testid=tax-category-form-submit]').click();
  await expect(dialog.locator('[data-testid=tax-category-form-key] .error-text')).toContainText(/already a tax category|Ya hay una categoría/);
  await dialog.locator('[data-testid=tax-category-form-cancel]').click();

  // Server-side evidence: one category with that key.
  const res = await api<{ total: number }>(context, A, 'GET', `/tax/categories?key=${key}`);
  expect(res.data.total).toBe(1);
});

test('Categories in the three viewports: no horizontal scroll; cards on a phone', async ({ page }) => {
  await login(page, A, '/tax/categories');
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto(`${A}/tax/categories`);
    await listReady(page);
    await noHorizontalScroll(page, vp.label);
    if (vp.width === 390) await expect(shown(page).locator('.data-table__cards')).toBeVisible();
    await page.screenshot({ path: shot(`tax-categories-${vp.label}`) });
  }
});

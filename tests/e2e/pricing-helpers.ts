// Shared steps of the pricing specs (apps/pricing/WORKBOOK.md) against hub `a`, with the real Inventory and
// Customers apps (no doubles): what a spec creates is named «E2E Pricing …» (codes and SKUs E2EPF…), so
// `cleanPricing()` removes exactly that, in every app it touched, before and after the spec.
import { type BrowserContext, expect, type Locator, type Page } from '@playwright/test';

import { A, api, psql, shot, shown } from './helpers';

export const TAG = 'E2E Pricing';
export const CODE = 'E2EPF';

export const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
] as const;
export const DESKTOP = { width: 1280, height: 860 };

/** A unique suffix for this run's data. */
export const stamp = (): string => Date.now().toString(36).toUpperCase();

/** Deletes what the pricing specs created (codes and SKUs `E2EPF…`, names «E2E Pricing …»). */
export function cleanPricing(): void {
  const products = `select id from inventory_product where sku like '${CODE}-%'`;
  const lists = `select id from pricing_pricelist where code like '${CODE}%'`;
  psql(
    [
      `delete from pricing_priceitem where price_list_id in (${lists}) or product_id in (${products})`,
      `delete from pricing_pricelist where code like '${CODE}%'`,
      `delete from pricing_discountrule where code like '${CODE}%'`,
      `delete from inventory_stockmovement where product_id in (${products})`,
      `delete from inventory_productcategory where product_id in (${products})`,
      `delete from inventory_product where sku like '${CODE}-%'`,
      `delete from customer_customergroup where name like '${TAG}%'`,
    ].join('; '),
  );
}

/** Calls the Hub's API as the page's user and checks the status. */
export async function post<T>(context: BrowserContext, path: string, body: unknown, status = 201): Promise<T> {
  const res = await api<T>(context, A, 'POST', path, body);
  expect(res.status, `${path} ${JSON.stringify(res.data)}`).toBe(status);
  return res.data;
}

/** An Inventory product, through Inventory's own API. */
export function createProduct(context: BrowserContext, name: string, sku: string, price: number): Promise<{ id: string }> {
  return post(context, '/inventory/products', { name, sku, price, tax_category_key: 'product.generic' });
}

/** Screenshots of the page shown at the three viewports (`APP-PRICING-<key>-<390|834|1440>`), then back. */
export async function shootFlow(page: Page, key: string, restore = DESKTOP): Promise<string[]> {
  const files: string[] = [];
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    // The tables refit to their box; wait for a frame rather than a fixed time.
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    const file = shot(`APP-PRICING-${key}-${viewport.label}`);
    await page.screenshot({ path: file });
    files.push(file);
  }
  await page.setViewportSize(restore);
  return files;
}

/** The dialog of a FormModal or a ConfirmDialog (Ionic moves it to ion-app). */
export const dialog = (page: Page, testid: string): Locator => page.locator(`ion-modal[data-testid=${testid}]`);

/** Types into an Ionic field of the open dialog. */
export async function fill(page: Page, testid: string, value: string): Promise<void> {
  const input = page.locator(`[data-testid=${testid}] input`).first();
  await input.fill(value);
  await input.blur();
}

/** The row (or card) of `table` that shows `text`. */
export const row = (page: Page, table: string, text: string): Locator =>
  shown(page).locator(`[data-testid=${table}-row]`, { hasText: text });

/** Waits for the first answer of `table`: a row or its empty state. */
export const ready = (page: Page, table: string): Promise<void> =>
  shown(page).locator(`[data-testid=${table}-empty], [data-testid=${table}-row]`).first().waitFor({ state: 'visible' });

/** Narrows `table` to `text` with its search box. */
export async function search(page: Page, table: string, text: string): Promise<void> {
  await shown(page).locator(`[data-testid=${table}-search] input`).fill(text);
}

/** Picks the option of an `ion-select` (its popover) whose text is exactly `label`. */
export async function choose(page: Page, select: Locator, label: string): Promise<void> {
  const popover = page.locator('ion-popover.select-popover');
  await expect(popover).toHaveCount(0);
  await select.click();
  await popover.locator('ion-radio').filter({ hasText: new RegExp(`^\\s*${label}\\s*$`) }).click();
  await expect(popover).toHaveCount(0);
}

/** Shows `label` of the status filter behind the table's funnel (Active, Inactive or All). */
export async function filterStatus(page: Page, table: string, label: 'Active' | 'Inactive' | 'All'): Promise<void> {
  const panel = shown(page).getByTestId(`${table}-filters-panel`);
  await shown(page).getByTestId(`${table}-filters-toggle`).click();
  await expect(panel).toBeVisible();
  await choose(page, panel.getByTestId(`${table}-filter-status`), label);
  await panel.getByTestId(`${table}-filters-apply`).click();
  await expect(panel).toBeHidden();
}

/** Picks the option of a `Combo` whose text holds `text`, searching it by `query`. Only a search the Combo
 *  itself says failed (its `-error` state: runserver restarting because another session saved a `.py`
 *  file, `ERR_CONNECTION_REFUSED`) is asked again, with its «Retry», once `/healthz` answers again, twice
 *  at most; anything else fails at once. */
export async function pick(page: Page, testid: string, query: string, text: string): Promise<void> {
  const input = page.locator(`[data-testid=${testid}] input`);
  const option = page.locator(`[data-testid^=${testid}-option-]`, { hasText: text }).first();
  const failed = page.locator(`[data-testid=${testid}-error]`);
  await input.click();
  await input.fill(query);
  for (let attempt = 1; ; attempt += 1) {
    await option.or(failed).first().waitFor({ state: 'visible' });
    if (await option.isVisible()) break;
    if (attempt === 3) throw new Error(`pick ${testid}: the search kept failing: ${await failed.innerText()}`);
    console.warn(`pick ${testid}: the search failed (attempt ${attempt}); asking it again once the server answers`);
    await expect
      .poll(async () => (await page.request.get(`${A}/healthz`).catch(() => null))?.status() ?? 0, { timeout: 30_000 })
      .toBe(200);
    await page.locator(`[data-testid=${testid}-retry]`).click();
  }
  await option.click();
}

/** Runs a row action: its button, or the same entry inside «⋮» when the row folds its actions. */
export async function rowAction(page: Page, table: string, id: string, action: string): Promise<void> {
  const button = shown(page).locator(`[data-testid=${table}-row-${id}-${action}]`);
  const menu = shown(page).locator(`[data-testid=${table}-row-${id}-menu]`);
  await button.or(menu).first().waitFor({ state: 'visible' });
  if (await button.isVisible()) {
    await button.click();
    return;
  }
  await menu.click();
  await page.locator(`ion-popover [data-testid=${table}-row-${id}-${action}]`).click();
}

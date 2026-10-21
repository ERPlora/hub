// flow: SALE-F07 (apps/sale/WORKBOOK.md), with INVENTORY-F29 — an article marked sold out («86») in Inventory
// stays in the till, greyed with «Sold out»: a tap adds nothing and says why, and its search row says it
// too, while the article next to it still sells. Through the API (the assistant's way, which never sees the
// grid) a new line of it is a 409 `sale.product_sold_out` and nothing is written. What was ordered before it
// sold out is still charged (apps/sale/tests/test_integration_inventory.py). Screenshots of the till in
// the three viewports. What this file creates is deleted after it.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, login, shot, shown } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { cleanSales, drawerOff, restoreDrawer, saleByKey, stamp } from './sale-helpers';

const RUN = stamp();
let croquettes: Product;
let bread: Product;

/** The widths of this task's screenshots, as the SaaS panel's `VIEWPORTS`. */
const SHOTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
] as const;

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  // The till opens without a cash session: the drawer's lock is sale-cash-gate.spec.ts's.
  await drawerOff(context);
  croquettes = await createProduct(context, { name: `E2E Croquettes ${RUN}`, sku: `E2E-SO-C-${RUN}`, price: 650, tax_category_key: 'restaurant.food' });
  bread = await createProduct(context, { name: `E2E Bread ${RUN}`, sku: `E2E-SO-B-${RUN}`, price: 120, tax_category_key: 'restaurant.food' });
  const marked = await api<{ is_sold_out: boolean }>(context, A, 'POST', '/inventory/products/sold_out', { id: croquettes.id, sold_out: true });
  expect(marked.status, 'mark sold out').toBe(200);
  await context.close();
});

test.afterAll(() => {
  cleanSales();
  cleanInventory();
  restoreDrawer();
});

const tile = (page: Page, product: Product): Locator => shown(page).locator(`[data-testid=pos-product-${product.id}]`);
const linesOf = (page: Page, product: Product): Locator => shown(page).locator('[data-testid^=pos-line-]').filter({ hasText: product.name });

async function tillReady(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  await tile(page, bread).waitFor({ state: 'visible' });
}

async function openCart(page: Page): Promise<void> {
  const fab = shown(page).locator('[data-testid=pos-cart-fab]');
  if (await fab.isVisible()) await fab.click();
}

test('SALE-F07: a sold-out article is greyed «Sold out» in the till; a tap adds nothing and says why', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  await tillReady(page);

  // In the grid, greyed with its badge; the article beside it sells as always.
  const soldOut = tile(page, croquettes);
  await expect(soldOut).toBeVisible();
  await expect(soldOut).toHaveClass(/pos-tile--sold-out/);
  await expect(soldOut).toHaveAttribute('aria-disabled', 'true');
  await expect(soldOut.locator('.pos-tile__badge')).toHaveText(/^(Sold out|Agotado)$/);
  await expect(tile(page, bread)).not.toHaveClass(/pos-tile--sold-out/);

  // A tap adds nothing: the reason goes above the grid. The tile is `aria-disabled` but takes the tap (a
  // touchscreen would swallow a native `disabled`), so the mouse clicks it as a finger would.
  await soldOut.click({ force: true });
  const notice = shown(page).locator('[data-testid=pos-tap-notice]');
  await expect(notice).toHaveText(new RegExp(`^«${croquettes.name}» (is sold out|está agotado)\\.$`));
  await expect(linesOf(page, croquettes)).toHaveCount(0);

  // The search finds it and says it is sold out instead of its SKU; picking it adds nothing either.
  await shown(page).locator('[data-testid=pos-search-trigger]').click();
  const search = page.locator('[data-testid=pos-search]');
  await search.locator('input').fill(croquettes.sku);
  const row = search.locator(`[data-testid=pos-search-${croquettes.id}]`);
  await expect(row.locator('p')).toHaveText(/^(Sold out|Agotado)$/);
  await page.screenshot({ path: shot('FIX-SALE-SOLD-OUT-LINE-ACCEPTED-search-1440') });
  await row.click();
  await expect(search).toBeHidden();
  await expect(notice).toHaveText(new RegExp(`^«${croquettes.name}» (is sold out|está agotado)\\.$`));
  await expect(linesOf(page, croquettes)).toHaveCount(0);

  // In each viewport, a till opened there (on a phone the check is the drawer behind the button): the
  // greyed tile, a tap that adds nothing and its reason above the grid.
  for (const size of SHOTS) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await page.goto(`${A}/sale/pos`);
    await tillReady(page);
    await tile(page, croquettes).click({ force: true });
    await expect(notice).toHaveText(new RegExp(`^«${croquettes.name}» (is sold out|está agotado)\\.$`));
    await expect(tile(page, croquettes).locator('.pos-tile__badge')).toBeVisible();
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await page.screenshot({ path: shot(`FIX-SALE-SOLD-OUT-LINE-ACCEPTED-${size.label}`) });
  }

  // The article on sale still goes into the check.
  await page.setViewportSize({ width: 1440, height: 900 });
  await tile(page, bread).click();
  await openCart(page);
  await expect(linesOf(page, bread).first()).toBeVisible();
  await expect(linesOf(page, croquettes)).toHaveCount(0);
});

test('SALE-F07: through the API a new line of a sold-out article is a 409 and nothing is written', async ({ page, context }) => {
  await login(page, A, '/sale/pos');
  const opened = await api<{ error: { code: string; message: string } }>(context, A, 'POST', '/sale/orders', {
    label: `e2e sold out ${RUN}`,
    lines: [{ product: croquettes.sku }],
  });
  expect(opened.status).toBe(409);
  expect(opened.data.error.code).toBe('sale.product_sold_out');
  expect(opened.data.error.message).toMatch(new RegExp(`^«${croquettes.name}» (is sold out|está agotado)\\.$`));
  const charged = await api<{ error: { code: string } }>(context, A, 'POST', '/sale/sales', {
    idempotency_key: `e2e-sold-out-${RUN}`,
    lines: [{ product: croquettes.name }],
    payments: [{ method: 'card' }],
  });
  expect(charged.status).toBe(409);
  expect(charged.data.error.code).toBe('sale.product_sold_out');
  expect(await saleByKey(context, `e2e-sold-out-${RUN}`)).toBeNull();
});

// flow: INVENTORY-F28 INVENTORY-F17
// Inventory's hooks of the Home (FIX-INVENTORY-SETUP-HOOKS; the old module's `setup` and `widgets`, the old hub's
// dashboard in docs/reference/old-hub/dashboard-*.png), as the owner of hub `a` reads them in Spanish: «Tu catálogo»
// pending and «Importante» in «Termina de configurar tu negocio» while the hub has no active product (its «Configurar»
// leads to Inventory → Products), done without a reload once one is added and pending again when it is turned off;
// «Productos con stock bajo», «Valor de existencias (a coste)» and «Productos con menos stock» on the board by default
// with the server's figures, and «Productos en stock» to add, leaving the captures
// `FIX-INVENTORY-SETUP-HOOKS-INVENTORY-F28-<width>` (the step) and `…-INVENTORY-F17-<width>` (the four panels).
// The products the hub already had are turned off for the run and back on after it; the run's own are `E2E-…`,
// which `cleanInventory()` removes.
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, horizontalOverflow, login, psql, shot, shown, untilStill } from './helpers';
import { cleanInventory, createProduct, stamp, VIEWPORTS } from './inventory-helpers';

const KEY = 'FIX-INVENTORY-SETUP-HOOKS';
const STEP = 'inventory.catalog';
const PANELS = ['inventory.low_stock_count', 'inventory.value', 'inventory.in_stock', 'inventory.low_stock_products'];
const DEFAULT_PANELS = PANELS.filter((key) => key !== 'inventory.in_stock');
const TITLES = ['Productos con stock bajo', 'Valor de existencias (a coste)', 'Productos en stock', 'Productos con menos stock'];
/** Where the Home keeps this browser's board (base/frontend/lib/home.ts `BOARD_STORAGE_KEY`). */
const BOARD = 'dashboard-hub';
/** The hub's own active products, turned off while the run needs an empty catalog. */
const PARKED = 'e2e_fix_inv_hooks_parked';

test.describe.configure({ mode: 'serial' });

test.beforeAll(() => {
  cleanInventory();
  psql(
    [
      `drop table if exists ${PARKED}`,
      `create table ${PARKED} as select id from inventory_product where is_active and not is_deleted`,
      `update inventory_product set is_active = false where id in (select id from ${PARKED})`,
    ].join('; '),
  );
});

test.afterAll(() => {
  cleanInventory();
  psql([`update inventory_product set is_active = true where id in (select id from ${PARKED})`, `drop table ${PARKED}`].join('; '));
});

/** The owner on `a` in Spanish (the Hub's language cookie, as the sign-in sets it from the account), on the Home. */
async function spanishOwner(
  browser: Browser,
  viewport: { width: number; height: number },
  board?: string[],
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'es-ES' });
  if (board) await context.addInitScript(([key, keys]) => localStorage.setItem(key, keys), [BOARD, JSON.stringify(board)]);
  const page = await context.newPage();
  await login(page, A, '/');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}/`);
  await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
  await expect(card(page)).toHaveAttribute('aria-busy', 'false');
  // The owner's Spanish session with Inventory's four panels for the fleet's visual sweep
  // (`ui-clip-sweep.sh --storage-state`), when asked.
  if (board && process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  return { context, page };
}

const card = (page: Page): Locator => shown(page).locator('[data-testid="setup-card"]');
const row = (page: Page): Locator => card(page).locator(`[data-testid="setup-row"][data-key="${STEP}"]`);
const panel = (page: Page, key: string): Locator =>
  shown(page).locator(`[data-testid="widget-board"] [data-testid="widget"][data-key="${key}"]`);

/** A low-stock article: 2 left at 1.25 € each, under its threshold of 5. */
async function lowStockProduct(context: BrowserContext): Promise<{ id: string; name: string }> {
  const id = stamp();
  return createProduct(context, {
    name: `E2E Café ${id}`,
    sku: `E2E-CAF-${id}`,
    cost: 125,
    initial_stock: '2',
    low_stock_threshold: '5',
    track_stock: true,
  });
}

interface Summary {
  products_low_stock: number;
  products_in_stock: number;
  stock_value: number;
}

test('INVENTORY-F28: «Tu catálogo» pending without products, done with one and pending again when it is turned off', async ({ browser }) => {
  const { context, page } = await spanishOwner(browser, { width: 1440, height: 900 });
  try {
    // Pending with no active product: «Importante», never «Necesario para facturar».
    await expect(row(page).locator('.setup-row-title')).toHaveText('Tu catálogo');
    await expect(row(page).locator('.setup-row-desc')).toHaveText('Añade al menos un producto para que haya algo que vender.');
    await expect(row(page).locator('[data-testid="setup-pill"]')).toHaveText('Importante');

    // «Configurar» leads to Inventory → Products.
    await row(page).locator(`[data-testid="setup-configure-${STEP}"]`).click();
    await expect(page).toHaveURL(`${A}/inventory/products`);
    await page.goto(`${A}/`);
    await expect(row(page)).toBeVisible();

    // One product: the step is done without a reload (it leaves the folded list; «Ver todo» says «Hecho»).
    const product = await lowStockProduct(context);
    await expect(row(page)).toHaveCount(0);
    await card(page).locator('[data-testid="setup-toggle"]').click();
    await expect(row(page).locator('[data-testid="setup-pill"]')).toHaveText('Hecho');
    await expect(row(page).locator(`[data-testid="setup-configure-${STEP}"]`)).toHaveCount(0);

    // Turned off, the catalog is empty again: pending without a reload.
    const off = await api(context, A, 'POST', '/inventory/products/update', { id: product.id, is_active: false });
    expect(off.status).toBe(200);
    await expect(row(page).locator('[data-testid="setup-pill"]')).toHaveText('Importante');
    await expect(row(page).locator(`[data-testid="setup-configure-${STEP}"]`)).toBeVisible();
  } finally {
    await context.close();
    cleanInventory();
  }
});

test('INVENTORY-F17: Inventory\'s three default panels on the Home with the server\'s figures, «Productos en stock» to add', async ({ browser }) => {
  const { context, page } = await spanishOwner(browser, { width: 1440, height: 900 });
  try {
    const product = await lowStockProduct(context);
    const summary = await api<Summary>(context, A, 'GET', '/inventory/stock/summary');
    expect(summary.status).toBe(200);
    expect(summary.data.products_low_stock).toBeGreaterThan(0);

    for (const key of DEFAULT_PANELS) await expect(panel(page, key)).toBeVisible();
    await expect(panel(page, 'inventory.in_stock')).toHaveCount(0);
    const number = new Intl.NumberFormat('es-ES');
    const money = new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR' });
    const low = panel(page, 'inventory.low_stock_count');
    await expect(low.locator('[data-testid="widget-title"]')).toHaveText('Productos con stock bajo');
    await expect(low.locator('[data-testid="widget-value"]')).toHaveText(number.format(summary.data.products_low_stock));
    const value = panel(page, 'inventory.value');
    await expect(value.locator('[data-testid="widget-title"]')).toHaveText('Valor de existencias (a coste)');
    await expect(value.locator('[data-testid="widget-value"]')).toHaveText(money.format(summary.data.stock_value / 100));
    const lowest = panel(page, 'inventory.low_stock_products');
    await expect(lowest.locator('[data-testid="widget-title"]')).toHaveText('Productos con menos stock');
    await expect(lowest).toContainText(product.name);

    // «Personalizar panel» offers «Productos en stock», grouped under «Inventario».
    await shown(page).locator('[data-testid="widgets-customize"]').click();
    const picker = page.locator('ion-modal[data-testid="widgets-picker"]:not(.overlay-hidden)');
    await expect(picker.locator('[data-testid="widgets-add-inventory.in_stock"]')).toBeVisible();
    await expect(picker).toContainText('Inventario');
  } finally {
    await context.close();
    cleanInventory();
  }
});

for (const size of VIEWPORTS) {
  test(`INVENTORY-F28 and INVENTORY-F17 at ${size.label}: the step pending, then done with a product and the four panels with its figures`, async ({ browser }) => {
    const { context, page } = await spanishOwner(browser, { width: size.width, height: size.height }, PANELS);
    try {
      // The step in sight while pending, with no sideways scroll; the panels read, with nothing to count yet.
      await expect(row(page).locator('[data-testid="setup-pill"]')).toHaveText('Importante');
      for (const key of PANELS) await expect(panel(page, key)).toHaveAttribute('aria-busy', 'false');
      await expect(panel(page, 'inventory.low_stock_count').locator('[data-testid="widget-value"]')).toHaveText('0');
      await expect(panel(page, 'inventory.low_stock_products').locator('[data-testid="widget-empty"]')).toHaveText('Sin datos');
      await row(page).evaluate((element) => element.scrollIntoView({ block: 'start' }));
      await untilStill(page);
      const overflow = () => horizontalOverflow(page);
      expect(await overflow(), `no sideways scroll at ${size.label}`).toBeLessThanOrEqual(0);
      await page.screenshot({ path: shot(`${KEY}-INVENTORY-F28-${size.label}`) });

      // A product: the step leaves the list and the four panels paint its figures.
      const product = await lowStockProduct(context);
      await expect(row(page)).toHaveCount(0);
      for (const [index, key] of PANELS.entries()) {
        await expect(panel(page, key).locator('[data-testid="widget-title"]')).toHaveText(TITLES[index]);
        await expect(panel(page, key).locator('[data-testid="widget-error"]')).toHaveCount(0);
        await expect(panel(page, key)).toHaveAttribute('aria-busy', 'false');
      }
      await expect(panel(page, 'inventory.in_stock').locator('[data-testid="widget-value"]')).toHaveText('1');
      await expect(panel(page, 'inventory.low_stock_products')).toContainText(product.name);
      await panel(page, 'inventory.low_stock_count').evaluate((element) => element.scrollIntoView({ block: 'start' }));
      await untilStill(page);
      expect(await overflow(), `no sideways scroll at ${size.label}`).toBeLessThanOrEqual(0);
      await page.screenshot({ path: shot(`${KEY}-INVENTORY-F17-${size.label}`) });
    } finally {
      await context.close();
      cleanInventory();
    }
  });
}

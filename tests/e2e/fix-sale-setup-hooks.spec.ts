// flow: paneles de Ventas en el Inicio (hooks de LiveAppConfig) — the old hub's dashboard with Sales' four panels
// (docs/reference/old-hub/dashboard-*.png), as the owner of hub `a` reads it in Spanish: «Ventas hoy» and «Tickets
// hoy» on by default with today's figures, both moving without a reload when another sale is charged, and «Ventas
// últimos 7 días» and «Actividad reciente» turned on from «Customize panel». Each viewport leaves its capture
// `FIX-SALE-SETUP-HOOKS-<width>` with the four panels on the board.
// Amounts of three digits (2,50 €): the Home's thousands separator is FIX-HUB-MONEY-THOUSANDS-SEPARATOR's, so the
// expected text is the server's figure formatted as the panel does, whatever the day's total. What this file creates
// is deleted after it (`cleanSales()`, `cleanInventory()`).
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, horizontalOverflow, login, shot, shown, untilStill } from './helpers';
import { cleanInventory, createProduct } from './inventory-helpers';
import { chargeByApi, cleanSales, drawerOff, restoreDrawer, stamp } from './sale-helpers';

const KEY = 'FIX-SALE-SETUP-HOOKS';
const SKU = `E2E-HOME-${stamp()}`;
const PRICE = 250;
const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];
const DEFAULTS = ['sale.today', 'sale.tickets_today'];
const ALL = [...DEFAULTS, 'sale.last_7_days', 'sale.recent_activity'];
/** Where the Home keeps this browser's board (base/frontend/lib/home.ts `BOARD_STORAGE_KEY`). */
const BOARD = 'dashboard-hub';

interface Today {
  total: number;
  tickets: number;
}

const money = new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR' });
const count = new Intl.NumberFormat('es-ES');

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/sales');
  // The cash register's lock is SALE-F08's: here a sale charges in cash without opening a session.
  await drawerOff(context);
  await createProduct(context, { name: 'E2E Home panel', sku: SKU, price: PRICE, tax_category_key: 'product.generic' });
  await context.close();
});

test.afterAll(() => {
  try {
    cleanSales();
  } finally {
    try {
      cleanInventory();
    } finally {
      restoreDrawer();
    }
  }
});

/** The owner on `a` in Spanish (the Hub's language cookie, as the sign-in sets it from the account), on the Home. */
async function spanishOwner(browser: Browser, viewport: { width: number; height: number }, board?: string[]): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'es-ES' });
  if (board) await context.addInitScript(([key, keys]) => localStorage.setItem(key, keys), [BOARD, JSON.stringify(board)]);
  const page = await context.newPage();
  await login(page, A, '/');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}/`);
  await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
  // The owner's Spanish session with the board of four panels for the fleet's visual sweep
  // (`ui-clip-sweep.sh --storage-state`), when asked.
  if (board && process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  return { context, page };
}

const panel = (page: Page, key: string): Locator => shown(page).locator(`[data-testid="widget-board"] [data-testid="widget"][data-key="${key}"]`);

async function today(context: BrowserContext): Promise<Today> {
  const res = await api<Today>(context, A, 'GET', '/sale/sales/today');
  expect(res.status).toBe(200);
  return res.data;
}

async function charge(context: BrowserContext): Promise<string> {
  const sale = await chargeByApi(context, { lines: [{ product: SKU }], payments: [{ method: 'cash' }] });
  expect(sale.total).toBe(PRICE);
  return sale.number;
}

/** The two default panels say the day's money and tickets the server counts. */
async function figuresAre(page: Page, figures: Today): Promise<void> {
  await expect(panel(page, 'sale.today').locator('[data-testid="widget-value"]')).toHaveText(money.format(figures.total / 100));
  await expect(panel(page, 'sale.tickets_today').locator('[data-testid="widget-value"]')).toHaveText(count.format(figures.tickets));
}

test('paneles de Ventas en el Inicio (hooks de LiveAppConfig): today\'s figures by default, live, and the other two from «Customize panel»', async ({ browser }) => {
  const { context, page } = await spanishOwner(browser, { width: 1440, height: 900 });
  try {
    const first = await charge(context);
    await page.reload();

    // The defaults: «Ventas hoy» and «Tickets hoy», with what the server counts today.
    for (const [key, title] of [['sale.today', 'Ventas hoy'], ['sale.tickets_today', 'Tickets hoy']]) {
      await expect(panel(page, key).locator('[data-testid="widget-title"]')).toHaveText(title);
    }
    await expect(panel(page, 'sale.last_7_days')).toHaveCount(0);
    await expect(panel(page, 'sale.recent_activity')).toHaveCount(0);
    const before = await today(context);
    expect(before.tickets).toBeGreaterThanOrEqual(1);
    await figuresAre(page, before);

    // Followed live: another sale charged elsewhere moves both figures without a reload.
    const second = await charge(context);
    await figuresAre(page, { total: before.total + PRICE, tickets: before.tickets + 1 });

    // «Customize panel»: the other two are offered and turned on, after the defaults.
    await shown(page).locator('[data-testid="widgets-customize"]').click();
    const picker = page.locator('ion-modal[data-testid="widgets-picker"]:not(.overlay-hidden)');
    for (const key of DEFAULTS) await expect(picker.locator(`[data-testid="widgets-active-item"][data-key="${key}"]`)).toBeVisible();
    await picker.locator('[data-testid="widgets-add-sale.last_7_days"]').click();
    await picker.locator('[data-testid="widgets-add-sale.recent_activity"]').click();
    await picker.locator('[data-testid="widgets-close"]').click();
    await expect(picker).toBeHidden();

    // «Ventas últimos 7 días»: seven days, oldest first, today with what was sold.
    const chart = panel(page, 'sale.last_7_days');
    await expect(chart.locator('[data-testid="widget-title"]')).toHaveText('Ventas últimos 7 días');
    await expect(chart.locator('.widget-chart-col')).toHaveCount(7);
    await expect(chart.locator('[data-testid="widget-chart-amount"]')).toHaveText(money.format((before.total + PRICE) / 100));
    // «Actividad reciente»: the last sales, newest first.
    const activity = panel(page, 'sale.recent_activity');
    await expect(activity.locator('[data-testid="widget-title"]')).toHaveText('Actividad reciente');
    await expect(activity.locator('[data-testid="widget-entry"] strong').first()).toHaveText(second);
    await expect(activity.locator('[data-testid="widget-entry"] strong').nth(1)).toHaveText(first);

    // The choice stays on this device.
    await page.reload();
    for (const key of ALL) await expect(panel(page, key)).toBeVisible();
  } finally {
    await context.close();
  }
});

for (const size of SIZES) {
  test(`paneles de Ventas en el Inicio (hooks de LiveAppConfig) at ${size.label}: the four panels on the board`, async ({ browser }) => {
    const { context, page } = await spanishOwner(browser, { width: size.width, height: size.height }, ALL);
    try {
      for (const key of ALL) {
        await expect(panel(page, key).locator('[data-testid="widget-error"]')).toHaveCount(0);
        await expect(panel(page, key)).toHaveAttribute('aria-busy', 'false');
      }
      // The board at the top of the screen, as far as the page scrolls.
      await panel(page, 'sale.today').evaluate((element) => element.scrollIntoView({ block: 'start' }));
      await untilStill(page);
      const overflow = await horizontalOverflow(page);
      expect(overflow, `no sideways scroll at ${size.label}`).toBeLessThanOrEqual(0);
      await page.screenshot({ path: shot(`${KEY}-${size.label}`) });
    } finally {
      await context.close();
    }
  });
}

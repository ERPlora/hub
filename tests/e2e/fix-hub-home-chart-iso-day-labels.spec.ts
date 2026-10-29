// flow: BASE-F06 «Ver los paneles de las apps en Inicio» (panel `kind: chart`) — the old hub's gh:hub#2392, back in
// the new Home: Sales' «Ventas últimos 7 días» painted each day as `2026-10-23` («2026…» cut at 390 px) and no amount
// at all. The owner of hub `a` reads it in Spanish with two sales today and one yesterday: each bar says its weekday
// («vie»); above the bars, the chosen day and its amount, today's until another bar is tapped; no text cut nor sideways
// scroll at 390, 834 and 1440 px. Each viewport leaves its capture `FIX-HUB-HOME-CHART-ISO-DAY-LABELS-<width>`. What
// this file creates is deleted after it (`cleanSales()`, `cleanInventory()`).
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, horizontalOverflow, login, psql, shot, shown, untilStill } from './helpers';
import { cleanInventory, createProduct } from './inventory-helpers';
import { chargeByApi, cleanSales, drawerOff, restoreDrawer, stamp } from './sale-helpers';

const KEY = 'FIX-HUB-HOME-CHART-ISO-DAY-LABELS';
const SKU = `E2E-CHART-${stamp()}`;
const PRICE = 250;
const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];
const PANEL = 'sale.last_7_days';
/** Where the Home keeps this browser's board (base/frontend/lib/home.ts `BOARD_STORAGE_KEY`). */
const BOARD = 'dashboard-hub';

interface Day {
  day: string;
  total: number;
}

const money = new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR' });

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/sales');
  // The cash register's lock is SALE-F08's: here a sale charges in cash without opening a session.
  await drawerOff(context);
  await createProduct(context, { name: 'E2E Home chart', sku: SKU, price: PRICE, tax_category_key: 'product.generic' });
  // Sales on two business days: two today, and one moved to yesterday (setup: the till only charges today).
  for (let i = 0; i < 3; i += 1) {
    const sale = await chargeByApi(context, { lines: [{ product: SKU }], payments: [{ method: 'cash' }] });
    expect(sale.total).toBe(PRICE);
    if (i === 0) psql(`update sale_sale set business_day = business_day - 1 where number = '${sale.number}'`);
  }
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

/** The owner on `a` in Spanish (the Hub's language cookie, as the sign-in sets it), with only the chart on the board. */
async function spanishOwner(browser: Browser, viewport: { width: number; height: number }): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'es-ES' });
  await context.addInitScript(([key, keys]) => localStorage.setItem(key, keys), [BOARD, JSON.stringify([PANEL])]);
  const page = await context.newPage();
  await login(page, A, '/');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}/`);
  await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
  return { context, page };
}

const panel = (page: Page): Locator => shown(page).locator(`[data-testid="widget-board"] [data-testid="widget"][data-key="${PANEL}"]`);

/** The server's seven days, oldest first. */
async function week(context: BrowserContext): Promise<Day[]> {
  const res = await api<{ rows: Day[] }>(context, A, 'GET', '/sale/sales/last_7_days');
  expect(res.status).toBe(200);
  expect(res.data.rows).toHaveLength(7);
  return res.data.rows;
}

/** How the browser itself says a civil day in Spanish: its short weekday and the whole day («vie», «vie, 23 oct»). */
async function spanishDays(page: Page, days: string[]): Promise<{ weekday: string; full: string }[]> {
  return page.evaluate((list) => {
    const weekday = new Intl.DateTimeFormat('es', { weekday: 'short', timeZone: 'UTC' });
    const full = new Intl.DateTimeFormat('es', { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC' });
    return list.map((day) => {
      const at = new Date(`${day}T00:00:00Z`);
      return { weekday: weekday.format(at), full: full.format(at) };
    });
  }, days);
}

/** Every text of the chart whole: nothing ellipsed, squeezed nor spilling out of its box. */
async function cutTexts(chart: Locator): Promise<string[]> {
  return chart.locator('.widget-chart-label, [data-testid="widget-chart-day"], [data-testid="widget-chart-amount"]').evaluateAll((nodes) =>
    nodes
      .filter((node) => node.scrollWidth > node.clientWidth + 1 || node.scrollHeight > node.clientHeight + 1)
      .map((node) => node.textContent ?? ''),
  );
}

/** Each bar's height as a share of its track (the tallest day fills it). */
async function barShares(chart: Locator): Promise<number[]> {
  return chart.locator('.widget-chart-track').evaluateAll((tracks) =>
    tracks.map((track) => Math.round((track.firstElementChild?.getBoundingClientRect().height ?? 0) / track.getBoundingClientRect().height * 100) / 100),
  );
}

/** The days under the bars on one line, whatever each bar's height: the tops of their labels. */
async function labelTops(chart: Locator): Promise<number[]> {
  return chart.locator('.widget-chart-label').evaluateAll((nodes) => nodes.map((node) => Math.round(node.getBoundingClientRect().top)));
}

for (const size of SIZES) {
  test(`BASE-F06 «Ventas últimos 7 días» at ${size.label}: each day by its weekday and the chosen day's amount, nothing cut`, async ({ browser }) => {
    const { context, page } = await spanishOwner(browser, { width: size.width, height: size.height });
    try {
      const rows = await week(context);
      const [yesterday, today] = rows.slice(-2);
      expect(today.total, 'today counts the two sales charged today').toBeGreaterThanOrEqual(2 * PRICE);
      expect(yesterday.total, 'yesterday counts the sale moved to yesterday').toBeGreaterThanOrEqual(PRICE);
      const said = await spanishDays(page, rows.map((row) => row.day));

      const chart = panel(page);
      await expect(chart.locator('[data-testid="widget-title"]')).toHaveText('Ventas últimos 7 días');
      await expect(chart).toHaveAttribute('aria-busy', 'false');
      const bars = chart.locator('[data-testid="widget-chart-bar"]');
      await expect(bars).toHaveCount(7);

      // Each bar says its weekday, never the ISO date; its accessible name, the whole day and its amount.
      await expect(bars).toHaveText(said.map((day) => day.weekday));
      await expect(chart).not.toContainText(rows[0].day.slice(0, 4));
      for (const [index, row] of rows.entries()) {
        await expect(bars.nth(index)).toHaveAttribute('aria-label', `${said[index].full}: ${money.format(row.total / 100)}`);
      }

      // Above the bars, today's day and amount; another bar tapped says its own.
      const day = chart.locator('[data-testid="widget-chart-day"]');
      const amount = chart.locator('[data-testid="widget-chart-amount"]');
      await expect(day).toHaveText(said[6].full);
      await expect(amount).toHaveText(money.format(today.total / 100));
      await expect(bars.nth(6)).toHaveAttribute('aria-pressed', 'true');

      await chart.evaluate((element) => element.scrollIntoView({ block: 'center' }));
      await untilStill(page);
      expect(await cutTexts(chart), `no text cut at ${size.label}`).toEqual([]);
      const max = Math.max(...rows.map((row) => row.total));
      const shares = await barShares(chart);
      for (const [index, row] of rows.entries()) {
        if (row.total > 0) expect(shares[index], `the bar of ${row.day} at ${size.label}`).toBeCloseTo(row.total / max, 1);
      }
      const tops = await labelTops(chart);
      expect(tops, `the days on one line at ${size.label}`).toEqual(tops.map(() => tops[0]));
      const overflow = await horizontalOverflow(page);
      expect(overflow, `no sideways scroll at ${size.label}`).toBeLessThanOrEqual(0);
      await page.screenshot({ path: shot(`${KEY}-${size.label}`) });

      await bars.nth(5).click();
      await expect(day).toHaveText(said[5].full);
      await expect(amount).toHaveText(money.format(yesterday.total / 100));
      await expect(bars.nth(5)).toHaveAttribute('aria-pressed', 'true');
      await expect(bars.nth(6)).toHaveAttribute('aria-pressed', 'false');
      expect(await cutTexts(chart), `no text cut at ${size.label} with yesterday chosen`).toEqual([]);
    } finally {
      await context.close();
    }
  });
}

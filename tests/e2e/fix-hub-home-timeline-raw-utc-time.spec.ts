// flow: BASE-F06 «Ver los paneles de las apps en Inicio» (panel `kind: timeline`; the «Actividad» tab does not change)
// — Sales' «Actividad reciente» painted each sale's time as the server sends it, `2026-10-23T02:23:55.572622Z`. The owner
// of hub `a` reads it in Spanish on a device in Madrid whose clock says Friday 23 Oct 2026, 12:00: a sale of 09:15 that
// day says «9:15», one of yesterday 18:10 «Ayer 18:10» and one of the 20th «20 oct, 18:10», each in a `<time>` with the
// instant whole; no text cut nor sideways scroll at 390, 834 and 1440 px. Each viewport leaves its capture
// `FIX-HUB-HOME-TIMELINE-RAW-UTC-TIME-<width>`. What this file creates is deleted after it (`cleanSales()`,
// `cleanInventory()`).
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, horizontalOverflow, login, psql, shot, shown, untilStill } from './helpers';
import { cleanInventory, createProduct } from './inventory-helpers';
import { chargeByApi, cleanSales, drawerOff, restoreDrawer, stamp } from './sale-helpers';

const KEY = 'FIX-HUB-HOME-TIMELINE-RAW-UTC-TIME';
const SKU = `E2E-TIMELINE-${stamp()}`;
const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];
const PANEL = 'sale.recent_activity';
/** Where the Home keeps this browser's board (base/frontend/lib/home.ts `BOARD_STORAGE_KEY`). */
const BOARD = 'dashboard-hub';
const ZONE = 'Europe/Madrid';
/** The device's clock: Friday 23 Oct 2026, 12:00 in Madrid. */
const NOW = new Date('2026-10-23T10:00:00Z');

/** Each sale's moment in Madrid's wall time, the instant it is, how the panel says it and says it whole. */
const MOMENTS = [
  { local: '2026-10-23 09:15:00', instant: '2026-10-23T07:15:00.000Z', said: '9:15', whole: '23 oct 2026, 9:15' },
  { local: '2026-10-22 18:10:00', instant: '2026-10-22T16:10:00.000Z', said: 'Ayer 18:10', whole: '22 oct 2026, 18:10' },
  { local: '2026-10-20 18:10:00', instant: '2026-10-20T16:10:00.000Z', said: '20 oct, 18:10', whole: '20 oct 2026, 18:10' },
];
const numbers: string[] = [];

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/sales');
  // The cash register's lock is SALE-F08's: here a sale charges in cash without opening a session.
  await drawerOff(context);
  await createProduct(context, { name: 'E2E Home timeline', sku: SKU, price: 250, tax_category_key: 'product.generic' });
  // Setup: the till only charges now; each sale is then moved to its moment in Madrid's wall time.
  for (const moment of MOMENTS) {
    const sale = await chargeByApi(context, { lines: [{ product: SKU }], payments: [{ method: 'cash' }] });
    psql(`update sale_sale set created_at = timestamp '${moment.local}' at time zone '${ZONE}' where number = '${sale.number}'`);
    numbers.push(sale.number);
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

/** The owner on `a` in Spanish on a device in Madrid at `NOW`, with only «Actividad reciente» on the board. */
async function spanishOwner(browser: Browser, viewport: { width: number; height: number }): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'es-ES', timezoneId: ZONE });
  await context.clock.setFixedTime(NOW);
  await context.addInitScript(([key, keys]) => localStorage.setItem(key, keys), [BOARD, JSON.stringify([PANEL])]);
  const page = await context.newPage();
  await login(page, A, '/');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}/`);
  await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
  // The owner's Spanish session with this board for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`),
  // when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  return { context, page };
}

const panel = (page: Page): Locator => shown(page).locator(`[data-testid="widget-board"] [data-testid="widget"][data-key="${PANEL}"]`);

/** Every text of the timeline whole: nothing ellipsed, squeezed nor spilling out of its box. */
async function cutTexts(timeline: Locator): Promise<string[]> {
  return timeline.locator('[data-testid="widget-entry"] > *').evaluateAll((nodes) =>
    nodes
      .filter((node) => node.scrollWidth > node.clientWidth + 1 || node.scrollHeight > node.clientHeight + 1)
      .map((node) => node.textContent ?? ''),
  );
}

for (const size of SIZES) {
  test(`BASE-F06 «Actividad reciente» at ${size.label}: each sale's local time, «Ayer» or its date, never the raw ISO`, async ({ browser }) => {
    const { context, page } = await spanishOwner(browser, { width: size.width, height: size.height });
    try {
      const timeline = panel(page);
      await expect(timeline.locator('[data-testid="widget-title"]')).toHaveText('Actividad reciente');
      await expect(timeline).toHaveAttribute('aria-busy', 'false');

      for (const [index, moment] of MOMENTS.entries()) {
        const entry = timeline.locator('[data-testid="widget-entry"]').filter({ hasText: numbers[index] });
        await expect(entry).toHaveCount(1);
        const time = entry.locator('time[data-testid="widget-entry-time"]');
        await expect(time, `the sale of ${moment.local} in Madrid`).toHaveText(moment.said);
        const datetime = await time.getAttribute('datetime');
        expect(datetime && new Date(datetime).toISOString(), 'the instant whole, as the server sent it').toBe(moment.instant);
        await expect(time).toHaveAttribute('title', moment.whole);
      }
      await expect(timeline).not.toContainText('2026-10-2');

      await timeline.evaluate((element) => element.scrollIntoView({ block: 'center' }));
      await untilStill(page);
      expect(await cutTexts(timeline), `no text cut at ${size.label}`).toEqual([]);
      const overflow = await horizontalOverflow(page);
      expect(overflow, `no sideways scroll at ${size.label}`).toBeLessThanOrEqual(0);
      await page.screenshot({ path: shot(`${KEY}-${size.label}`) });
    } finally {
      await context.close();
    }
  });
}

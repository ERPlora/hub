// The Home's figures are the library's figure card (StatCard): its first figures with a colour head the board in a row
// in colour, one per colour, in the colour of their measure (sales 1, tickets 2, inventory 6); the rest stay soft. Seen
// at the three sizes, in light and in dark.
import { type Browser, expect, type Locator, type Page, test } from '@playwright/test';

import { A, horizontalOverflow, login, shot, shown, turnOffTurnedOn, turnOnMissing } from './helpers';
import { boardWidget, HOME_BOARD, panelValue } from './home-helpers';

const NEEDED = ['sale', 'inventory'] as const;
const BOARD = ['sale.today', 'sale.tickets_today', 'inventory.low_stock_count', 'inventory.value', 'sale.last_7_days'];
const SIZES = [
  { label: '375', width: 375, height: 667 },
  { label: '820', width: 820, height: 1180 },
  { label: '1440', width: 1440, height: 900 },
] as const;

const turnedOn: string[] = [];

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/');
  await turnOnMissing(context, A, NEEDED, turnedOn).finally(() => context.close());
});

test.afterAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/');
  await turnOffTurnedOn(context, A, turnedOn).finally(() => context.close());
});

async function homeWithFigures(browser: Browser, size: (typeof SIZES)[number], scheme: 'light' | 'dark') {
  const context = await browser.newContext({ baseURL: A, viewport: size, locale: 'es-ES', colorScheme: scheme });
  await context.addInitScript(([key, keys]) => localStorage.setItem(key, keys), [HOME_BOARD, JSON.stringify(BOARD)]);
  const page = await context.newPage();
  await login(page, A, '/');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}/`);
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  return { context, page };
}

const lively = (page: Page): Locator => shown(page).locator('[data-testid="widgets-lively"]');

async function readFigure(page: Page, key: string, tone: string, variant: 'live' | 'soft'): Promise<Locator> {
  const card = boardWidget(page, key);
  await expect(card).toHaveAttribute('aria-busy', 'false');
  await expect(card).toHaveAttribute('data-state', 'ready');
  await expect(panelValue(card)).toHaveText(/\d/);
  await expect(card).toHaveAttribute('data-tone', tone);
  await expect(card).toHaveClass(new RegExp(`ep-stat-card--${variant}`));
  return card;
}

for (const size of SIZES) {
  for (const scheme of ['light', 'dark'] as const) {
    test(`Inicio: the figures in figure cards, the main ones in a row in colour, at ${size.label} in ${scheme}`, async ({ browser }) => {
      const { context, page } = await homeWithFigures(browser, size, scheme);
      try {
        const row = lively(page);
        await expect(row).toHaveClass(/ep-stat-grid/);
        await expect(row.locator('[data-testid="widget"]')).toHaveCount(3);
        const keys = await row.locator('[data-testid="widget"]').evaluateAll((cards) => cards.map((card) => card.getAttribute('data-key')));
        expect(keys).toEqual(['sale.today', 'sale.tickets_today', 'inventory.low_stock_count']);
        const sales = await readFigure(page, 'sale.today', '1', 'live');
        const tickets = await readFigure(page, 'sale.tickets_today', '2', 'live');
        await readFigure(page, 'inventory.low_stock_count', '6', 'live');
        // Inventory's colour already shows in the row: its stock value stays soft, after the row.
        await readFigure(page, 'inventory.value', '6', 'soft');
        await expect(row.locator('[data-key="inventory.value"]')).toHaveCount(0);

        // Two by two on a phone and on a tablet, side by side on a desk: sales and tickets share their line.
        const [a, b] = [await sales.boundingBox(), await tickets.boundingBox()];
        expect(Math.abs((a?.y ?? 0) - (b?.y ?? 1))).toBeLessThan(2);
        expect(await horizontalOverflow(page)).toBe(0);

        await row.evaluate((element) => element.scrollIntoView({ block: 'start' }));
        await page.screenshot({ path: shot(`base-home-figures-${size.label}-${scheme}`) });
      } finally {
        await context.close();
      }
    });
  }
}

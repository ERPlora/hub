// The Home's figures are the library's figure card (StatCard): its first figures with a colour head the board in a row
// in colour, one per colour, in the colour of their measure (sales 1, tickets 2, inventory 6); the rest stay soft. Seen
// at the three sizes, in light and in dark.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { capture, horizontalOverflow, shown, THREE_SIZES } from './helpers';
import { boardWidget, panelValue, spanishOwnerWithPanels } from './home-helpers';

/** Sales and Inventory, on in the seeded business: three figures with a colour (two of inventory), and a chart. */
const BOARD = ['sale.today', 'sale.tickets_today', 'inventory.low_stock_count', 'inventory.value', 'sale.last_7_days'];

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

for (const size of THREE_SIZES) {
  for (const scheme of ['light', 'dark'] as const) {
    test(`Inicio: the figures in figure cards, the main ones in a row in colour, at ${size.label} in ${scheme}`, async ({ browser }) => {
      const { context, page } = await spanishOwnerWithPanels(browser, size, BOARD);
      try {
        await page.emulateMedia({ colorScheme: scheme });
        const row = lively(page);
        await expect(row).toHaveClass(/ep-stat-grid/);
        await expect(row.locator('[data-testid="widget"]')).toHaveCount(3);
        const keys = await row.locator('[data-testid="widget"]').evaluateAll((cards) => cards.map((card) => card.getAttribute('data-key')));
        expect(keys).toEqual(['sale.today', 'sale.tickets_today', 'inventory.low_stock_count']);
        const sales = await readFigure(page, 'sale.today', '1', 'live');
        const tickets = await readFigure(page, 'sale.tickets_today', '2', 'live');
        await readFigure(page, 'inventory.low_stock_count', '6', 'live');
        // Inventory's colour already shows in the row: its stock value stays soft, after the row, and two by two with
        // the other figures on a phone too: never the whole width.
        const soft = await readFigure(page, 'inventory.value', '6', 'soft');
        expect((await soft.boundingBox())?.width ?? size.width).toBeLessThan(size.width * 0.6);
        await expect(row.locator('[data-key="inventory.value"]')).toHaveCount(0);

        // Two by two on a phone and on a tablet, side by side on a desk: sales and tickets share their line.
        const [a, b] = [await sales.boundingBox(), await tickets.boundingBox()];
        expect(Math.abs((a?.y ?? 0) - (b?.y ?? 1))).toBeLessThan(2);
        expect(await horizontalOverflow(page)).toBe(0);

        await row.evaluate((element) => element.scrollIntoView({ block: 'start' }));
        await capture(page, `base-home-figures-${size.label}-${scheme}`);
      } finally {
        await context.close();
      }
    });
  }
}

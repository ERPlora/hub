// flow: SALE-F15, SALE-F20 — hub#2016: what is comped is usually what was already served (the dessert on the house,
// the dish that came out wrong), so a line already sent to the kitchen keeps its gift beside ⊗ «Void this item». In
// Spanish, at 390×844, 834×1194 and 1440×900: a check with a dish, its round sent; the gift on the sent line leaves it
// on the check at 0,00 € with «Invitación» and its «Comanda 1», and nothing waits to be sent to the kitchen; the gift
// again charges it again. What a run creates, the product `E2E-COMPSENT-<run>`, its checks and their kitchen tickets,
// is deleted after it.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { A, capture, shown } from './helpers';
import type { Product } from './inventory-helpers';
import { checkWithDish, cleanTill, dishForTheTill, stamp, VIEWPORTS } from './sale-helpers';

const KEY = 'FIX-HUB-2016-COMP-SENT';
const RUN = stamp();

let dish: Product;

test.beforeAll(async ({ browser }) => {
  dish = await dishForTheTill(browser, 'COMPSENT', RUN);
});

test.afterAll(cleanTill);

/** The dish's line on the check, found by its name. */
function dishLine(page: Page): Locator {
  return shown(page).locator('[data-testid^=pos-line-]').filter({ hasText: dish.name }).first();
}

async function sendRound(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=pos-cart-tab-round]').click();
  await shown(page).locator('[data-testid=pos-kitchen-send]').click();
  await expect(shown(page).locator('[data-testid=pos-cart-round-empty]'), 'the round left «Comanda actual»').toBeVisible();
  await shown(page).locator('[data-testid=pos-cart-tab-check]').click();
}

for (const size of VIEWPORTS) {
  test(`SALE-F15, SALE-F20: a dish already sent to the kitchen is comped and charged again at ${size.label}`, async ({ browser }) => {
    const context = await browser.newContext({ baseURL: A, locale: 'es-ES', viewport: { width: size.width, height: size.height } });
    try {
      const page = await context.newPage();
      await checkWithDish(page, context, 'es', dish);
      await sendRound(page);

      const line = dishLine(page);
      const lineId = (await line.getAttribute('data-testid'))?.replace('pos-line-', '');
      const gift = line.locator(`[data-testid=pos-line-${lineId}-gift]`);
      // The gift is outlined until the line is comped, then filled (the current product's icons).
      const giftIcon = gift.locator('ion-icon');
      await expect(line.locator('.pos-line__round')).toHaveText('Comanda 1');
      await expect(line.locator(`[data-testid=pos-line-${lineId}-void]`), 'the sent dish can still be voided').toBeVisible();
      await expect(giftIcon).toHaveAttribute('name', 'gift-outline');

      await gift.click();
      await expect(giftIcon).toHaveAttribute('name', 'gift');
      await expect(line.locator('.pos-line__gift')).toHaveText('Invitación');
      await expect(line.locator('.pos-line__amount')).toContainText('0,00');
      await expect(shown(page).locator('[data-testid=pos-total]'), 'the check no longer charges it').toContainText('0,00');
      await expect(line.locator('.pos-line__round'), 'still the round the kitchen has').toHaveText('Comanda 1');
      await expect(shown(page).locator('[data-testid=pos-kitchen-send]'), 'nothing new for the kitchen').toHaveCount(0);
      await capture(page, `${KEY}-es-${size.label}`);

      await gift.click();
      await expect(giftIcon).toHaveAttribute('name', 'gift-outline');
      await expect(line.locator('.pos-line__gift')).toHaveCount(0);
      await expect(line.locator('.pos-line__amount')).toContainText('7,00');
      await expect(shown(page).locator('[data-testid=pos-total]'), 'the check charges it again').toContainText('7,00');
    } finally {
      await context.close();
    }
  });
}

// flow: FLOW-F04
// The gallery of Automations writes its amounts and times as the language of the screen does: in English «€100.00» and
// «6:00 PM», and an opened card quotes with English quotation marks; in Spanish «100,00 €», «18:00» and «…». Before, the
// English cards read «100,00 €», «18:00» and «Big sale» between Spanish quotes. Seen in the three sizes the fleet checks.
import { type Browser, expect, type Page, test } from '@playwright/test';

import { A, capture, login, saveSessionForTheSweep, shown, signedInSpanish, THREE_SIZES } from './helpers';

const KEY = 'fix-flow-gallery-language-format';

async function signedInEnglish(browser: Browser, viewport: { width: number; height: number }) {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, '/flow/automations');
  await expect(page.locator('html')).toHaveAttribute('lang', /^en/);
  return { context, page };
}

const card = (page: Page, id: string) => shown(page).locator(`[data-testid=flow-card-open-${id}]`);
const panel = (page: Page, id: string) => shown(page).locator(`[data-testid=flow-card-panel-${id}]`);

for (const viewport of THREE_SIZES) {
  test(`FLOW-F04 the gallery in English says €100.00 and 6:00 PM, with English quotes, at ${viewport.label}`, async ({ browser }) => {
    const { context, page } = await signedInEnglish(browser, viewport);
    try {
      await expect(card(page, 'bigSaleNote')).toContainText('When a sale of €100.00 or more has a customer');
      await expect(card(page, 'bigSaleTask')).toContainText('When a sale over €100.00 is charged');
      await expect(card(page, 'weekReview')).toContainText('Every Friday at 6:00 PM');
      await card(page, 'bigSaleNote').click();
      await expect(panel(page, 'bigSaleNote')).toContainText('it writes “Big sale” on the customer');
      await expect(panel(page, 'bigSaleNote')).not.toContainText('«');
      await expect(panel(page, 'bigSaleNote')).not.toContainText('100,00');
      await panel(page, 'bigSaleNote').scrollIntoViewIfNeeded();
      await capture(page, `${KEY}-en-${viewport.label}`);
      await saveSessionForTheSweep(context);
    } finally {
      await context.close();
    }
  });

  test(`FLOW-F04 the gallery in Spanish still says 100,00 € and 18:00, with Spanish quotes, at ${viewport.label}`, async ({ browser }) => {
    const { context, page } = await signedInSpanish(browser, viewport, '/flow/automations');
    try {
      await expect(card(page, 'bigSaleNote')).toContainText('Cuando una venta de 100,00 € o más tiene cliente');
      await expect(card(page, 'weekReview')).toContainText('Todos los viernes a las 18:00');
      await card(page, 'bigSaleNote').click();
      await expect(panel(page, 'bigSaleNote')).toContainText('escribe «Venta grande» en la ficha del cliente');
      await panel(page, 'bigSaleNote').scrollIntoViewIfNeeded();
      await capture(page, `${KEY}-es-${viewport.label}`);
    } finally {
      await context.close();
    }
  });
}

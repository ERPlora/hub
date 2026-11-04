// flow: SALE-F20, SALE-F01
// hub#748: on a low phone «Send order» says «Order N sent to the kitchen.», and what a waiter often does next is
// «Charge». At the bottom that notice lay over the button for its 2.6 s (375x667: over its middle; 320x568: over all of
// it), so the tap fell on the notice and the sheet did not open. Here, with the notice on screen, the middle of «Charge»
// answers with «Charge», the notice covers none of it and is whole on screen and painted on top, and a real tap on that
// spot opens the charge sheet with the notice still up. The same with the longer words of a round whose sheet did not
// print. The notice is told to stay until it has been read: where it sits is the point, not how long it lasts, and read
// without that a check passes once it has gone by itself. The worst case of a real business: the red strip of a hub that
// cannot issue invoices yet takes 138 px over the till (hub `a`'s issuer is parked for the run and put back after it).
// What a run creates, the product `E2E-KSEND-<run>`, its checks and their kitchen tickets, is deleted after it.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { capture, shown, untilStill } from './helpers';
import { cleanInventory, type Product } from './inventory-helpers';
import { parkIssuer, unparkIssuer } from './invoice-helpers';
import { type Box, checkWithDish, cleanSales, dishForTheTill, eachNoticeSize, expectNoticeWhole, holdNotices, noticeBox, overlap, restoreDrawer, stamp } from './sale-helpers';

const KEY = 'FIX-HUB-748-NOTICE';
/** Hub `a`'s issuer, parked while the run needs the strip of a hub that cannot issue invoices yet. */
const PARKED = 'e2e_sale_kitchen_send_notice_issuer';
const RUN = stamp();
/** How long `toast()` shows a plain notice and a warning that the sheet did not print. */
const SENT_MS = 2600;
const NOT_PRINTED_MS = 4500;
const LANGUAGES = [
  { name: 'English', lang: 'en', locale: 'en-US', sent: 'Order 1 sent to the kitchen.', notPrinted: 'Order 1 sent to the kitchen, but it did not print.' },
  { name: 'Spanish', lang: 'es', locale: 'es-ES', sent: 'Comanda 1 enviada a cocina.', notPrinted: 'Comanda 1 enviada a cocina, pero no se imprimió.' },
] as const;

let dish: Product;

test.beforeAll(async ({ browser }) => {
  cleanSales();
  cleanInventory();
  parkIssuer(PARKED);
  dish = await dishForTheTill(browser, 'KSEND', RUN);
});

test.afterAll(() => {
  try {
    cleanSales();
    cleanInventory();
  } finally {
    try {
      restoreDrawer();
    } finally {
      unparkIssuer(PARKED);
    }
  }
});

/** A check of its own with a dish, its till in the language under test, the round sent with «Send order». */
async function sendRound(page: Page, context: BrowserContext, lang: string): Promise<void> {
  await checkWithDish(page, context, lang, dish);
  await expect(shown(page).locator('[data-testid=blocking-strip]'), 'the strip of a hub that cannot issue invoices yet').toBeVisible({ timeout: 30_000 });
  await shown(page).locator('[data-testid=pos-cart-tab-round]').click();
  await shown(page).locator('[data-testid=pos-kitchen-send]').click();
  await expect(shown(page).locator('[data-testid=pos-cart-round-empty]'), 'the round left «Current order»').toBeVisible();
}

/** The notice's box and whether it answers on its middle, and the same for «Charge», with everything on screen still. */
async function read(page: Page, notice: Locator): Promise<{ toast: Box; toastOnTop: boolean; charge: Box; answer: string }> {
  const toast = await noticeBox(notice);
  const toastOnTop = await notice.evaluate((el, box) => document.elementFromPoint((box.left + box.right) / 2, (box.top + box.bottom) / 2) === el, toast);
  const { charge, answer } = await shown(page)
    .locator('[data-testid=pos-charge]')
    .evaluate((button) => {
      const box = button.getBoundingClientRect();
      const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
      return {
        charge: { top: box.top, bottom: box.bottom, left: box.left, right: box.right },
        answer: hit && button.contains(hit) ? '«Charge»' : (hit?.tagName.toLowerCase() ?? 'nothing'),
      };
    });
  return { toast, toastOnTop, charge, answer };
}

/** «Charge» free with the notice on screen, and a finger on its middle opens the sheet with the notice still there. */
async function chargeAnswersATap(page: Page, notice: Locator, size: { label: string; height: number }): Promise<void> {
  await expect(notice, 'the notice is on screen').toBeVisible();
  await untilStill(page);
  const { toast, toastOnTop, charge, answer } = await read(page, notice);
  expect.soft(answer, `the middle of «Charge» at ${size.label}`).toBe('«Charge»');
  expect.soft(overlap(toast, charge), `the notice ${JSON.stringify(toast)} clear of «Charge» ${JSON.stringify(charge)}`).toBe(false);
  expect.soft(toastOnTop, 'the notice painted over what it shares the screen with').toBe(true);
  expectNoticeWhole(toast, size.height);

  // A real finger, not a forced click: on the notice it would close nothing and open nothing.
  await page.mouse.click((charge.left + charge.right) / 2, (charge.top + charge.bottom) / 2);
  await expect(page.locator('[data-testid=sale-checkout-modal] [data-testid=sale-checkout-keypad]'), `one tap on «Charge» opens the sheet at ${size.label}`).toBeVisible();
  await expect.soft(notice, 'the notice still on screen when the sheet opens').toBeVisible();
}

for (const { name, lang, locale, sent, notPrinted } of LANGUAGES) {
  test.describe(`SALE-F20, SALE-F01: in ${name}, the notice of «Send order» leaves «Charge» free`, () => {
    eachNoticeSize(locale, async (page, context, size) => {
      await holdNotices(page, SENT_MS);
      await sendRound(page, context, lang);
      const notice = page.locator('ion-toast').filter({ hasText: sent });
      await expect(notice).toBeVisible();
      await capture(page, `${KEY}-${lang}-${size.label}`);
      await chargeAnswersATap(page, notice, size);
    });
  });

  test.describe(`SALE-F20, SALE-F01: in ${name}, the notice of a round whose sheet did not print leaves «Charge» free`, () => {
    eachNoticeSize(locale, async (page, context, size) => {
      await holdNotices(page, NOT_PRINTED_MS);
      // The real answer of the send, plus the one field that says its sheet did not print (KITCHEN-F08).
      await page.route('**/kitchen/tickets/send', async (route) => {
        const response = await route.fetch();
        await route.fulfill({ response, json: { ...(await response.json()), print_error: 'no printer for usage kitchen' } });
      });
      await sendRound(page, context, lang);
      const notice = page.locator('ion-toast').filter({ hasText: notPrinted });
      await expect(notice).toBeVisible();
      await capture(page, `${KEY}-not-printed-${lang}-${size.label}`);
      await chargeAnswersATap(page, notice, size);
    });
  });
}

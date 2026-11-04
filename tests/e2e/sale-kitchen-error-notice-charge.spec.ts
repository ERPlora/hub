// flow: SALE-F20, SALE-F01
// hub#755: with Kitchen on, a round that cannot be sent keeps the cart open and says why for 4.5 s. Left at the bottom
// on a low phone the notice lay over «Charge», and a tap there to try again fell on the notice: no new send. Here, with
// the notice on screen, the middle of «Charge» and of «Send order» answer with the button itself, the notice covers
// neither, and a real tap on «Charge» sends the round again. The kitchen's answer is a 500 of this spec's own route,
// and the notice is told to stay until it has been read: where it sits is the point, not how long it lasts. The worst
// case of a real business: the red strip of a hub that cannot issue invoices yet takes 138 px over the till (hub `a`'s
// issuer is parked for the run and put back after it). What a run creates, its product `E2E-KERROR-<run>` and its
// checks, is deleted after it.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { capture, settled, shown, untilStill } from './helpers';
import { cleanInventory, type Product } from './inventory-helpers';
import { parkIssuer, unparkIssuer } from './invoice-helpers';
import { type Box, checkWithDish, cleanSales, dishForTheTill, eachNoticeSize, expectNoticeWhole, holdNotices, noticeBox, overlap, restoreDrawer, stamp, tillIsPhone } from './sale-helpers';

const KEY = 'FIX-HUB-755-ERROR-NOTICE';
/** Hub `a`'s issuer, parked while the run needs the strip of a hub that cannot issue invoices yet. */
const PARKED = 'e2e_sale_kitchen_error_issuer';
const RUN = stamp();
/** How long this notice lasts. */
const NOTICE_MS = 4500;
const LANGUAGES = [
  { name: 'English', lang: 'en', locale: 'en-US', notSent: 'The order could not be sent to the kitchen. Try again.' },
  { name: 'Spanish', lang: 'es', locale: 'es-ES', notSent: 'No se ha podido enviar la comanda a cocina. Inténtalo de nuevo.' },
] as const;

let dish: Product;

test.beforeAll(async ({ browser }) => {
  cleanSales();
  cleanInventory();
  parkIssuer(PARKED);
  dish = await dishForTheTill(browser, 'KERROR', RUN);
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

/** A check of its own with a dish not sent, its till in the language under test and the kitchen refusing: returns how
 *  many sends the kitchen has been asked for so far. */
async function checkWithKitchenDown(page: Page, context: BrowserContext, lang: string): Promise<() => number> {
  await holdNotices(page, NOTICE_MS);
  let sends = 0;
  await page.route('**/kitchen/tickets/send', async (route) => {
    sends += 1;
    await route.fulfill({ status: 500, json: { error: { code: 'internal_error', message: 'The kitchen did not answer.' } } });
  });
  await checkWithDish(page, context, lang, dish);
  await expect(shown(page).locator('[data-testid=blocking-strip]'), 'the strip of a hub that cannot issue invoices yet').toBeVisible({ timeout: 30_000 });
  await settled(page);
  return () => sends;
}

/** What the middle of a button of the till answers to, and its box. */
async function reach(button: Locator): Promise<{ answer: string; box: Box }> {
  return button.evaluate((el) => {
    const r = el.getBoundingClientRect();
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return {
      answer: hit && el.contains(hit) ? 'the button' : (hit?.tagName.toLowerCase() ?? 'nothing'),
      box: { top: r.top, bottom: r.bottom, left: r.left, right: r.right },
    };
  });
}

/** With the notice on screen: both ways of sending again answer with themselves, and it sits whole, clear of both. */
async function bothButtonsFree(notice: Locator, charge: Locator, send: Locator, height: number, where: string): Promise<void> {
  await expect(notice, `one notice at a time ${where}`).toHaveCount(1);
  await expect(notice, `the notice is on screen ${where}`).toBeVisible();
  await untilStill(notice.page());
  const box = await noticeBox(notice);
  for (const [name, button] of [
    ['Charge', charge],
    ['Send order', send],
  ] as const) {
    const { answer, box: at } = await reach(button);
    expect.soft(answer, `the middle of «${name}» ${where}`).toBe('the button');
    expect.soft(overlap(box, at), `the notice ${JSON.stringify(box)} clear of «${name}» ${JSON.stringify(at)} ${where}`).toBe(false);
  }
  expectNoticeWhole(box, height, where);
}

for (const { name, lang, locale, notSent } of LANGUAGES) {
  test.describe(`SALE-F20, SALE-F01: in ${name}, the notice of a round not sent leaves «Charge» free`, () => {
    eachNoticeSize(locale, async (page, context, size) => {
      const sends = await checkWithKitchenDown(page, context, lang);
      const till = shown(page);
      const charge = till.locator('[data-testid=pos-charge]');
      const send = till.locator('[data-testid=pos-kitchen-send]');
      const notice = page.locator('ion-toast').filter({ hasText: notSent });

      await till.locator('[data-testid=pos-cart-tab-round]').click();
      await expect(send).toBeVisible();
      await send.click();
      await expect.poll(sends, 'the send that fails').toBe(1);
      await bothButtonsFree(notice, charge, send, size.height, `at ${size.label}, after «Send order»`);
      await capture(page, `${KEY}-${lang}-${size.label}`);

      // Trying again with the notice on screen: the finger lands on «Charge», which sends the round first.
      const first = await notice.getAttribute('id');
      const at = (await charge.boundingBox())!;
      await page.mouse.click(at.x + at.width / 2, at.y + at.height / 2);
      await expect.poll(sends, 'a tap on «Charge» sends the round again').toBe(2);
      await expect.soft(page.locator('[data-testid=sale-checkout-modal]'), 'nothing is charged with the round not sent').toBeHidden();
      // The second notice closes the first before it opens: what is measured next is the new one.
      await expect(page.locator(`ion-toast[id="${first}"]`), 'the new notice takes the place of the first').toHaveCount(0);
      await bothButtonsFree(notice, charge, send, size.height, `at ${size.label}, after «Charge»`);
      if (await tillIsPhone(page)) await expect.soft(till.locator('[data-testid=pos-cart-drawer]'), 'the check stays open').toBeVisible();
    });
  });
}

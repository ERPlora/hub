// flow: SALE-F01, SALE-F20
// hub#732: «Charge» with dishes not sent yet sends the round and opens the charge sheet at once, so the notice «Order N
// sent to the kitchen.» shares the screen with the keypad. Left at the bottom on a low phone it lay over the last row
// of keys (`,` `0` `C`) for its 2.6 s, and a tap there fell on the notice: the amount did not change. Here, with the
// notice on screen, the middle of every key answers with that key, the notice covers none of the keypad, and the taps
// type the amount. The notice is told to stay until it has been read: where it sits is the point, not how long it
// lasts, and a sheet opening on a cold Vite takes longer than its 2.6 s. What a run creates, the product
// `E2E-KNOTICE-<run>`, its checks and their kitchen tickets, is deleted after it.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, capture, login, psql, shown, untilStill } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { cleanSales, drawerOff, openTillCart, restoreDrawer, stamp } from './sale-helpers';

const KEY = 'FIX-HUB-732-NOTICE';
const RUN = stamp();
const NOTICE_MS = 2600;
const SIZES = [
  { label: '1440x900', width: 1440, height: 900 },
  { label: '820x1180', width: 820, height: 1180 },
  { label: '375x667', width: 375, height: 667 },
  { label: '320x568', width: 320, height: 568 },
] as const;
const LANGUAGES = [
  { name: 'English', lang: 'en', locale: 'en-US', sent: 'Order 1 sent to the kitchen.', separator: '.' },
  { name: 'Spanish', lang: 'es', locale: 'es-ES', sent: 'Comanda 1 enviada a cocina.', separator: ',' },
] as const;

interface Box {
  top: number;
  bottom: number;
  left: number;
  right: number;
}

let dish: Product;

/** The kitchen tickets of this file's checks (their dishes name the lines of its product), before the sales: a ticket
 *  names the check's lines. */
function cleanRun(): void {
  const lines = "select id from sale_orderline where sku like 'E2E-KNOTICE-%'";
  const tickets = `select distinct ticket_id from kitchen_ticketitem where sale_line_id in (${lines}) or name like 'E2E KNOTICE %'`;
  psql(
    [
      `create temp table e2e_knotice_tickets as ${tickets}`,
      "delete from printing_printjob where source_app = 'kitchen' and reference in (select number from kitchen_ticket where id in (select ticket_id from e2e_knotice_tickets))",
      'delete from kitchen_logentry where ticket_id in (select ticket_id from e2e_knotice_tickets)',
      'delete from kitchen_ticketitem where ticket_id in (select ticket_id from e2e_knotice_tickets)',
      'delete from kitchen_ticket where id in (select ticket_id from e2e_knotice_tickets)',
    ].join('; '),
  );
}

function cleanUp(): void {
  cleanRun();
  cleanSales();
  cleanInventory();
}

test.beforeAll(async ({ browser }) => {
  cleanUp();
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  // Cash without a cash session: the drawer's lock is sale-cash-gate.spec.ts's.
  await drawerOff(context);
  dish = await createProduct(context, { name: `E2E KNOTICE Dish ${RUN}`, sku: `E2E-KNOTICE-${RUN}`, price: 700, tax_category_key: 'restaurant.food' });
  await context.close();
});

test.afterAll(() => {
  try {
    cleanUp();
  } finally {
    restoreDrawer();
  }
});

/** A check of its own with a dish not sent, its till in the language under test, and the sheet opened by «Charge». */
async function chargeUnsentDish(page: Page, context: BrowserContext, lang: string): Promise<Locator> {
  // A notice's timer (2600 is the default of `toast()`) waits for the spec to read it; no other timer changes.
  await page.addInitScript((noticeMs) => {
    const original = window.setTimeout.bind(window);
    window.setTimeout = ((run: TimerHandler, ms?: number, ...rest: unknown[]) =>
      original(run, ms === noticeMs ? 600_000 : ms, ...rest)) as typeof window.setTimeout;
  }, NOTICE_MS);
  await login(page, A, '/sale/pos');
  await context.addCookies([{ name: 'django_language', value: lang, domain: new URL(A).hostname, path: '/' }]);
  await page.reload();
  await shown(page).locator(`[data-testid=pos-product-${dish.id}]`).click();
  await expect(shown(page).locator('[data-testid^=pos-line-]').filter({ hasText: dish.name }).first()).toBeAttached();
  await openTillCart(page);
  await shown(page).locator('[data-testid=pos-charge]').click();
  return page.locator('[data-testid=sale-checkout-modal]');
}

/** What the middle of each key answers to, the keys' boxes and the notice's own (its host fills the screen), all in one read. */
async function read(sheet: Locator, notice: Locator): Promise<{ answers: Record<string, string>; keypad: Box; toast: Box }> {
  const toast = await notice.evaluate((el) => {
    const box = el.shadowRoot!.querySelector('.toast-wrapper')!.getBoundingClientRect();
    return { top: box.top, bottom: box.bottom, left: box.left, right: box.right };
  });
  const { answers, keypad } = await sheet.locator('[data-testid=sale-checkout-keypad]').evaluate((pad) => {
    const answered: Record<string, string> = {};
    for (const key of pad.querySelectorAll<HTMLElement>('button')) {
      const box = key.getBoundingClientRect();
      const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
      answered[key.dataset.testid ?? ''] = hit && key.contains(hit) ? 'the key' : (hit?.tagName.toLowerCase() ?? 'nothing');
    }
    const box = pad.getBoundingClientRect();
    return { answers: answered, keypad: { top: box.top, bottom: box.bottom, left: box.left, right: box.right } };
  });
  return { answers, keypad, toast };
}

async function tap(page: Page, sheet: Locator, key: string): Promise<void> {
  const box = (await sheet.locator(`[data-testid=sale-checkout-keypad-${key}]`).boundingBox())!;
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
}

for (const { name, lang, locale, sent, separator } of LANGUAGES) {
  test.describe(`SALE-F01, SALE-F20: in ${name}, the kitchen's notice leaves the keypad of the charge sheet free`, () => {
    for (const size of SIZES) {
      test(size.label, async ({ browser }) => {
        const context = await browser.newContext({ baseURL: A, locale, viewport: { width: size.width, height: size.height } });
        try {
          const page = await context.newPage();
          const sheet = await chargeUnsentDish(page, context, lang);
          const notice = page.locator('ion-toast').filter({ hasText: sent });
          await expect(sheet.locator('[data-testid=sale-checkout-keypad]')).toBeVisible();
          await expect(notice, 'the notice is on screen with the sheet').toBeVisible();
          await untilStill(page);
          await capture(page, `${KEY}-${lang}-${size.label}`);

          const { answers, keypad, toast } = await read(sheet, notice);
          for (const [key, answer] of Object.entries(answers)) expect.soft(answer, `the middle of «${key}» at ${size.label}`).toBe('the key');
          const overKeys = toast.top < keypad.bottom && toast.bottom > keypad.top && toast.left < keypad.right && toast.right > keypad.left;
          expect.soft(overKeys, `the notice ${JSON.stringify(toast)} clear of the keypad ${JSON.stringify(keypad)}`).toBe(false);
          expect.soft(toast.top, 'the notice whole on screen, at the top').toBeGreaterThanOrEqual(0);
          expect.soft(toast.bottom, 'the notice whole on screen, at the bottom').toBeLessThanOrEqual(size.height);
          expect.soft(toast.right - toast.left, 'the notice not squeezed').toBeGreaterThan(200);

          // The amount, typed with the notice on screen: the last row's keys take the finger too.
          for (const key of ['1', '0', 'dot', '5']) await tap(page, sheet, key);
          await expect.soft(sheet.locator('[data-testid=sale-checkout-tendered]'), 'tendered').toContainText(`10${separator}50`);
          await expect.soft(notice, 'the notice still on screen while typing').toBeVisible();
          await tap(page, sheet, 'clear');
          await expect.soft(sheet.locator('[data-testid=sale-checkout-tendered]'), 'cleared').not.toContainText(`10${separator}50`);
        } finally {
          await context.close();
        }
      });
    }
  });
}

// flow: kitchen-e2e-wait — FIX of the Kitchen specs' wait (FIX-HUB-KITCHEN-E2E-WAIT-BLIND-TO-SHADOW-ROOTS)
// Before a capture or a measurement, the Kitchen specs (kitchen-*.spec.ts) wait for the screen to stop moving with the
// harness's one wait, `untilStill` (helpers.ts). Their own wait asked the document alone for its animations, which
// leaves shadow roots out, and Ionic animates its overlays (`ion-modal`, `ion-toast`) in theirs: a capture could come
// out with a sheet still sliding in and pass for good. Here the till's «Order tickets» sheet (KITCHEN-F19: «Tickets · 1»
// beside what was sent opens it) enters at a fifth of its speed (Chrome's own control), and once the Kitchen specs'
// wait returns nothing may move, asked with the harness's own detector (`exposeMovingInPage`, helpers.ts), at 390, 834
// and 1440. What a run creates — the product `E2E-KST-<run>`, its check and its kitchen ticket — is deleted after it.
import { type CDPSession, expect, type Locator, type Page, test } from '@playwright/test';

import { A, capture, exposeMovingInPage, hostPage, psql, repeatedTop, shown, untilStill } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { cleanSales, drawerOff, openTillCart, restoreDrawer, stamp } from './sale-helpers';

const KEY = 'FIX-HUB-KITCHEN-E2E-WAIT-BLIND-TO-SHADOW-ROOTS';
const RUN = stamp();

const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
] as const;

let burger: Product;

test.use({ locale: 'en-US' });

/** The kitchen tickets of this file's checks (their dishes name the lines of its product), before the sales: a ticket
 *  names the check's lines. */
function cleanRun(): void {
  const lines = "select id from sale_orderline where sku like 'E2E-KST-%'";
  const tickets = `select distinct ticket_id from kitchen_ticketitem where sale_line_id in (${lines}) or name like 'E2E KST %'`;
  psql(
    [
      `create temp table e2e_kst_tickets as ${tickets}`,
      "delete from printing_printjob where source_app = 'kitchen' and reference in (select number from kitchen_ticket where id in (select ticket_id from e2e_kst_tickets))",
      'delete from kitchen_logentry where ticket_id in (select ticket_id from e2e_kst_tickets)',
      'delete from kitchen_ticketitem where ticket_id in (select ticket_id from e2e_kst_tickets)',
      'delete from kitchen_ticket where id in (select ticket_id from e2e_kst_tickets)',
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
  const { context } = await hostPage(browser, A, { next: '/sale/pos' });
  // The till opens without a cash session: the drawer's lock is sale-cash-gate.spec.ts's.
  await drawerOff(context);
  burger = await createProduct(context, { name: `E2E KST Burger ${RUN}`, sku: `E2E-KST-${RUN}`, price: 1200, tax_category_key: 'restaurant.food' });
  await context.close();
});

test.afterAll(() => {
  cleanUp();
  restoreDrawer();
});

const sheet = (page: Page): Locator => page.locator('ion-modal[data-testid=pos-kitchen-tickets]');

/** What moves on the page now, by the detector of helpers.ts put in the page (`exposeMovingInPage`). */
async function moving(page: Page): Promise<string[]> {
  await exposeMovingInPage(page);
  return page.evaluate(() => (window as unknown as { __movingInPage: () => string[] }).__movingInPage());
}

/** Every animation of the page at `rate` times its speed. */
async function playbackRate(devtools: CDPSession, rate: number): Promise<void> {
  await devtools.send('Animation.setPlaybackRate', { playbackRate: rate });
}

test('kitchen-e2e-wait: after the Kitchen specs’ wait the till’s «Order tickets» sheet has stopped entering, at 390, 834 and 1440', async ({
  browser,
}) => {
  const { context, page } = await hostPage(browser, A, { next: '/sale/pos', viewport: SIZES[2] });
  const devtools = await context.newCDPSession(page);
  await devtools.send('Animation.enable');
  try {
    const view = shown(page);
    // KITCHEN-F18: the burger, «Current order» → «Send order (1)»; the notice goes by itself before the sheet opens.
    await view.locator(`[data-testid=pos-product-${burger.id}]`).click();
    await view.locator('[data-testid=pos-cart-tab-round]').click();
    await view.locator('[data-testid=pos-kitchen-send]').click();
    const sent = page.locator('ion-toast').filter({ hasText: 'Order 1 sent to the kitchen.' });
    await expect(sent).toBeVisible();
    await expect(sent).toBeHidden({ timeout: 15_000 });
    const chip = view.locator('[data-testid=pos-cart-sent] [data-testid=pos-kitchen-tickets-open]');
    for (const size of SIZES) {
      await page.setViewportSize({ width: size.width, height: size.height });
      await playbackRate(devtools, 1);
      // On a phone the check is the drawer behind the cart button: it and the tabs settle at full speed before the sheet.
      await openTillCart(page);
      await view.locator('[data-testid=pos-cart-tab-check]').click();
      await expect(chip).toHaveText('Tickets · 1');
      await untilStill(page);
      await playbackRate(devtools, 0.2);
      await chip.click();
      // Visible once Ionic presents it, the moment its entrance starts: its title is in the page a frame before.
      await expect(sheet(page)).toBeVisible();
      await expect(sheet(page).locator('[data-testid=pos-kitchen-tickets-title]')).toHaveText('Order tickets');
      await untilStill(page);
      expect.soft(await moving(page), `still moving after the Kitchen specs’ wait at ${size.label}`).toEqual([]);
      expect(await repeatedTop(page, await capture(page, `${KEY}-${size.label}`))).toBe(0);
      await playbackRate(devtools, 1);
      await sheet(page).locator('[data-testid=pos-kitchen-tickets-close]').click();
      await expect(sheet(page)).toBeHidden();
    }
  } finally {
    await playbackRate(devtools, 1);
    await context.close();
  }
});

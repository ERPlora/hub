// flow: BASE-F01 BASE-F10 INVOICE-F21
// The hub's action center (base's WORKBOOK, «La campana» and «El aviso «Todavía no puedes facturar»»), as the owner of
// hub `a` meets it in Spanish at 390, 834 and 1440, in light and dark: the bell's pill with its number and the gravest
// notice's colour; a new notice comes as a card and settles in the bell; the panel opens with «Todavía no puedes
// facturar» on top and the counters in rows, and closes with Esc or a tap outside, giving the focus back to the bell;
// with the assistant open the card comes in to its left and the panel opens over it; with the till's charge sheet open
// no card comes, the bell only counts; and once the business details are saved, «Todavía no puedes facturar» goes.
// The new notice is the demo's «open demo items» counter, raised and dropped through Demo's operations. Hub `a`'s
// issuer is parked for the run and put back as it was after it.
import { type Browser, type BrowserContext, expect, type Page, test } from '@playwright/test';

import { actionBell, actionPanel, arrivalCard, bellSays, bellTotal, closeActionCenter, featuredNotice, noticeButton, noticeIn, openActionCenter } from './action-center';
import { A, api, capture, clearItems, compactBar, horizontalOverflow, login, psql, shown, uniqueName } from './helpers';
import { spanishContext, spanishHome } from './home-helpers';
import { cleanInventory, type Product, VIEWPORTS } from './inventory-helpers';
import { type IssuerOut, issuerNow, parkIssuer, unparkIssuer } from './invoice-helpers';
import { checkWithDish, cleanSales, dishForTheTill } from './sale-helpers';

const KEY = 'BASE-ACTION-CENTER';
/** Hub `a`'s issuer, parked while the run needs a business that cannot issue invoices yet. */
const PARKED = 'e2e_base_action_center_issuer';
const SIZES = VIEWPORTS;
const SCHEMES = ['light', 'dark'] as const;
const BLOCKING = 'Todavía no puedes facturar';
const DEMO_NOTICE = '1 elemento de demo abierto';
/** What the issuer is saved with when the hub had none before the run. */
const ISSUER = { legal_name: 'e2e Bar Centro SL', tax_id: 'B12345674', address: 'Calle Mayor 1', postal_code: '28001', city: 'Madrid', province: 'Madrid', country: 'ES' };

let original: IssuerOut;
let dish: Product;

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  await login(await context.newPage(), A, '/');
  original = await issuerNow(context);
  await context.close();
  parkIssuer(PARKED);
  dish = await dishForTheTill(browser, 'CENTER', Date.now().toString(36).toUpperCase());
});

test.afterAll(() => {
  try {
    cleanSales();
    cleanInventory();
  } finally {
    unparkIssuer(PARKED);
  }
});

/** The owner of `a` on the Home in Spanish, in the colour scheme `scheme`. */
async function spanishOwner(browser: Browser, size: (typeof SIZES)[number], scheme: (typeof SCHEMES)[number]) {
  const context = await spanishContext(browser, { width: size.width, height: size.height });
  const page = await context.newPage();
  await page.emulateMedia({ colorScheme: scheme });
  await spanishHome(page);
  return { context, page };
}

/** No receipt left waiting by an earlier run: «Nothing is printing …» moves with the clock, with no event, so the
 *  bell and a fresh read of the server could disagree while it moves. */
function noPrintsWaiting(): void {
  psql("delete from printing_printjob where status = 'pending'");
}

/** A new notice: the demo's counter of open items, from none to one. */
async function raiseDemoNotice(context: BrowserContext): Promise<void> {
  const created = await api(context, A, 'POST', '/demo/items', { name: uniqueName('Action center') });
  expect(created.status).toBe(201);
}

/** Waits until no card is on screen: one that another notice of the business brought settles in the bell first. */
async function noCardOnScreen(page: Page): Promise<void> {
  await expect(arrivalCard(page)).toHaveCount(0, { timeout: 15_000 });
}

/** The bell says what the server counts now. */
async function bellSaysTheServer(page: Page, context: BrowserContext): Promise<number> {
  const total = await bellTotal(context);
  await bellSays(page, total);
  return total;
}

async function captured(page: Page, state: string, scheme: string, label: string): Promise<void> {
  const overflow = await horizontalOverflow(page);
  expect(overflow, `no sideways scroll: ${state} at ${label}`).toBeLessThanOrEqual(0);
  await capture(page, `${KEY}-${state}-${scheme}-${label}`);
}

/** The bell holds the focus once the panel has gone (Ionic's button keeps its focusable part in its shadow root). */
async function expectFocusOnTheBell(page: Page): Promise<void> {
  await expect.poll(() => page.evaluate(() => document.activeElement?.closest('[data-testid=action-bell]') !== null)).toBe(true);
}

/** A new notice comes as a card under the bar, says its words, and settles in the bell, which then counts it. */
async function expectArrival(page: Page, context: BrowserContext, shotOf: (state: string) => Promise<void>): Promise<void> {
  await noCardOnScreen(page);
  await raiseDemoNotice(context);
  const card = arrivalCard(page);
  await expect(card).toBeVisible();
  await expect(card).toContainText(DEMO_NOTICE);
  await card.hover();
  await shotOf('arrival');
  await page.mouse.move(1, 1);
  await expect(card).toBeHidden({ timeout: 15_000 });
  await bellSaysTheServer(page, context);
}

async function expectThePanel(page: Page, size: (typeof SIZES)[number], shotOf: (state: string) => Promise<void>): Promise<void> {
  const panel = await openActionCenter(page);
  const featured = featuredNotice(panel);
  await expect(featured.locator('h3')).toHaveText(BLOCKING);
  await expect(featured).toContainText('No se podrá emitir ningún tique ni factura hasta que configures esto:');
  await expect(featured).not.toContainText(/\btickets?\b/i);
  await expect(noticeButton(featured, 'Configurar los datos del negocio')).toBeVisible();
  await expect(panel.locator('[data-testid=action-row]').filter({ hasText: DEMO_NOTICE })).toBeVisible();
  await shotOf('panel');
  await closeActionCenter(page);
  await expectFocusOnTheBell(page);
  await openActionCenter(page);
  if (compactBar(page)) {
    await panel.locator('[data-testid=action-panel-close]').click();
  } else {
    // A tap outside: on the screen's left, which the panel (400 px from the right) leaves uncovered.
    await page.mouse.click(10, Math.round(size.height / 2));
  }
  await expect(actionPanel(page)).toBeHidden();
  await expectFocusOnTheBell(page);
}

/** With the assistant open (beside the screen from a tablet), a new card comes in to its left and the panel opens
 *  over it. */
async function expectBesideTheAssistant(page: Page, context: BrowserContext, shotOf: (state: string) => Promise<void>): Promise<void> {
  await clearItems(context, A);
  await bellSaysTheServer(page, context);
  await shown(page).locator('[data-testid=assistant-button]').click();
  const assistant = page.locator('[data-testid=assistant-panel]');
  await expect(assistant).toBeVisible();
  await noCardOnScreen(page);
  await raiseDemoNotice(context);
  const card = arrivalCard(page);
  await expect(card).toBeVisible();
  await card.hover();
  const [cardBox, assistantBox] = await Promise.all([card.boundingBox(), assistant.boundingBox()]);
  expect(cardBox!.x + cardBox!.width, 'the card to the left of the assistant').toBeLessThanOrEqual(assistantBox!.x + 1);
  await shotOf('assistant-arrival');
  await page.mouse.move(1, 1);
  await expect(card).toBeHidden({ timeout: 15_000 });
  const panel = await openActionCenter(page);
  const over = await page.evaluate(() => {
    const open = document.querySelector('[data-testid=action-panel]')?.shadowRoot?.querySelector('.modal-wrapper') as HTMLElement | null;
    const box = (open ?? document.querySelector('[data-testid=action-featured]'))!.getBoundingClientRect();
    const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
    return hit?.closest('[data-testid=action-panel]') !== null;
  });
  expect(over, 'the panel over the assistant').toBe(true);
  await expect(featuredNotice(panel)).toBeVisible();
  await shotOf('assistant-panel');
  await closeActionCenter(page);
  await shown(page).locator('[data-testid=assistant-button]').click();
  await expect(assistant).toBeHidden();
}

/** At the till, with the charge sheet open, a new notice brings no card: the bell only counts it. */
async function expectQuietWhileCharging(page: Page, context: BrowserContext, shotOf: (state: string) => Promise<void>): Promise<void> {
  await clearItems(context, A);
  await checkWithDish(page, context, 'es', dish);
  await bellSaysTheServer(page, context);
  await noCardOnScreen(page);
  await shown(page).locator('[data-testid=pos-charge]').click();
  const sheet = page.locator('[data-testid=sale-checkout-modal]');
  await expect(sheet).toBeVisible();
  await raiseDemoNotice(context);
  // The card is offered in the same turn the bell takes the notice: once the bell counts it, no card means none came.
  await bellSaysTheServer(page, context);
  await expect(arrivalCard(page), 'no card while charging').toHaveCount(0);
  await shotOf('pos-checkout');
  await page.keyboard.press('Escape');
  await expect(sheet).toBeHidden();
}

/** «Configurar los datos del negocio» leads to the issuer; once it is saved, «Todavía no puedes facturar» goes. */
async function expectResolved(page: Page, context: BrowserContext, shotOf: (state: string) => Promise<void>): Promise<void> {
  const panel = await openActionCenter(page);
  await noticeButton(featuredNotice(panel), 'Configurar los datos del negocio').click();
  await expect(page).toHaveURL(/\/invoice\/issuer$/);
  await expect(actionPanel(page)).toBeHidden();
  const { legal_name, tax_id, address, postal_code, city, province, country } = original.configured ? original : { ...original, ...ISSUER };
  const saved = await api(context, A, 'POST', '/invoice/issuer', { legal_name, tax_id, address, postal_code, city, province, country });
  expect(saved.status).toBe(200);
  await bellSaysTheServer(page, context);
  await clearItems(context, A);
  const left = await bellSaysTheServer(page, context);
  if (left === 0) {
    await expect(actionBell(page)).not.toHaveClass(/has-notices/);
    await shotOf('bell-alone');
  }
  const opened = await openActionCenter(page);
  await expect(noticeIn(opened, BLOCKING)).toHaveCount(0);
  await closeActionCenter(page);
}

for (const size of SIZES) {
  for (const scheme of SCHEMES) {
    test(`BASE-F01 BASE-F10 at ${size.label}, ${scheme}: the bell, its arrivals and its panel`, async ({ browser }) => {
      test.setTimeout(300_000);
      const { context, page } = await spanishOwner(browser, size, scheme);
      const shotOf = (state: string) => captured(page, state, scheme, size.label);
      try {
        await clearItems(context, A);
        noPrintsWaiting();
        await page.reload();
        await bellSaysTheServer(page, context);
        await expect(actionBell(page)).toHaveAttribute('data-severity', 'danger');
        await shotOf('pill');
        await expectArrival(page, context, shotOf);
        await expectThePanel(page, size, shotOf);
        if (!compactBar(page)) await expectBesideTheAssistant(page, context, shotOf);
        await expectQuietWhileCharging(page, context, shotOf);
        await expectResolved(page, context, shotOf);
      } finally {
        await clearItems(context, A);
        await context.close();
        // The next run starts from a business that cannot issue invoices yet again.
        parkIssuerAgain();
      }
    });
  }
}

/** Hub `a` without an issuer again, keeping the one parked before the run. */
function parkIssuerAgain(): void {
  unparkIssuer(PARKED);
  parkIssuer(PARKED);
}

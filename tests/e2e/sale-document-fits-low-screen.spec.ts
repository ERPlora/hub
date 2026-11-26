// flow: SALE-F01, SALE-F29 — the ticket that opens right after charging, on a low screen. In Chrome on an Android
// tablet in landscape the address bar takes part of the screen: the page has 665 px of height while `100vh` still
// counts the 721 px it would have without the bar (hub#2543). The window fits the space the page really has, the
// ticket scrolls inside it, and its ✕ and its print button stay on view; the same at the fleet's sizes, in English
// and in Spanish, with a screenshot at each.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { A, capture, shown } from './helpers';
import { cleanTill, dishForTheTill, stamp, tillIn, TILL_LANGUAGES } from './sale-helpers';
import type { Product } from './inventory-helpers';
import { CHROME_LANDSCAPE, expectWindowOnScreen, underAddressBar, type WindowFit, windowFit } from './screen';

const RUN = stamp();
const SIZES = [
  { width: 1280, height: 665 },
  { width: 1280, height: 720 },
  { width: 1440, height: 900 },
  { width: 820, height: 1180 },
  { width: 375, height: 667 },
] as const;
/** What always shows inside the ticket's window. */
const ON_VIEW = ['✕', 'print button'] as const;

let dish: Product;

test.beforeAll(async ({ browser }) => {
  dish = await dishForTheTill(browser, 'DOCFIT', RUN);
});

test.afterAll(() => cleanTill());

/** Where the window, its ✕, its print button, its footer and the end of the paper sit, and the height the page has. */
function fitOf(modal: Locator): Promise<WindowFit> {
  return windowFit(modal, {
    '✕': '[data-testid=sale-document-close]',
    'print button': '[data-testid=sale-document-print]',
    footer: '.sale-doc-modal__footer',
    paper: '[data-testid=sale-receipt]',
  });
}

/** The ticket scrolled to its end inside the window: its last line ends above the footer. */
async function scrolledToTheEnd(modal: Locator): Promise<WindowFit> {
  await modal.locator('ion-content.sale-doc-modal__body').evaluate(async (content) => {
    await (content as HTMLElement & { scrollToBottom(duration?: number): Promise<void> }).scrollToBottom(0);
  });
  return fitOf(modal);
}

/** Charges the dish in cash on the till already open; the ticket's window opens on its own. */
async function chargeDish(page: Page): Promise<Locator> {
  await shown(page).locator(`[data-testid=pos-product-${dish.id}]`).click();
  await shown(page).locator('[data-testid=pos-charge]').click();
  const sheet = page.locator('[data-testid=sale-checkout-modal]');
  await expect(sheet).toBeVisible();
  for (const key of ['1', '0']) await sheet.locator(`[data-testid=sale-checkout-keypad-${key}]`).click();
  await sheet.locator('[data-testid=sale-checkout-confirm]').click();
  await expect(sheet).toBeHidden();
  const modal = page.locator('[data-testid=sale-document-modal]');
  await expect(modal.locator('[data-testid=sale-receipt]')).toBeVisible();
  await expect(modal.locator('[data-testid=sale-document-print]')).toBeEnabled();
  return modal;
}

for (const till of TILL_LANGUAGES) {
  test(`SALE-F29 (${till.name}): right after charging, the ticket's window fits a low screen with its ✕ and its print button on view`, async ({
    browser,
  }) => {
    const context = await browser.newContext({ baseURL: A, locale: till.locale, viewport: { width: CHROME_LANDSCAPE.width, height: CHROME_LANDSCAPE.withoutBar } });
    const page = await context.newPage();
    await tillIn(page, context, till.lang);
    const bar = await underAddressBar(page);
    const modal = await chargeDish(page);

    const fit = await fitOf(modal);
    expect(fit.screen, 'the page is as tall as the screen under the address bar').toBe(CHROME_LANDSCAPE.page);
    expectWindowOnScreen(fit, ON_VIEW, 'under the address bar');
    await capture(page, `SALE-DOCUMENT-FIT-${till.lang}-1280x665-chrome`);
    const end = await scrolledToTheEnd(modal);
    expect(end.parts.paper.bottom, 'the end of the ticket is reached above the footer').toBeLessThanOrEqual(end.parts.footer.top + 0.5);
    expectWindowOnScreen(end, ON_VIEW, 'with the ticket scrolled to its end');

    await bar.evaluate((style) => (style as Element).remove());
    for (const size of SIZES) {
      const label = `${size.width}x${size.height}`;
      await page.setViewportSize(size);
      const at = await fitOf(modal);
      expect(at.screen, `the page fills the window at ${label}`).toBe(size.height);
      expectWindowOnScreen(at, ON_VIEW, `at ${label}`);
      await capture(page, `SALE-DOCUMENT-FIT-${till.lang}-${label}`);
    }
    await context.close();
  });
}

// flow: SALE-F01, SALE-F29 — the ticket that opens right after charging, on a low screen. In Chrome on an Android
// tablet in landscape the address bar takes part of the screen: the page has 665 px of height while `100vh` still
// counts the 721 px it would have without the bar (hub#2543). The window fits the space the page really has, the
// ticket scrolls inside it, and its ✕ and its print button stay on view; the same at the fleet's sizes, in English
// and in Spanish, with a screenshot at each.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { A, capture, shown } from './helpers';
import { cleanTill, dishForTheTill, stamp, tillIn, TILL_LANGUAGES } from './sale-helpers';
import type { Product } from './inventory-helpers';

const RUN = stamp();
/** The tablet's screen with Chrome's address bar shown: what the page has, and what `100vh` counts. */
const CHROME_LANDSCAPE = { width: 1280, page: 665, withoutBar: 721 };
const SIZES = [
  { width: 1280, height: 665 },
  { width: 1280, height: 720 },
  { width: 1440, height: 900 },
  { width: 820, height: 1180 },
  { width: 375, height: 667 },
] as const;

interface Box {
  top: number;
  bottom: number;
}

interface DocumentFit {
  screen: number;
  window: Box;
  close: Box;
  print: Box;
  footer: Box;
  paper: Box;
}

let dish: Product;

test.beforeAll(async ({ browser }) => {
  dish = await dishForTheTill(browser, 'DOCFIT', RUN);
});

test.afterAll(() => cleanTill());

/** Where the window (Ionic's wrapper, in the modal's shadow root), its ✕, its print button, its footer and the end of
 *  the paper sit, and the height the page has (the modal's own box, which covers it). */
function fitOf(modal: Locator): Promise<DocumentFit> {
  return modal.evaluate((el) => {
    const box = (part: Element | null | undefined): Box => {
      if (!part) throw new Error('the document window lost one of its parts');
      const { top, bottom } = part.getBoundingClientRect();
      return { top, bottom };
    };
    return {
      screen: el.getBoundingClientRect().height,
      window: box(el.shadowRoot?.querySelector('.modal-wrapper')),
      close: box(el.querySelector('[data-testid=sale-document-close]')),
      print: box(el.querySelector('[data-testid=sale-document-print]')),
      footer: box(el.querySelector('.sale-doc-modal__footer')),
      paper: box(el.querySelector('[data-testid=sale-receipt]')),
    };
  });
}

function expectInside(fit: DocumentFit, where: string): void {
  expect(fit.window.top, `the window starts on the screen ${where}`).toBeGreaterThanOrEqual(-0.5);
  expect(fit.window.bottom, `the window ends on the screen ${where}`).toBeLessThanOrEqual(fit.screen + 0.5);
  for (const [name, part] of [
    ['✕', fit.close],
    ['print button', fit.print],
  ] as const) {
    expect(part.top, `the ${name} starts inside the window ${where}`).toBeGreaterThanOrEqual(fit.window.top - 0.5);
    expect(part.bottom, `the ${name} ends inside the window ${where}`).toBeLessThanOrEqual(fit.window.bottom + 0.5);
  }
}

/** The ticket scrolled to its end inside the window: its last line ends above the footer. */
async function scrolledToTheEnd(modal: Locator): Promise<DocumentFit> {
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
    // Chrome's address bar, as on the tablet: the page is 56 px shorter than what `100vh` counts.
    const bar = await page.addStyleTag({ content: `body { height: ${CHROME_LANDSCAPE.page}px !important; max-height: ${CHROME_LANDSCAPE.page}px !important; }` });
    const modal = await chargeDish(page);

    const fit = await fitOf(modal);
    expect(fit.screen, 'the page is as tall as the screen under the address bar').toBe(CHROME_LANDSCAPE.page);
    expectInside(fit, 'under the address bar');
    await capture(page, `SALE-DOCUMENT-FIT-${till.lang}-1280x665-chrome`);
    const end = await scrolledToTheEnd(modal);
    expect(end.paper.bottom, 'the end of the ticket is reached above the footer').toBeLessThanOrEqual(end.footer.top + 0.5);
    expectInside(end, 'with the ticket scrolled to its end');

    await bar.evaluate((style) => style.remove());
    for (const size of SIZES) {
      const label = `${size.width}x${size.height}`;
      await page.setViewportSize(size);
      const at = await fitOf(modal);
      expect(at.screen, `the page fills the window at ${label}`).toBe(size.height);
      expectInside(at, `at ${label}`);
      await capture(page, `SALE-DOCUMENT-FIT-${till.lang}-${label}`);
    }
    await context.close();
  });
}

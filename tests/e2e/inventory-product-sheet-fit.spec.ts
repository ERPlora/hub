// flow: INVENTORY-F25, INVENTORY-F29 — the product sheet on a low screen. A tablet in landscape is 1280×761 CSS px,
// and in Spanish the sheet's six actions wrap into several rows. Every action shows inside the window and the barcode
// is reached by scrolling the sheet above them, never hidden under them (hub#2012). In Chrome on that tablet the
// address bar leaves the page 665 px high while `100vh` still counts 721: the window fits the page, with its ✕ and its
// last row of actions on view. The same holds on a desktop, a tablet in portrait and a low phone, with a screenshot at
// each size.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { capture, signedInSpanish } from './helpers';
import {
  cleanInventory,
  createProduct,
  presentedDialog,
  productRow,
  productsReady,
  searchProducts,
  stamp,
} from './inventory-helpers';
import { CHROME_LANDSCAPE, expectWindowFitsAt, expectWindowOnScreen, underAddressBar, type WindowFit, windowFit } from './screen';
import { rowAction } from './service-helpers';

const RUN = stamp();
const LANDSCAPE_TABLET = { width: 1280, height: 761 };
const SIZES = [
  { width: 1440, height: 900 },
  { width: 820, height: 1180 },
  { width: 375, height: 667 },
] as const;
const ACTIONS = ['print-label', 'receive', 'count', 'write-off', 'sold-out', 'close-button'] as const;
/** What always shows inside the sheet's window: its ✕, its footer and every action. */
const ON_VIEW = ['✕', 'footer', ...ACTIONS] as const;

/** Where the sheet's window, its ✕, its fields, its barcode, its footer and its actions sit on screen. */
function fitOf(sheet: Locator): Promise<WindowFit> {
  return windowFit(sheet, {
    '✕': '[data-testid=inventory-product-detail-close]',
    footer: '.ep-form-modal__footer',
    body: '.ep-form-modal__body',
    barcode: '[data-testid=inventory-barcode]',
    ...Object.fromEntries(ACTIONS.map((id) => [id, `[data-testid=inventory-product-detail-${id}]`])),
  });
}

/** Scrolls the sheet's fields to their end, where the barcode is, and says where it all sits then. */
async function scrolledToBarcode(sheet: Locator): Promise<WindowFit> {
  await sheet.locator('.ep-form-modal__body').evaluate((body) => {
    body.scrollTop = body.scrollHeight;
  });
  return fitOf(sheet);
}

function expectBarcodeReached({ parts }: WindowFit): void {
  expect(parts.barcode.bottom, 'the barcode is not under the actions').toBeLessThanOrEqual(parts.footer.top + 0.5);
  expect(parts.barcode.bottom, 'the barcode is inside the fields').toBeLessThanOrEqual(parts.body.bottom + 0.5);
}

async function openSheet(page: Page, product: { id: string; sku: string }): Promise<Locator> {
  await productsReady(page);
  await searchProducts(page, product.sku);
  await expect(productRow(page, product.sku)).toBeVisible();
  return presentedDialog(page, 'inventory-product-detail', () => rowAction(page, 'inventory-products', product.id, 'detail'));
}

test.afterAll(() => cleanInventory());

test('INVENTORY-F25: on a tablet in landscape the product sheet shows all its actions inside its window', async ({ browser }) => {
  const { context, page } = await signedInSpanish(browser, LANDSCAPE_TABLET, '/inventory/products');
  const product = await createProduct(context, { name: `E2E Ficha baja ${RUN}`, sku: `E2E-FIT-${RUN}` });
  const sheet = await openSheet(page, product);
  for (const id of ACTIONS) await expect(sheet.locator(`[data-testid=inventory-product-detail-${id}]`)).toBeVisible();

  const fit = await fitOf(sheet);
  const rows = new Set(ACTIONS.map((id) => Math.round(fit.parts[id].top))).size;
  expect(rows, 'the six actions wrap, as on the tablet').toBeGreaterThan(1);
  expectWindowOnScreen(fit, ON_VIEW, 'at 1280x761');
  await capture(page, 'FIX-INVENTORY-SHEET-FIT-1280x761');

  expectBarcodeReached(await scrolledToBarcode(sheet));
  await capture(page, 'FIX-INVENTORY-SHEET-FIT-1280x761-barcode');

  await expectWindowFitsAt(page, { sizes: SIZES, measure: () => fitOf(sheet), onView: ON_VIEW, name: 'FIX-INVENTORY-SHEET-FIT' });
  await context.close();
});

test('INVENTORY-F29: in Chrome on a tablet in landscape, under the address bar, the product sheet fits the page with its ✕ and «Marcar agotado» on view', async ({
  browser,
}) => {
  const viewport = { width: CHROME_LANDSCAPE.width, height: CHROME_LANDSCAPE.withoutBar };
  const { context, page } = await signedInSpanish(browser, viewport, '/inventory/products');
  const product = await createProduct(context, { name: `E2E Ficha Chrome ${RUN}`, sku: `E2E-CHROME-${RUN}` });
  const bar = await underAddressBar(page);
  const sheet = await openSheet(page, product);

  const fit = await fitOf(sheet);
  expect(fit.screen, 'the page is as tall as the screen under the address bar').toBe(CHROME_LANDSCAPE.page);
  expectWindowOnScreen(fit, ON_VIEW, 'under the address bar');
  await capture(page, 'FIX-INVENTORY-SHEET-FIT-1280x665-chrome');
  const scrolled = await scrolledToBarcode(sheet);
  expectBarcodeReached(scrolled);
  expectWindowOnScreen(scrolled, ON_VIEW, 'with the barcode scrolled into view under the address bar');

  await bar.evaluate((style) => (style as Element).remove());
  const low = [{ width: CHROME_LANDSCAPE.width, height: CHROME_LANDSCAPE.page }];
  await expectWindowFitsAt(page, { sizes: low, measure: () => fitOf(sheet), onView: ON_VIEW, name: 'FIX-INVENTORY-SHEET-FIT' });
  await context.close();
});

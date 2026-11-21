// flow: INVENTORY-F25, INVENTORY-F29 — the product sheet on a low screen. A tablet in landscape is 1280×761 CSS px,
// and in Spanish the sheet's six actions wrap into several rows. Every action shows inside the window and the barcode
// is reached by scrolling the sheet above them, never hidden under them (hub#2012). The same holds on a desktop, a
// tablet in portrait and a low phone, with a screenshot at each size.
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
import { rowAction } from './service-helpers';

const RUN = stamp();
const LANDSCAPE_TABLET = { width: 1280, height: 761 };
const SIZES = [
  { width: 1440, height: 900 },
  { width: 820, height: 1180 },
  { width: 375, height: 667 },
] as const;
const ACTIONS = ['print-label', 'receive', 'count', 'write-off', 'sold-out', 'close-button'] as const;

interface Box {
  top: number;
  bottom: number;
}

interface SheetFit {
  window: Box;
  footer: Box;
  body: Box;
  barcode: Box;
  actions: Box[];
}

/** Where the sheet's window (Ionic's wrapper, in the modal's shadow root), its parts and its actions sit on screen. */
function fitOf(sheet: Locator): Promise<SheetFit> {
  return sheet.evaluate((modal, ids) => {
    const box = (el: Element | null | undefined): { top: number; bottom: number } => {
      if (!el) throw new Error('the product sheet lost one of its parts');
      const { top, bottom } = el.getBoundingClientRect();
      return { top, bottom };
    };
    return {
      window: box(modal.shadowRoot?.querySelector('.modal-wrapper')),
      footer: box(modal.querySelector('.ep-form-modal__footer')),
      body: box(modal.querySelector('.ep-form-modal__body')),
      barcode: box(modal.querySelector('[data-testid=inventory-barcode]')),
      actions: ids.map((id) => box(modal.querySelector(`[data-testid=inventory-product-detail-${id}]`))),
    };
  }, ACTIONS as readonly string[]);
}

/** Scrolls the sheet's fields to their end, where the barcode is. */
async function scrollToBarcode(sheet: Locator): Promise<void> {
  await sheet.locator('.ep-form-modal__body').evaluate((body) => {
    body.scrollTop = body.scrollHeight;
  });
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
  const rows = new Set(fit.actions.map((action) => Math.round(action.top))).size;
  expect(rows, 'the six actions wrap, as on the tablet').toBeGreaterThan(1);
  expect(fit.footer.bottom, 'the footer ends inside the window').toBeLessThanOrEqual(fit.window.bottom + 0.5);
  fit.actions.forEach((action, at) => {
    expect(action.top, `${ACTIONS[at]} starts inside the window`).toBeGreaterThanOrEqual(fit.window.top);
    expect(action.bottom, `${ACTIONS[at]} ends inside the window`).toBeLessThanOrEqual(fit.window.bottom + 0.5);
  });
  await capture(page, 'FIX-INVENTORY-SHEET-FIT-1280x761');

  await scrollToBarcode(sheet);
  const scrolled = await fitOf(sheet);
  expect(scrolled.barcode.bottom, 'the barcode is not under the actions').toBeLessThanOrEqual(scrolled.footer.top + 0.5);
  expect(scrolled.barcode.bottom, 'the barcode is inside the fields').toBeLessThanOrEqual(scrolled.body.bottom + 0.5);
  await capture(page, 'FIX-INVENTORY-SHEET-FIT-1280x761-barcode');

  for (const size of SIZES) {
    const label = `${size.width}x${size.height}`;
    await page.setViewportSize(size);
    await capture(page, `FIX-INVENTORY-SHEET-FIT-${label}`);
    const at = await fitOf(sheet);
    expect(at.footer.bottom, `the footer ends inside the window at ${label}`).toBeLessThanOrEqual(at.window.bottom + 0.5);
  }
  await context.close();
});

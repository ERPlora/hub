// flow: BASE-F01, SALE-F01
// hub#838: on a screen as low as a phone on its side (500 px high or less, the till's own cut, hub#800), the red strip
// «Todavía no puedes facturar» is one line, its title and «Configurar», with no sentence and no step named: it still
// warns and still leads to set up, and the till keeps room for a whole row of its catalogue. Before, the strip took
// 117 px and left `ion-content` 21 to 132 px between it, the top bar (60) and the tab bar (66). Under a browser's address
// bar (568x264, 640x304) a row (143 px) cannot fit even with no strip at all (264 − 60 − 66 = 138): there the measure is a
// floor, with the cart button whole. On a screen of normal height the strip is as it was, sentence and steps named.
// Hub `a` with no issuer (parked for the run), its owner in Spanish, on the till; the product `E2E-STRIPLOW-<run>` and
// the cash register switched off for the run are put back after it.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, capture, record, settled, shown } from './helpers';
import { cleanInventory, type Product } from './inventory-helpers';
import { parkIssuer, unparkIssuer } from './invoice-helpers';
import { dishForTheTill, restoreDrawer, stamp, tillIn } from './sale-helpers';

const KEY = 'FIX-HUB-838-BLOCKING-STRIP-LOW';
/** Hub `a`'s issuer, parked while the run needs the strip of a hub that cannot issue invoices yet. */
const PARKED = 'e2e_base_blocking_strip_low_issuer';
const RUN = stamp();
/** The one step pending in a local hub with no issuer, and where «Configurar» leads. */
const STEP = 'invoice.business_identity';
const STEP_ROUTE = '/invoice/issuer';
/** A phone on its side, and the lowest-widest window still under the cut: a whole row of the catalogue fits. The same
 *  phones in a browser, under its address bar (568x264, 640x304), have `least`: what `ion-content` keeps at least,
 *  measured with the strip in one line (21 and 61 px before). */
const LOW = [
  { label: '568x320', width: 568, height: 320 },
  { label: '640x360', width: 640, height: 360 },
  { label: '667x319', width: 667, height: 319 },
  { label: '667x375', width: 667, height: 375 },
  { label: '1280x500', width: 1280, height: 500 },
  { label: '568x264', width: 568, height: 264, least: 90 },
  { label: '640x304', width: 640, height: 304, least: 130 },
] as const;
/** Screens of normal height: the strip as it always was. */
const NORMAL = [
  { label: '1440x900', width: 1440, height: 900 },
  { label: '820x1180', width: 820, height: 1180 },
  { label: '375x667', width: 375, height: 667 },
] as const;
/** One line: the 40 px of «Configurar» (the touch minimum) and 4 px above and under it. */
const ONE_LINE = 48;
/** A fraction of a pixel of rounding between two boxes that touch. */
const EDGE = 0.5;

let product: Product;
let context: BrowserContext;
let page: Page;
const measured: Record<string, unknown> = {};

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser }) => {
  product = await dishForTheTill(browser, 'STRIPLOW', RUN);
  parkIssuer(PARKED);
  context = await browser.newContext({ baseURL: A, viewport: { width: 568, height: 320 }, locale: 'es-ES' });
  page = await context.newPage();
  await tillIn(page, context, 'es');
  await expect(shown(page).locator('[data-testid=blocking-strip]'), 'the strip of a hub that cannot issue invoices yet').toBeVisible();
  await expect(shown(page).locator(`[data-testid=pos-product-${product.id}]`)).toBeVisible();
});

test.afterAll(async () => {
  record(KEY, measured);
  try {
    await context?.close();
    unparkIssuer(PARKED);
  } finally {
    try {
      cleanInventory();
    } finally {
      restoreDrawer();
    }
  }
});

/** The strip, the content between the bars and the product's tile, as the shown page lays them out now. */
async function layout(where: string) {
  const strip = shown(page).locator('[data-testid=blocking-strip]');
  await expect(strip, `the strip at ${where}`).toBeVisible();
  await settled(page);
  return shown(page).evaluate((view, id) => {
    const box = (el: Element | null | undefined) => {
      const r = el?.getBoundingClientRect();
      return r ? { top: r.top, bottom: r.bottom, height: r.height } : null;
    };
    return {
      strip: box(view.querySelector('[data-testid=blocking-strip]'))!,
      title: box(view.querySelector('.blocking-strip-title'))!,
      configure: box(view.querySelector(`[data-testid="blocking-configure-${id}"]`)),
      content: box(view.querySelector('ion-content'))!,
      tabbar: box(view.querySelector('ion-footer.section-tabbar'))!,
    };
  }, STEP);
}

/** The product's tile scrolled into the content: is it whole between the content's edges? */
async function rowWhole(): Promise<boolean> {
  return shown(page).evaluate(async (view, id) => {
    const tile = view.querySelector(`[data-testid=pos-product-${id}]`);
    const content = view.querySelector('ion-content');
    if (!tile || !content) return false;
    tile.scrollIntoView({ block: 'nearest' });
    await new Promise((frame) => requestAnimationFrame(() => requestAnimationFrame(frame)));
    const t = tile.getBoundingClientRect();
    const c = content.getBoundingClientRect();
    return t.top >= c.top - 0.5 && t.bottom <= c.bottom + 0.5;
  }, product.id);
}

/** The cart button whole inside the content, between the strip and the tab bar, with the content scrolled to its top
 *  and to its bottom (Ionic's own `scrollToTop`/`scrollToBottom`). */
async function cartButtonWhole(where: string): Promise<void> {
  const fab = shown(page).locator('[data-testid=pos-cart-fab]');
  const content = shown(page).locator('ion-content');
  await expect(fab, `the cart button at ${where}`).toBeVisible();
  for (const end of ['top', 'bottom'] as const) {
    await content.evaluate(async (el, to) => {
      const ionContent = el as unknown as { scrollToTop(ms: number): Promise<void>; scrollToBottom(ms: number): Promise<void> };
      await (to === 'top' ? ionContent.scrollToTop(0) : ionContent.scrollToBottom(0));
    }, end);
    await settled(page);
    const button = (await fab.boundingBox())!;
    const room = (await content.boundingBox())!;
    expect.soft(button.y, `the cart button under the strip at ${where}, scrolled to the ${end}`).toBeGreaterThanOrEqual(room.y - EDGE);
    expect.soft(button.y + button.height, `the cart button over the tab bar at ${where}, scrolled to the ${end}`).toBeLessThanOrEqual(room.y + room.height + EDGE);
  }
}

/** One line: the title and «Configurar», no sentence and no step named. */
async function isOneLine(where: string): Promise<void> {
  const strip = shown(page).locator('[data-testid=blocking-strip]');
  await expect(strip.locator('.blocking-strip-title'), `the title at ${where}`).toHaveText('Todavía no puedes facturar');
  await expect(strip.locator('.blocking-strip-text'), `no sentence at ${where}`).toHaveCount(0);
  await expect(strip.locator('[data-testid=blocking-item]'), `no step named at ${where}`).toHaveCount(0);
  await expect(strip.locator(`[data-testid="blocking-configure-${STEP}"]`), `«Configurar» at ${where}`).toBeVisible();
  const box = await layout(where);
  expect(box.strip.height, `the strip in one line at ${where}`).toBeLessThanOrEqual(ONE_LINE + EDGE);
  const middle = (box.title.top + box.title.bottom) / 2;
  expect(box.configure, `«Configurar» at ${where}`).not.toBeNull();
  expect(middle, `the title beside «Configurar», on its line, at ${where}`).toBeGreaterThanOrEqual(box.configure!.top);
  expect(middle, `the title beside «Configurar», on its line, at ${where}`).toBeLessThanOrEqual(box.configure!.bottom);
}

test.describe('BASE-F01: a phone on its side keeps the strip in one line and room for the till', () => {
  for (const size of LOW) {
    const room = 'least' in size ? `at least ${size.least} px for the till (under a browser's address bar)` : 'a whole row of the catalogue';
    test(`${size.label}: one line, ${room}, and the cart button whole`, async () => {
      await page.setViewportSize({ width: size.width, height: size.height });
      await isOneLine(size.label);
      const box = await layout(size.label);
      measured[size.label] = { strip: box.strip.height, content: box.content.height };
      if ('least' in size) expect(box.content.height, `ion-content at ${size.label}`).toBeGreaterThanOrEqual(size.least);
      else expect(await rowWhole(), `a whole row of the catalogue inside the till at ${size.label} (ion-content ${box.content.height} px)`).toBe(true);
      await capture(page, `${KEY}-${size.label}`);
      await cartButtonWhole(size.label);
    });
  }

  test('568x264: «Configurar» still leads to set the business up, where the strip names no way in to itself', async () => {
    await page.setViewportSize({ width: 568, height: 264 });
    await shown(page).locator(`[data-testid="blocking-configure-${STEP}"]`).click();
    await expect(page).toHaveURL(new RegExp(`${STEP_ROUTE}$`));
    const strip = shown(page).locator('[data-testid=blocking-strip]');
    await expect(strip.locator('.blocking-strip-title')).toHaveText('Todavía no puedes facturar');
    await expect(strip.locator('ion-button')).toHaveCount(0);
    await expect(shown(page).locator('[data-testid=invoice-issuer-save]'), 'the issuer form, loaded').toBeAttached();
    const box = await layout('568x264 on the settings');
    expect(box.strip.height, 'the strip in one line on the settings').toBeLessThanOrEqual(ONE_LINE + EDGE);
    await capture(page, `${KEY}-568x264-settings`);
    await page.goBack();
    await expect(shown(page).locator('[data-testid=pos-till]')).toBeVisible();
  });
});

test.describe('BASE-F01: on a screen of normal height the strip is as it was', () => {
  for (const size of NORMAL) {
    test(`${size.label}: the sentence and the step named, with its «Configurar»`, async () => {
      await page.setViewportSize({ width: size.width, height: size.height });
      const strip = shown(page).locator('[data-testid=blocking-strip]');
      await expect(strip.locator('.blocking-strip-text')).toHaveText('No se podrá emitir ningún tique ni factura hasta que configures esto:');
      await expect(strip.locator('[data-testid=blocking-item]')).toHaveCount(1);
      await expect(strip.locator('[data-testid=blocking-item] strong')).toHaveText('Los datos de tu negocio');
      await expect(strip.locator(`[data-testid="blocking-configure-${STEP}"]`)).toBeVisible();
      const box = await layout(size.label);
      measured[size.label] = { strip: box.strip.height, content: box.content.height };
      expect(box.strip.height, `the strip in its three lines at ${size.label}`).toBeGreaterThan(ONE_LINE * 2);
      await capture(page, `${KEY}-${size.label}`);
    });
  }
});

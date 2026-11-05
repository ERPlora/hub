// flow: SALE-F01, SALE-F20
// hub#800: a phone on its side (568x320, 640x360, 667x375) sells from start to end, with the red strip of a hub that
// cannot issue invoices yet and without it, in English and in Spanish. Every tap here is a real one, never forced: a
// product from the catalogue, the cart button, the «+» of the check's line, the tabs of the check and «Charge», which
// opens its sheet. Before the fix, the strip left the till 45 to 100 px («Charge» under the tab bar, the cart button out
// of a finger's reach), and without it the bar and the foot of the check, 180 px, left 0 to 35 px for the lines.
// A phone upright and a tablet keep what they had: the drawer between the strip and the tab bar, nothing to scroll in
// the page, the cart button in its corner. What a run creates, its product `E2E-TILLSIDE-<run>`, its check and the
// issuer of a hub that had none (with it, the strip goes as it does for a business with its data complete), is deleted
// after it; hub `a`'s issuer is parked only for the runs with the strip.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, capture, login, settled, shown } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { cleanInvoices, ensureIssuer, parkIssuer, unparkIssuer } from './invoice-helpers';
import { cleanSales, drawerOff, restoreDrawer, stamp, tillIsPhone } from './sale-helpers';

const KEY = 'FIX-HUB-800-TILL-ON-ITS-SIDE';
/** Hub `a`'s issuer, parked while a run needs the strip of a hub that cannot issue invoices yet. */
const PARKED = 'e2e_sale_till_on_its_side_issuer';
const RUN = stamp();
/** A phone on its side: the lowest one is the narrowest phone there is, turned. */
const ON_ITS_SIDE = [
  { label: '568x320', width: 568, height: 320 },
  { label: '640x360', width: 640, height: 360 },
  { label: '667x375', width: 667, height: 375 },
] as const;
/** The lowest of them in a browser, under its address bar (56 px). Only without the strip: with it, 21 px are left
 *  between the strip and the tab bar, less than a cart button; the strip itself would have to give way. */
const UNDER_AN_ADDRESS_BAR = { label: '568x264', width: 568, height: 264 } as const;
/** Where the till is laid out as it always was. */
const UPRIGHT = [
  { label: '390x844', width: 390, height: 844 },
  { label: '820x1180', width: 820, height: 1180 },
] as const;
/** A real tap gives up soon: on main it spent its whole test retrying on what sat over the button. */
const TAP = { timeout: 5_000 };
/** A fraction of a pixel of rounding between two boxes that touch. */
const EDGE = 0.5;
/** What shows of the check's first line as the drawer opens, so nobody has to guess that the lines are further down. */
const LINE_PEEK = 30;

let product: Product;

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  // Cash without a cash session: the drawer's lock is sale-cash-gate.spec.ts's.
  await drawerOff(context);
  await ensureIssuer(context);
  product = await createProduct(context, { name: `E2E Till side ${RUN}`, sku: `E2E-TILLSIDE-${RUN}`, price: 700, tax_category_key: 'restaurant.drink' });
  await context.close();
});

test.afterAll(() => {
  try {
    cleanSales();
    cleanInventory();
    cleanInvoices();
  } finally {
    restoreDrawer();
  }
});

/** What a finger on the middle of `el` touches, with nothing scrolled first. */
async function touches(control: Locator): Promise<{ reached: boolean; hit: string; bottom: number }> {
  return control.evaluate((el) => {
    const box = el.getBoundingClientRect();
    const hit = document.elementFromPoint((box.left + box.right) / 2, (box.top + box.bottom) / 2);
    return {
      reached: !!hit && (el === hit || el.contains(hit)),
      hit: hit ? `${hit.tagName.toLowerCase()} ${hit.getAttribute('data-testid') ?? hit.className}`.trim() : 'nothing',
      bottom: box.bottom,
    };
  });
}

/** The check's line, whose «+» a real tap reaches, however low the window: the quantity goes up by one. */
async function tapTheLine(page: Page, where: string): Promise<void> {
  const line = shown(page).locator('[data-testid^=pos-line-]').filter({ hasText: product.name }).first();
  const quantity = line.locator('.pos-qty__field');
  const before = Number(await quantity.inputValue());
  await line.locator('[data-testid=pos-qty-plus]').click(TAP);
  await expect(quantity, `the «+» of the line works at ${where}`).toHaveValue(String(before + 1));
}

/** «Current order» and back, with real taps; its send bar and its flame take a tap too (a trial: nothing is sent). */
async function tapTheTabs(page: Page, where: string): Promise<void> {
  const drawer = shown(page).locator('[data-testid=pos-cart-drawer]');
  await drawer.locator('[data-testid=pos-cart-tab-round]').click(TAP);
  await expect(drawer.locator('[data-testid=pos-cart-tab-round]'), `«Current order» at ${where}`).toHaveAttribute('aria-selected', 'true');
  await tapTheLine(page, `${where}, on «Current order»`);
  await drawer.locator('[data-testid=pos-kitchen-send]').click({ ...TAP, trial: true });
  await drawer.locator('[data-testid=pos-kitchen-rush]').click({ ...TAP, trial: true });
  await capture(page, `${KEY}-${where.replaceAll(' ', '-')}-round`);
  await drawer.locator('[data-testid=pos-cart-tab-check]').click(TAP);
  await expect(drawer.locator('[data-testid=pos-cart-tab-check]'), `«Check» at ${where}`).toHaveAttribute('aria-selected', 'true');
}

/** A whole sale's taps, at the size the page is at now, from the catalogue to the charge sheet. */
async function sellOnItsSide(page: Page, size: { label: string; width: number; height: number }, strip: boolean, lang: string): Promise<void> {
  const where = `${lang} ${size.label} ${strip ? 'with-strip' : 'no-strip'}`;
  await page.setViewportSize({ width: size.width, height: size.height });
  expect(await tillIsPhone(page), `the check is a drawer at ${where}`).toBe(true);
  const till = shown(page).locator('[data-testid=pos-till]');
  const drawer = shown(page).locator('[data-testid=pos-cart-drawer]');
  await expect(drawer, `the drawer closed at ${where}`).toBeHidden();
  await settled(page);

  // The catalogue answers: the product goes on the check, and the button says so.
  const fab = till.locator('[data-testid=pos-cart-fab]');
  const total = till.locator('[data-testid=pos-cart-fab-total]');
  const before = (await total.count()) ? await total.innerText() : '';
  await till.locator(`[data-testid=pos-product-${product.id}]`).click(TAP);
  await expect(total, `the product on the check at ${where}`).not.toHaveText(before);
  await capture(page, `${KEY}-${where.replaceAll(' ', '-')}-catalogue`);

  // The cart button whole in what the page shows, wherever the catalogue is scrolled: its count too, 6 px over it.
  await settled(page);
  const button = await fab.evaluate((el) => {
    const box = el.getBoundingClientRect();
    const view = el.closest('.ion-page');
    const under = view?.querySelector('.page-notice')?.getBoundingClientRect().bottom ?? 0;
    const over = view?.querySelector('ion-footer.section-tabbar')?.getBoundingClientRect().top ?? 0;
    const content = view?.querySelector('ion-content')?.getBoundingClientRect();
    return { top: box.top, bottom: box.bottom, from: Math.max(under, content?.top ?? 0), to: over };
  });
  expect.soft(button.top - 6, `the cart button below what is above it at ${where}`).toBeGreaterThanOrEqual(button.from - EDGE);
  expect.soft(button.bottom, `the cart button above the tab bar at ${where}`).toBeLessThanOrEqual(button.to + EDGE);

  await fab.click(TAP);
  await expect(till).toHaveClass(/pos-till--cart-open/);
  await settled(page);
  await capture(page, `${KEY}-${where.replaceAll(' ', '-')}-check`);

  // The lines show as it opens: some of the first one between the tabs and the foot.
  const peek = await drawer.evaluate((el) => {
    const line = el.querySelector('[data-testid^=pos-line-]')?.getBoundingClientRect();
    const foot = el.querySelector('.pos-foot')?.getBoundingClientRect();
    return (foot?.top ?? 0) - (line?.top ?? 0);
  });
  // Under an address bar the heading and the tabs fill what is left: there, the line takes scrolling (tapped below).
  if (size.height >= ON_ITS_SIDE[0].height) expect.soft(peek, `the first line shows as the drawer opens at ${where}`).toBeGreaterThanOrEqual(LINE_PEEK);

  // The bar and the foot, on screen as the drawer opens, with nothing on top of them.
  for (const id of ['pos-cart-close', 'pos-open-checks', 'pos-prebill', 'pos-charge']) {
    const control = drawer.locator(`[data-testid=${id}]`);
    const reach = await touches(control);
    expect.soft(reach.reached, `a finger on «${id}» reaches it at ${where} (it touches «${reach.hit}»)`).toBe(true);
    expect.soft(reach.bottom, `«${id}» inside the window at ${where}`).toBeLessThanOrEqual(size.height + EDGE);
  }

  await tapTheLine(page, where);
  await tapTheTabs(page, where);

  // A real tap on «Charge» opens the sheet, and its way out works too.
  await drawer.locator('[data-testid=pos-charge]').click(TAP);
  const sheet = page.locator('[data-testid=sale-checkout-modal]');
  await expect(sheet.locator('[data-testid=sale-checkout-keypad]'), `the charge sheet at ${where}`).toBeVisible();
  await settled(page);
  // The sale can end from here: the keypad takes a real tap and the confirm button, a trial (nothing is charged).
  await sheet.locator('[data-testid=sale-checkout-keypad-5]').click(TAP);
  await sheet.locator('[data-testid=sale-checkout-confirm]').click({ ...TAP, trial: true });
  await sheet.locator('[data-testid=sale-checkout-close]').click(TAP);
  await expect(sheet).toBeHidden();

  await drawer.locator('[data-testid=pos-cart-close]').click(TAP);
  await expect(till).not.toHaveClass(/pos-till--cart-open/);
  await expect(drawer).toBeHidden();

  // A real tap outside closes it too, even where the top bar is under the shade: the dialog takes the whole page.
  await fab.click(TAP);
  await expect(till).toHaveClass(/pos-till--cart-open/);
  await settled(page);
  await page.mouse.click(8, 8);
  await expect(till, `a tap outside closes the drawer at ${where}`).not.toHaveClass(/pos-till--cart-open/);
  await expect(drawer).toBeHidden();
}

/** The search over the catalogue, as low as it gets: its field, its result and the line a real tap on it adds. */
async function searchOnItsSide(page: Page): Promise<void> {
  await page.setViewportSize({ width: ON_ITS_SIDE[0].width, height: ON_ITS_SIDE[0].height });
  const till = shown(page).locator('[data-testid=pos-till]');
  await expect(shown(page).locator('[data-testid=pos-cart-drawer]')).toBeHidden();
  await settled(page);
  await till.locator('[data-testid=pos-search-trigger]').click(TAP);
  const search = till.locator('[data-testid=pos-search]');
  await search.locator('input').fill(product.sku);
  const result = search.locator(`[data-testid=pos-search-${product.id}]`);
  await expect(result).toBeVisible();
  await capture(page, `${KEY}-search`);
  const total = till.locator('[data-testid=pos-cart-fab-total]');
  const before = (await total.count()) ? await total.innerText() : '';
  await result.click(TAP);
  await expect(total, 'the product found goes on the check').not.toHaveText(before);
}

/** The layout of a till that has room: nothing on its side has reached it. */
async function keepsItsLayout(page: Page, size: (typeof UPRIGHT)[number], where: string): Promise<void> {
  await page.setViewportSize({ width: size.width, height: size.height });
  const till = shown(page).locator('[data-testid=pos-till]');
  const drawer = shown(page).locator('[data-testid=pos-cart-drawer]');
  expect(await tillIsPhone(page), `the check is a drawer at ${where}`).toBe(true);
  await settled(page);
  await till.locator('[data-testid=pos-cart-fab]').click(TAP);
  await expect(till).toHaveClass(/pos-till--cart-open/);
  await settled(page);
  const seen = await till.evaluate((el) => {
    const box = (node: Element | null | undefined) => {
      const r = node?.getBoundingClientRect();
      return { top: r?.top ?? 0, bottom: r?.bottom ?? 0, right: r?.right ?? 0 };
    };
    const content = el.closest('ion-content');
    const scroller = content?.shadowRoot?.querySelector('.inner-scroll');
    const view = el.closest('.ion-page');
    return {
      till: box(el),
      drawer: box(el.querySelector('[data-testid=pos-cart-drawer]')),
      fab: box(el.querySelector('[data-testid=pos-cart-fab]')),
      tabbar: box(view?.querySelector('ion-footer.section-tabbar')),
      room: (scroller?.scrollHeight ?? 0) - (scroller?.clientHeight ?? 0),
      total: box(el.querySelector('.pos-foot__total')),
      actions: box(el.querySelector('.pos-foot__actions')),
    };
  });
  expect.soft(seen.total.bottom, `the total over the foot's buttons at ${where}`).toBeLessThanOrEqual(seen.actions.top + EDGE);
  // The drawer lies inside the till's border of 1 px: over it would be the strip, the top bar or the tab bar.
  expect.soft(Math.abs(seen.drawer.top - seen.till.top), `the drawer starts with the till at ${where}`).toBeLessThanOrEqual(1 + EDGE);
  expect.soft(Math.abs(seen.drawer.bottom - seen.till.bottom), `the drawer ends with the till at ${where}`).toBeLessThanOrEqual(1 + EDGE);
  expect.soft(seen.till.bottom, `the till above the tab bar at ${where}`).toBeLessThanOrEqual(seen.tabbar.top + EDGE);
  expect.soft(seen.room, `nothing to scroll in the page at ${where}`).toBeLessThanOrEqual(EDGE);
  await capture(page, `${KEY}-${where.replaceAll(' ', '-')}-upright`);
  await drawer.locator('[data-testid=pos-cart-close]').click(TAP);
  await expect(drawer).toBeHidden();
  const fab = await till.evaluate((el) => {
    const button = el.querySelector('[data-testid=pos-cart-fab]')?.getBoundingClientRect();
    const box = el.getBoundingClientRect();
    return { fromRight: box.right - (button?.right ?? 0), fromBottom: box.bottom - (button?.bottom ?? 0) };
  });
  // Its corner of the till: 1rem and the catalogue's own padding is not in it.
  expect.soft(fab.fromRight, `the cart button in its corner at ${where}`).toBeLessThanOrEqual(32);
  expect.soft(fab.fromBottom, `the cart button in its corner at ${where}`).toBeLessThanOrEqual(32);
}

test('SALE-F01: on a phone with a notch and a home bar, the drawer on its side keeps its buttons clear of them', async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A, viewport: { width: 667, height: 375 } });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  // What Ionic reads from the phone (`env(safe-area-inset-*)`), which a desktop's Chrome has at 0.
  await page.evaluate(() => {
    const root = document.documentElement.style;
    root.setProperty('--ion-safe-area-top', '12px');
    root.setProperty('--ion-safe-area-right', '44px');
    root.setProperty('--ion-safe-area-bottom', '21px');
  });
  const till = shown(page).locator('[data-testid=pos-till]');
  await till.locator(`[data-testid=pos-product-${product.id}]`).click(TAP);
  await till.locator('[data-testid=pos-cart-fab]').click(TAP);
  await expect(till).toHaveClass(/pos-till--cart-open/);
  await settled(page);
  const seen = await till.evaluate((el) => {
    const box = (id: string) => el.querySelector(`[data-testid=${id}]`)?.getBoundingClientRect();
    const drawer = el.querySelector('[data-testid=pos-cart-drawer]');
    return { close: box('pos-cart-close'), charge: box('pos-charge'), behindEdges: drawer ? getComputedStyle(drawer).backgroundColor : '' };
  });
  expect.soft(seen.behindEdges, 'the room left for the notch is the drawer’s, not a gap onto the shade').not.toBe('rgba(0, 0, 0, 0)');
  expect.soft(seen.close?.top ?? 0, 'the bar under the notch').toBeGreaterThanOrEqual(12);
  expect.soft(seen.close?.right ?? 667, '«Close» clear of the notch').toBeLessThanOrEqual(667 - 44 + EDGE);
  expect.soft(seen.charge?.right ?? 667, '«Charge» clear of the notch').toBeLessThanOrEqual(667 - 44 + EDGE);
  expect.soft(seen.charge?.bottom ?? 375, '«Charge» above the home bar').toBeLessThanOrEqual(375 - 21 + EDGE);
  await context.close();
});

const LANGUAGES = [
  { name: 'English', lang: 'en', locale: 'en-US' },
  { name: 'Spanish', lang: 'es', locale: 'es-ES' },
] as const;

for (const strip of [true, false]) {
  for (const { name, lang, locale } of LANGUAGES) {
    test.describe(`SALE-F01: in ${name}, ${strip ? 'under the red strip' : 'without the strip'}, a phone on its side sells`, () => {
      let context: BrowserContext;
      let page: Page;

      test.beforeAll(async ({ browser }) => {
        if (strip) parkIssuer(PARKED);
        context = await browser.newContext({ baseURL: A, locale, viewport: { width: 1440, height: 900 } });
        page = await context.newPage();
        await login(page, A, '/sale/pos');
        // In the language under test (the Hub's language cookie, which the sign-in has just set from the account).
        await context.addCookies([{ name: 'django_language', value: lang, domain: new URL(A).hostname, path: '/' }]);
        await page.reload();
        await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
        const notice = shown(page).locator('[data-testid=blocking-strip]');
        if (strip) await expect(notice, 'the strip of a hub that cannot issue invoices yet').toBeVisible();
        else await expect(notice, 'a hub with its issuer has no strip').toBeHidden();
      });

      test.afterAll(async () => {
        await context.close();
        if (strip) unparkIssuer(PARKED);
      });

      for (const size of strip ? ON_ITS_SIDE : [...ON_ITS_SIDE, UNDER_AN_ADDRESS_BAR]) {
        test(size.label, async () => {
          await sellOnItsSide(page, size, strip, lang);
        });
      }

      if (strip) {
        test('the search, under the strip of the lowest phone', async () => {
          await searchOnItsSide(page);
        });
      }

      for (const size of UPRIGHT) {
        test(`${size.label} keeps its layout`, async () => {
          await keepsItsLayout(page, size, `${lang} ${size.label} ${strip ? 'with-strip' : 'no-strip'}`);
        });
      }
    });
  }
}

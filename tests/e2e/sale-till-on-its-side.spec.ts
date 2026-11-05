// flow: SALE-F01, SALE-F20
// hub#800: a phone on its side (568x320, 640x360, 667x375) sells from start to end, with the red strip of a hub that
// cannot issue invoices yet and without it, in English and in Spanish. Every tap here is a real one, never forced: a
// product from the catalogue, the cart button, the «+» of the check's line, the tabs of the check and «Charge», which
// opens its sheet. Before the fix, the strip left the till 45 to 100 px («Charge» under the tab bar, the cart button out
// of a finger's reach), and without it the bar and the foot of the check, 180 px, left 0 to 35 px for the lines.
// A phone upright and a tablet keep what they had: the drawer between the strip and the tab bar, nothing to scroll in
// the page, the cart button in its corner, the foot in its two rows. What a run creates, its product `E2E-TILLSIDE-<run>`, its check and the
// issuer of a hub that had none (with it, the strip goes as it does for a business with its data complete), is deleted
// after it; hub `a`'s issuer is parked only for the runs with the strip.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, capture, login, settled, shown } from './helpers';
import { cleanInventory, type Product } from './inventory-helpers';
import { cleanInvoices, ensureIssuer, parkIssuer, unparkIssuer } from './invoice-helpers';
import { cleanSales, dishForTheTill, fingerOn, restoreDrawer, stamp, tillIn, tillIsPhone } from './sale-helpers';

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
/** As low, but so wide that one row of the catalogue does not fill the page. */
const LOW_AND_WIDE = { label: '1280x500', width: 1280, height: 500 } as const;
/** The page's own margin under the till. */
const PAGE_MARGIN = 16;
/** Where the till is laid out as it always was. */
const UPRIGHT = [
  { label: '390x844', width: 390, height: 844 },
  { label: '820x1180', width: 820, height: 1180 },
] as const;
/** A real tap gives up well before the test does: on main it spent its whole 180 s retrying on what sat over the button.
 *  Not less: a tap that landed still waits for the page, and with a loaded machine 5 s ran out on that. */
const TAP = { timeout: 15_000 };
/** A fraction of a pixel of rounding between two boxes that touch. */
const EDGE = 0.5;
/** What shows of the check's first line as the drawer opens, so nobody has to guess that the lines are further down. */
const LINE_PEEK = 30;

let product: Product;

test.beforeAll(async ({ browser }) => {
  product = await dishForTheTill(browser, 'TILLSIDE', RUN);
  // A business with its data complete has no strip; the runs with it park the issuer.
  const context = await browser.newContext({ baseURL: A });
  await login(await context.newPage(), A, '/sale/pos');
  await ensureIssuer(context);
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

/** A real tap on `pick` puts one more item on the check, which the cart button counts. Its total proves nothing: it reads
 *  «—» while the preview is on its way, whatever was tapped. */
async function addsOneItem(till: Locator, pick: Locator, where: string): Promise<void> {
  const count = till.locator('[data-testid=pos-cart-fab-count]');
  const before = (await count.count()) ? Number(await count.innerText()) : 0;
  await pick.click(TAP);
  await expect(count, `one more item on the check at ${where}`).toHaveText(String(before + 1));
}

/** «Open checks» opens whole inside the window, as low as it gets, and a tap beside it closes it. */
async function openChecksFit(page: Page, height: number, where: string): Promise<void> {
  const drawer = shown(page).locator('[data-testid=pos-cart-drawer]');
  await drawer.locator('[data-testid=pos-open-checks]').click(TAP);
  const checks = drawer.locator('[data-testid=pos-checks]');
  await expect(checks, `«Open checks» at ${where}`).toBeVisible();
  const bottom = await checks.evaluate((el) => el.getBoundingClientRect().bottom);
  expect.soft(bottom, `«Open checks» inside the window at ${where}`).toBeLessThanOrEqual(height + EDGE);
  await drawer.locator('[data-testid=pos-checks-backdrop]').click({ ...TAP, position: { x: 8, y: 8 } });
  await expect(checks).toBeHidden();
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
  await addsOneItem(till, till.locator(`[data-testid=pos-product-${product.id}]`), where);
  await capture(page, `${KEY}-${where.replaceAll(' ', '-')}-catalogue`);

  // The cart button whole in what the page shows, at both ends of the catalogue's scroll (the tap above moved it): its
  // count too, 6 px over it. Under an address bar with the strip nothing fits; that size is not sold here.
  await settled(page);
  for (const end of ['top', 'bottom'] as const) {
    const button = await fab.evaluate(async (el, to) => {
      const view = el.closest('.ion-page');
      const content = view?.querySelector('ion-content') as (Element & { getScrollElement(): Promise<HTMLElement> }) | null;
      const scroller = await content?.getScrollElement();
      if (scroller) scroller.scrollTop = to === 'top' ? 0 : scroller.scrollHeight;
      await new Promise((frame) => requestAnimationFrame(frame));
      const box = el.getBoundingClientRect();
      const tillBox = el.closest('[data-testid=pos-till]')?.getBoundingClientRect();
      const under = view?.querySelector('.page-notice')?.getBoundingClientRect().bottom ?? 0;
      const over = view?.querySelector('ion-footer.section-tabbar')?.getBoundingClientRect().top ?? 0;
      return {
        top: box.top,
        bottom: box.bottom,
        left: box.left,
        middle: ((tillBox?.left ?? 0) + (tillBox?.right ?? 0)) / 2,
        from: Math.max(under, content?.getBoundingClientRect().top ?? 0),
        to: over,
      };
    }, end);
    expect.soft(button.top - 6, `the cart button below what is above it at ${where}, scrolled to the ${end}`).toBeGreaterThanOrEqual(button.from - EDGE);
    expect.soft(button.bottom, `the cart button above the tab bar at ${where}, scrolled to the ${end}`).toBeLessThanOrEqual(button.to + EDGE);
    expect.soft(button.left, `the cart button in its corner, not across the till, at ${where}, scrolled to the ${end}`).toBeGreaterThan(button.middle);
  }

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
  for (const id of ['pos-cart-close', 'pos-open-checks', 'customer-search-trigger', 'pos-ticket-discount', 'pos-prebill', 'pos-charge']) {
    const reach = await drawer.locator(`[data-testid=${id}]`).evaluate(fingerOn);
    expect.soft(reach.reached, `a finger on «${id}» reaches it at ${where} (it touches «${reach.hit}»)`).toBe(true);
    expect.soft(reach.bottom, `«${id}» inside the window at ${where}`).toBeLessThanOrEqual(size.height + EDGE);
  }

  await tapTheLine(page, where);
  await tapTheTabs(page, where);
  await openChecksFit(page, size.height, where);

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

/** A check with no lines yet, as low as it gets: the cart button opens it, it says what to do, and «Charge» waits in view,
 *  off, until there is something to charge. */
async function emptyCheckOnItsSide(page: Page, where: string): Promise<void> {
  const { width, height } = ON_ITS_SIDE[0];
  await page.setViewportSize({ width, height });
  expect(await tillIsPhone(page), `the check is a drawer at ${where}`).toBe(true);
  const till = shown(page).locator('[data-testid=pos-till]');
  const drawer = shown(page).locator('[data-testid=pos-cart-drawer]');
  await expect(drawer).toBeHidden();
  await settled(page);
  await till.locator('[data-testid=pos-cart-fab]').click(TAP);
  await expect(till).toHaveClass(/pos-till--cart-open/);
  await settled(page);
  const bottomOf = (target: Locator): Promise<number> => target.evaluate((el) => el.getBoundingClientRect().bottom);
  const footTop = await drawer.locator('.pos-foot').evaluate((el) => el.getBoundingClientRect().top);
  await capture(page, `${KEY}-${where.replaceAll(' ', '-')}-empty`);
  expect.soft(await bottomOf(drawer.locator('[data-testid=pos-cart-empty]')), `«Tap a product» whole above the foot at ${where}`).toBeLessThanOrEqual(footTop + EDGE);
  // Off, a button takes no finger at all (`pointer-events: none`): only where it lies can be read.
  const charge = drawer.locator('[data-testid=pos-charge]');
  await expect(charge, `«Charge» off with nothing to charge at ${where}`).toHaveClass(/button-disabled/);
  expect.soft(await bottomOf(charge), `«Charge» inside the window at ${where}`).toBeLessThanOrEqual(height + EDGE);
  // «Current order» with nothing pending says so where it can be read too.
  await drawer.locator('[data-testid=pos-cart-tab-round]').click(TAP);
  const allSent = drawer.locator('[data-testid=pos-cart-round-empty] strong');
  await expect(allSent, `«Nothing to send» at ${where}`).toBeVisible();
  await capture(page, `${KEY}-${where.replaceAll(' ', '-')}-round-empty`);
  expect.soft(await bottomOf(allSent), `«Nothing to send» above the foot at ${where}`).toBeLessThanOrEqual(footTop + EDGE);
  await drawer.locator('[data-testid=pos-cart-tab-check]').click(TAP);
  await drawer.locator('[data-testid=pos-cart-close]').click(TAP);
  await expect(drawer).toBeHidden();

  // Upright, both keep the air they always had (2.5rem): the low phone's is not theirs.
  await page.setViewportSize({ width: UPRIGHT[0].width, height: UPRIGHT[0].height });
  expect(await tillIsPhone(page), `the check is a drawer at ${UPRIGHT[0].label}`).toBe(true);
  await expect(drawer).toBeHidden();
  await settled(page);
  const airOf = (target: Locator): Promise<string> => target.evaluate((el) => getComputedStyle(el).paddingTop);
  await till.locator('[data-testid=pos-cart-fab]').click(TAP);
  await expect(till).toHaveClass(/pos-till--cart-open/);
  expect.soft(await airOf(drawer.locator('[data-testid=pos-cart-empty]')), `«Tap a product» upright, from ${where}`).toBe('40px');
  await drawer.locator('[data-testid=pos-cart-tab-round]').click(TAP);
  expect.soft(await airOf(drawer.locator('[data-testid=pos-cart-round-empty]')), `«Nothing to send» upright, from ${where}`).toBe('40px');
  await drawer.locator('[data-testid=pos-cart-tab-check]').click(TAP);
  await drawer.locator('[data-testid=pos-cart-close]').click(TAP);
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
  await addsOneItem(till, result, 'the search');
}

/** A ticket discount on the lowest phone: its row over the total and the buttons, and «Charge» still in reach. */
async function discountOnItsSide(page: Page, where: string): Promise<void> {
  const { width, height } = ON_ITS_SIDE[0];
  await page.setViewportSize({ width, height });
  const till = shown(page).locator('[data-testid=pos-till]');
  const drawer = shown(page).locator('[data-testid=pos-cart-drawer]');
  await expect(drawer).toBeHidden();
  await settled(page);
  await addsOneItem(till, till.locator(`[data-testid=pos-product-${product.id}]`), where);
  await till.locator('[data-testid=pos-cart-fab]').click(TAP);
  await expect(till).toHaveClass(/pos-till--cart-open/);
  await drawer.locator('[data-testid=pos-ticket-discount]').click(TAP);
  const apply = page.locator('[data-testid=pos-discount-apply]');
  const sheet = page.locator('ion-modal').filter({ has: apply });
  await sheet.locator('[data-testid=pos-key-1]').click(TAP);
  await sheet.locator('[data-testid=pos-key-0]').click(TAP);
  await apply.click(TAP);
  await expect(apply).toBeHidden();
  await expect(drawer.locator('.pos-foot__discount')).toBeVisible();
  await settled(page);
  const rows = await drawer.evaluate((el) => ({
    discount: el.querySelector('.pos-foot__discount')?.getBoundingClientRect().bottom ?? 0,
    total: el.querySelector('.pos-foot__total')?.getBoundingClientRect().top ?? 0,
  }));
  expect.soft(rows.discount, `the discount over the total at ${where}`).toBeLessThanOrEqual(rows.total + EDGE);
  const charge = await drawer.locator('[data-testid=pos-charge]').evaluate(fingerOn);
  expect.soft(charge.reached, `a finger on «Charge» reaches it with a discount at ${where} (it touches «${charge.hit}»)`).toBe(true);
  expect.soft(charge.bottom, `«Charge» inside the window with a discount at ${where}`).toBeLessThanOrEqual(height + EDGE);
  await drawer.locator('[data-testid=pos-cart-close]').click(TAP);
  await expect(drawer).toBeHidden();
}

/** A window as low but wide: the catalogue does not fill the page, and the till's box still does. */
async function fillsThePage(page: Page, where: string): Promise<void> {
  await page.setViewportSize({ width: LOW_AND_WIDE.width, height: LOW_AND_WIDE.height });
  expect(await tillIsPhone(page), `the check is a drawer at ${where}`).toBe(true);
  await settled(page);
  const gap = await shown(page)
    .locator('[data-testid=pos-till]')
    .evaluate((el) => (el.closest('.ion-page')?.querySelector('ion-footer.section-tabbar')?.getBoundingClientRect().top ?? 0) - el.getBoundingClientRect().bottom);
  expect.soft(gap, `the till down to the page's margin at ${where}`).toBeLessThanOrEqual(PAGE_MARGIN + EDGE);
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
  // The foot's two rows with the air between them they always had (0.65rem): the low phone's one row is not theirs.
  expect.soft(seen.actions.top - seen.total.bottom, `the total over the foot's buttons at ${where}`).toBeGreaterThanOrEqual(8);
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
        await tillIn(page, context, lang);
        const notice = shown(page).locator('[data-testid=blocking-strip]');
        if (strip) await expect(notice, 'the strip of a hub that cannot issue invoices yet').toBeVisible();
        else await expect(notice, 'a hub with its issuer has no strip').toBeHidden();
      });

      test.afterAll(async () => {
        await context.close();
        if (strip) unparkIssuer(PARKED);
      });

      test('568x320, a check with no lines yet', async () => {
        await emptyCheckOnItsSide(page, `${lang} 568x320 ${strip ? 'with-strip' : 'no-strip'}`);
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

      if (!strip) {
        test('568x320, a check with a ticket discount', async () => {
          await discountOnItsSide(page, `${lang} 568x320 no-strip`);
        });

        test(`${LOW_AND_WIDE.label}, the till fills the page`, async () => {
          await fillsThePage(page, `${lang} ${LOW_AND_WIDE.label} no-strip`);
        });
      }
    });
  }
}

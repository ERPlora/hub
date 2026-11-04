// flow: SALE-F01
// hub#630: on a low phone the check's drawer holds what a cashier needs to charge. With a check open in the drawer,
// «Charge» is whole inside the drawer and above the section tab bar, and a finger on it reaches it (on a 320x568
// phone it lay under the tab bar: the tap fell on «Quick notes»); what sits between the bar and the foot scrolls, so
// the check's line is reached too; the controls of the check's bar never sit on one
// another, nor does their text spill out of them («Assign customer» sat on «Open checks»), and the customer's button
// keeps its words wherever two lines of them fit, as it always read there; and the charge sheet opened from there
// shows its whole cash keypad above its foot as soon as it opens (375x667: the last row peeked half under «Charge»;
// 320x568: three rows lay under it), with the words of a total still loading clear of the title on the lowest phone,
// where the figure shares the title's row. «Current order» leaves the same things in reach, plus its tabs and «Send
// order» (hub#787: at 320x568 its send bar ate all that scrolled, 0 px, and with it the tabs and the lines). A tablet
// and a desktop keep what they had. The worst case of a real
// business: the red strip of a hub that cannot issue invoices yet takes 138 px over the till (hub `a`'s issuer is
// parked for the run and put back after it), with Tables and Kitchen on (their button and the «Check» / «Current
// order» tabs). What a run creates, its product `E2E-CARTFIT-<run>` and its check, is deleted after it.
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, capture, login, psql, settled, shown, untilStill } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { cleanSales, drawerOff, openTillCart, restoreDrawer, stamp, tillIsPhone } from './sale-helpers';

const KEY = 'FIX-HUB-630-CART-PHONE';
/** Hub `a`'s issuer, parked while the run needs the strip of a hub that cannot issue invoices yet. */
const PARKED = 'e2e_sale_cart_phone_fit_issuer';
const RUN = stamp();
const SIZES = [
  /** The narrowest phone (an iPhone SE of the first generation): the customer's button is only its icon. */
  { label: '320x568', width: 320, height: 568, customerText: false },
  /** The commonest Android width, with the least room where the button still has its words. */
  { label: '360x640', width: 360, height: 640, customerText: true },
  /** The fleet's low phone (an iPhone SE). */
  { label: '375x667', width: 375, height: 667, customerText: true },
] as const;
/** A phone with room, even under the strip: «Send order» stays pinned while what is above it scrolls (hub#787). */
const ROOMY = { label: '390x844', width: 390, height: 844 } as const;
/** Where the check is not a phone's low drawer: nothing of this fix may change what they read. */
const WIDE = [
  { label: '820x1180', width: 820, height: 1180 },
  { label: '1440x900', width: 1440, height: 900 },
] as const;
/** A fraction of a pixel of rounding between two boxes that touch. */
const EDGE = 0.5;

type Box = { left: number; top: number; right: number; bottom: number };

let product: Product;
/** A second line, so that one can be marked: only with two lines or more. */
let other: Product;

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser }) => {
  psql([`drop table if exists ${PARKED}`, `create table ${PARKED} as select * from invoice_issuer`, 'delete from invoice_issuer'].join('; '));
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  // Cash without a cash session: the drawer's lock is sale-cash-gate.spec.ts's.
  await drawerOff(context);
  product = await createProduct(context, { name: `E2E Cart fit ${RUN}`, sku: `E2E-CARTFIT-${RUN}`, price: 700, tax_category_key: 'restaurant.drink' });
  other = await createProduct(context, { name: `E2E Cart fit other ${RUN}`, sku: `E2E-CARTFIT-B-${RUN}`, price: 300, tax_category_key: 'restaurant.drink' });
  await context.close();
});

test.afterAll(() => {
  try {
    cleanSales();
    cleanInventory();
  } finally {
    try {
      restoreDrawer();
    } finally {
      psql(['delete from invoice_issuer', `insert into invoice_issuer select * from ${PARKED}`, `drop table ${PARKED}`].join('; '));
    }
  }
});

/** The check's drawer open, still, at the size the page is at now. After a resize the drawer first leaves (0.25 s). */
async function openDrawer(page: Page): Promise<Locator> {
  const drawer = shown(page).locator('[data-testid=pos-cart-drawer]');
  expect(await tillIsPhone(page), 'the till is a phone’s: the check is a drawer').toBe(true);
  await expect(drawer).toBeHidden();
  await openTillCart(page);
  await settled(page);
  return drawer;
}

/** «Charge» whole inside the drawer, above the tab bar, and what a finger on its centre touches is «Charge». */
async function chargeWithinReach(page: Page, drawer: Locator, where: string): Promise<Locator> {
  const charge = shown(page).locator('[data-testid=pos-charge]');
  const reach = await page.evaluate(() => {
    const view = document.querySelector('.ion-page:not(.ion-page-hidden) [data-testid=pos-till]')?.closest('.ion-page');
    const box = (el: Element | null | undefined): Box | null => {
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { left: r.left, top: r.top, right: r.right, bottom: r.bottom };
    };
    const charge = view?.querySelector('[data-testid=pos-charge]');
    const at = charge && box(charge);
    const hit = at && document.elementFromPoint((at.left + at.right) / 2, (at.top + at.bottom) / 2);
    return {
      charge: at,
      drawer: box(view?.querySelector('[data-testid=pos-cart-drawer]')),
      tabbar: box(view?.querySelector('ion-footer.section-tabbar')),
      reached: !!hit && !!charge?.contains(hit),
      hit: hit ? `${hit.tagName.toLowerCase()} ${hit.getAttribute('data-testid') ?? ''}`.trim() : 'nothing',
    };
  });
  expect(reach.charge, `«Charge» on screen at ${where}`).not.toBeNull();
  expect(reach.drawer, `the drawer at ${where}`).not.toBeNull();
  expect(reach.tabbar, `the tab bar at ${where}`).not.toBeNull();
  const { charge: box, drawer: room, tabbar } = reach as { charge: Box; drawer: Box; tabbar: Box };
  expect.soft(box.top, `«Charge» below the top of the drawer at ${where}`).toBeGreaterThanOrEqual(room.top - EDGE);
  expect.soft(box.bottom, `«Charge» inside the drawer at ${where}`).toBeLessThanOrEqual(room.bottom + EDGE);
  expect.soft(box.bottom, `«Charge» above the tab bar at ${where}`).toBeLessThanOrEqual(tabbar.top + EDGE);
  expect(reach.reached, `a finger on «Charge» reaches it at ${where} (it touches «${reach.hit}»)`).toBe(true);
  await expect(drawer).toBeVisible();
  return charge;
}

/** The check's line, scrolled into view inside the drawer: what sits between the bar and the foot scrolls, and a
 *  finger on the line reaches it (squeezed to nothing, the lines would be out of any scroll's reach). */
async function lineWithinReach(page: Page, where: string): Promise<void> {
  const line = shown(page).locator('[data-testid^=pos-line-]').filter({ hasText: product.name }).first();
  await line.scrollIntoViewIfNeeded();
  const reach = await line.evaluate((el) => {
    const r = el.getBoundingClientRect();
    const hit = document.elementFromPoint((r.left + r.right) / 2, (r.top + r.bottom) / 2);
    return { height: r.height, reached: !!hit && el.contains(hit), hit: hit ? `${hit.tagName.toLowerCase()} ${hit.getAttribute('data-testid') ?? ''}`.trim() : 'nothing' };
  });
  expect(reach.height, `the check's line has its height at ${where}`).toBeGreaterThan(0);
  expect(reach.reached, `a finger on the check's line reaches it at ${where} (it touches «${reach.hit}»)`).toBe(true);
}

/** A control of «Current order», brought to the top of what scrolls as a finger would: its middle answers with itself. */
async function reachedOnceScrolled(control: Locator, name: string, where: string): Promise<void> {
  const reach = await control.evaluate((el) => {
    el.scrollIntoView({ block: 'start' });
    const r = el.getBoundingClientRect();
    const hit = document.elementFromPoint((r.left + r.right) / 2, (r.top + r.bottom) / 2);
    return { height: r.height, reached: !!hit && el.contains(hit), hit: hit ? `${hit.tagName.toLowerCase()} ${hit.getAttribute('data-testid') ?? ''}`.trim() : 'nothing' };
  });
  expect.soft(reach.height, `«${name}» has its height at ${where}`).toBeGreaterThan(0);
  expect.soft(reach.reached, `a finger on «${name}» reaches it at ${where} (it touches «${reach.hit}»)`).toBe(true);
}

/** «Current order» in the drawer (hub#787): its two tabs, the line to send, its quantity, the flame and «Send order» are
 *  all reached by scrolling (with room, «Send order» is in view from the start, however the rest scrolls), «Charge» stays
 *  where it is, and a real tap on «Check» goes back. */
async function roundFits(page: Page, size: { label: string; width: number; height: number }, lang: 'en' | 'es'): Promise<void> {
  const where = `${lang} ${size.label}, «Current order»`;
  await page.setViewportSize({ width: size.width, height: size.height });
  await expect(shown(page).locator('[data-testid=blocking-strip]'), 'the strip of a hub that cannot issue invoices yet').toBeVisible();
  const drawer = await openDrawer(page);
  const till = shown(page);
  const check = till.locator('[data-testid=pos-cart-tab-check]');
  const round = till.locator('[data-testid=pos-cart-tab-round]');
  await round.click({ timeout: 5_000 });
  await expect(round).toHaveAttribute('aria-selected', 'true');
  await untilStill(page);
  await capture(page, `${KEY}-${lang}-round-${size.label}`);

  const send = till.locator('[data-testid=pos-kitchen-send]');
  if (size.label === ROOMY.label) {
    const middle = await till.locator('[data-testid=pos-cart] .pos-cart__scroll').evaluate((el) => {
      el.scrollTo(0, 0);
      return { scrolls: el.scrollHeight > el.clientHeight };
    });
    expect(middle.scrolls, `there is something to scroll at ${where}`).toBe(true);
    await expect(send, `«Send order» pinned at ${where}`).toBeInViewport({ ratio: 1 });
  }
  await reachedOnceScrolled(check, 'Check', where);
  await reachedOnceScrolled(round, 'Current order', where);
  const line = till.locator('[data-testid^=pos-line-]').filter({ hasText: product.name }).first();
  await reachedOnceScrolled(line, 'the line to send', where);
  await line.locator('[data-testid=pos-qty-plus]').click({ trial: true, timeout: 5_000 });
  await reachedOnceScrolled(till.locator('[data-testid=pos-kitchen-rush]'), 'the flame', where);
  await reachedOnceScrolled(send, 'Send order', where);
  await send.click({ trial: true, timeout: 5_000 });
  await chargeWithinReach(page, drawer, where);
  await capture(page, `${KEY}-${lang}-round-send-${size.label}`);

  await check.click({ timeout: 5_000 });
  await expect(check).toHaveAttribute('aria-selected', 'true');
  await till.locator('[data-testid=pos-cart-close]').click();
  await expect(drawer).toBeHidden();
}

/** The check's bar: no control on another, every control inside the bar, and the text of each inside its control. */
async function barInOrder(page: Page, where: string): Promise<void> {
  const bar = shown(page).locator('[data-testid=pos-cart] .pos-toolbar');
  const parts = await bar.evaluate((el) => {
    const box = (r: DOMRect) => ({ left: r.left, top: r.top, right: r.right, bottom: r.bottom });
    const controls = [...el.querySelectorAll('ion-button')].filter((control) => {
      const r = control.getBoundingClientRect();
      return r.width > 0 && r.height > 0 && getComputedStyle(control).visibility !== 'hidden';
    });
    return {
      bar: box(el.getBoundingClientRect()),
      controls: controls.map((control) => {
        // The painted text of the control: its text nodes' line boxes (none for text that is not displayed).
        const text: { left: number; top: number; right: number; bottom: number }[] = [];
        const walker = document.createTreeWalker(control, NodeFilter.SHOW_TEXT);
        for (let node = walker.nextNode(); node; node = walker.nextNode()) {
          if (!node.textContent?.trim()) continue;
          const range = document.createRange();
          range.selectNodeContents(node);
          for (const r of range.getClientRects()) if (r.width > 0) text.push(box(r));
        }
        return { id: control.getAttribute('data-testid') ?? control.className, ...box(control.getBoundingClientRect()), text };
      }),
    };
  });
  expect(parts.controls.length, `the bar's controls at ${where}`).toBeGreaterThanOrEqual(3);
  const controls = [...parts.controls].sort((a, b) => a.left - b.left);
  for (const control of controls) {
    expect.soft(control.left, `«${control.id}» inside the bar at ${where}`).toBeGreaterThanOrEqual(parts.bar.left - EDGE);
    expect.soft(control.right, `«${control.id}» inside the bar at ${where}`).toBeLessThanOrEqual(parts.bar.right + EDGE);
    for (const line of control.text) {
      expect.soft(line.left, `the text of «${control.id}» inside it at ${where}`).toBeGreaterThanOrEqual(control.left - EDGE);
      expect.soft(line.right, `the text of «${control.id}» inside it at ${where}`).toBeLessThanOrEqual(control.right + EDGE);
      expect.soft(line.top, `the text of «${control.id}» inside it at ${where}`).toBeGreaterThanOrEqual(control.top - EDGE);
      expect.soft(line.bottom, `the text of «${control.id}» inside it at ${where}`).toBeLessThanOrEqual(control.bottom + EDGE);
    }
  }
  for (let i = 1; i < controls.length; i++) {
    expect.soft(controls[i].left, `«${controls[i].id}» clear of «${controls[i - 1].id}» at ${where}`).toBeGreaterThanOrEqual(controls[i - 1].right - EDGE);
  }
}

/** Every key of the cash keypad whole above the sheet's foot, as the sheet is now. */
async function keysAboveFoot(sheet: Locator, where: string): Promise<void> {
  const places = await sheet.evaluate((root) => ({
    foot: root.querySelector('.sheet-foot')?.getBoundingClientRect().top ?? 0,
    keys: [...root.querySelectorAll('[data-testid=sale-checkout-keypad] > button')].map((key) => ({
      id: key.getAttribute('data-testid') ?? '',
      bottom: key.getBoundingClientRect().bottom,
    })),
  }));
  expect(places.keys.length, `the keypad at ${where}`).toBe(12);
  for (const key of places.keys) expect.soft(key.bottom, `«${key.id}» above the foot at ${where}`).toBeLessThanOrEqual(places.foot + EDGE);
}

/** The customer's button: its words whole inside it where it has them, only its icon and its name where it does not. */
async function customerButton(page: Page, name: string, hasText: boolean, where: string): Promise<void> {
  const trigger = shown(page).locator('[data-testid=pos-cart] [data-testid=customer-search-trigger]');
  const label = trigger.locator('.customer-search__label');
  // Ionic hands the host's aria-label to its native button: the name a screen reader reads.
  const read = await trigger.evaluate((el) => el.shadowRoot?.querySelector('button')?.getAttribute('aria-label') ?? el.getAttribute('aria-label'));
  expect(read, `the button is named at ${where}`).toBe(name);
  if (!hasText) {
    await expect(label, `only its icon at ${where}`).toBeHidden();
    return;
  }
  await expect(label, `its words at ${where}`).toBeVisible();
  // No line cut away: as tall as it would be with no limit of lines (a word too wide for the button breaks into one more).
  const cut = await label.evaluate((el) => {
    const limited = el.getBoundingClientRect().height;
    el.style.setProperty('-webkit-line-clamp', 'none');
    const whole = el.getBoundingClientRect().height;
    el.style.removeProperty('-webkit-line-clamp');
    return whole - limited;
  });
  expect.soft(cut, `its words whole at ${where}`).toBeLessThanOrEqual(0.5);
}

/** A customer whose name does not fit: two lines at most, ended in «…», inside the button and clear of the next control. */
async function aLongNameStaysInside(page: Page, where: string): Promise<void> {
  const trigger = shown(page).locator('[data-testid=pos-cart] [data-testid=customer-search-trigger]');
  const fit = await trigger.evaluate((el) => {
    const label = el.querySelector('.customer-search__label') as HTMLElement;
    const before = label.textContent;
    label.textContent = 'María del Carmen Fernández de la Peña Rodríguez';
    const box = el.getBoundingClientRect();
    const words = label.getBoundingClientRect();
    const lineHeight = parseFloat(getComputedStyle(label).lineHeight);
    const checks = el.closest('.pos-toolbar')?.querySelector('[data-testid=pos-open-checks]')?.getBoundingClientRect();
    const seen = { lines: Math.round(words.height / lineHeight), hidden: label.scrollHeight > label.clientHeight, inside: words.left >= box.left && words.right <= box.right && words.top >= box.top && words.bottom <= box.bottom, clear: !!checks && box.right <= checks.left + 0.5 };
    label.textContent = before;
    return seen;
  });
  expect.soft(fit.lines, `a long name in two lines at ${where}`).toBeLessThanOrEqual(2);
  expect.soft(fit.hidden, `the rest of a long name is cut at ${where}`).toBe(true);
  expect.soft(fit.inside, `a long name inside its button at ${where}`).toBe(true);
  expect.soft(fit.clear, `a long name clear of «Open checks» at ${where}`).toBe(true);
}

async function cartFits(page: Page, size: (typeof SIZES)[number], lang: 'en' | 'es', assign: string): Promise<void> {
  const where = `${lang} ${size.label}`;
  await page.setViewportSize({ width: size.width, height: size.height });
  await expect(shown(page).locator('[data-testid=blocking-strip]'), 'the strip of a hub that cannot issue invoices yet').toBeVisible();
  const drawer = await openDrawer(page);
  await barInOrder(page, where);
  await customerButton(page, assign, size.customerText, where);
  if (size.customerText) await aLongNameStaysInside(page, where);
  await lineWithinReach(page, where);
  const charge = await chargeWithinReach(page, drawer, where);
  await capture(page, `${KEY}-${lang}-cart-${size.label}`);

  // A real tap on «Charge» opens the sheet (on main it timed out on the tab bar).
  await charge.click({ timeout: 5_000 });
  const sheet = page.locator('[data-testid=sale-checkout-modal]');
  await expect(sheet.locator('[data-testid=sale-checkout-keypad]')).toBeVisible();
  await expect(sheet.locator('[data-testid=sale-checkout-total]')).toContainText(/\d/);
  await settled(page);
  expect(await sheet.locator('.sale-checkout').evaluate((el) => el.scrollTop), `the sheet as it opens at ${where}`).toBe(0);
  await keysAboveFoot(sheet, where);
  await capture(page, `${KEY}-${lang}-sheet-${size.label}`);

  await sheet.locator('[data-testid=sale-checkout-close]').click();
  await expect(sheet).toBeHidden();
  await shown(page).locator('[data-testid=pos-cart-close]').click();
  await expect(drawer).toBeHidden();
}

/** The tablet's drawer and the desktop's column: the button in one line, «Charge» in reach, and the line in view. */
async function wideKeepsItsBar(page: Page, size: (typeof WIDE)[number], lang: 'en' | 'es', assign: string): Promise<void> {
  const where = `${lang} ${size.label}`;
  await page.setViewportSize({ width: size.width, height: size.height });
  const phone = await tillIsPhone(page);
  if (phone) await expect(shown(page).locator('[data-testid=pos-cart-drawer]')).toBeHidden();
  await openTillCart(page);
  await settled(page);
  await barInOrder(page, where);
  await customerButton(page, assign, true, where);
  const lines = await shown(page).locator('[data-testid=pos-cart] .customer-search__label').evaluate((el) => Math.round(el.getBoundingClientRect().height / parseFloat(getComputedStyle(el).lineHeight)));
  expect(lines, `the button in one line at ${where}`).toBe(1);
  await lineWithinReach(page, where);
  await expect(shown(page).locator('[data-testid=pos-charge]')).toBeVisible();
  await shown(page).locator('[data-testid=pos-charge]').click({ trial: true, timeout: 5_000 });
  await capture(page, `${KEY}-${lang}-wide-${size.label}`);
  if (phone) {
    await shown(page).locator('[data-testid=pos-cart-close]').click();
    await expect(shown(page).locator('[data-testid=pos-cart-drawer]')).toBeHidden();
  }
}

/** A till of its own in the language under test (the Hub's language cookie, which the sign-in has just set from the
 *  account), with `product` on its check. */
async function tillWithALine(browser: Browser, locale: string, lang: string): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, locale, viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  await context.addCookies([{ name: 'django_language', value: lang, domain: new URL(A).hostname, path: '/' }]);
  await page.reload();
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  await shown(page).locator(`[data-testid=pos-product-${product.id}]`).click();
  await expect(shown(page).locator('[data-testid^=pos-line-]').filter({ hasText: product.name }).first()).toBeAttached();
  return { context, page };
}

const LANGUAGES = [
  { name: 'English', lang: 'en', locale: 'en-US', assign: 'Assign customer' },
  { name: 'Spanish', lang: 'es', locale: 'es-ES', assign: 'Asignar cliente' },
] as const;

for (const { name, lang, locale, assign } of LANGUAGES) {
  test.describe(`SALE-F01: in ${name}, on a low phone the check's drawer reaches «Charge» and its bar stays in order`, () => {
    let context: BrowserContext;
    let page: Page;

    test.beforeAll(async ({ browser }) => {
      ({ context, page } = await tillWithALine(browser, locale, lang));
      await expect(shown(page).locator('[data-testid=customer-search-trigger]'), 'the bar in the language under test').toContainText(assign);
    });

    test.afterAll(async () => {
      await context.close();
    });

    for (const size of SIZES) {
      test(size.label, async () => {
        await cartFits(page, size, lang, assign);
      });
    }

    for (const size of WIDE) {
      test(size.label, async () => {
        await wideKeepsItsBar(page, size, lang, assign);
      });
    }
  });
}

for (const { name, lang, locale } of LANGUAGES) {
  // A check of their own: a real tap on «Charge», above, sends what is pending, and «Current order» would have nothing.
  test.describe(`SALE-F20: in ${name}, on a low phone «Current order» keeps its tabs, its lines and «Send order» in reach`, () => {
    let context: BrowserContext;
    let page: Page;

    test.beforeAll(async ({ browser }) => {
      ({ context, page } = await tillWithALine(browser, locale, lang));
    });

    test.afterAll(async () => {
      await context.close();
    });

    for (const size of [...SIZES, ROOMY]) {
      test(size.label, async () => {
        await roundFits(page, size, lang);
      });
    }
  });
}

for (const { name, lang, locale } of LANGUAGES) {
  // A marked line: the total of the whole check is already followed by the till, the total of a part has no earlier
  // answer to show while the new one is held back (and it is what a real part charge shows on a slow network).
  test(`SALE-F01: in ${name}, at 320x568 the sheet's total still being worked out stays between its title and «Close»`, async ({ browser }) => {
    const { context, page } = await tillWithALine(browser, locale, lang);
    const line = shown(page).locator('[data-testid^=pos-line-]').filter({ hasText: product.name }).first();
    await shown(page).locator(`[data-testid=pos-product-${other.id}]`).click();
    await expect(shown(page).locator('[data-testid^=pos-line-]').filter({ hasText: other.name }).first()).toBeAttached();
    await line.locator('[data-testid$=-mark]').click();
    await page.setViewportSize({ width: 320, height: 568 });
    await openDrawer(page);

    // The stream the opening sheet asks for never answers.
    await page.route('**/api/live**', () => {});
    await shown(page).locator('[data-testid=pos-charge]').click({ timeout: 5_000 });
    const sheet = page.locator('[data-testid=sale-checkout-modal]');
    await expect(sheet.locator('.pay-total__loading')).toBeVisible();
    const row = await sheet.evaluate((root) => {
      const box = (selector: string) => {
        const r = root.querySelector(selector)?.getBoundingClientRect();
        return { left: r?.left ?? 0, top: r?.top ?? 0, right: r?.right ?? 0, bottom: r?.bottom ?? 0 };
      };
      return { words: box('.pay-total__loading'), title: box('[data-testid=sale-checkout-title]'), close: box('[data-testid=sale-checkout-close]') };
    });
    expect.soft(row.words.left, 'the loading words clear of the title').toBeGreaterThanOrEqual(row.title.right - EDGE);
    expect.soft(row.words.right, 'the loading words clear of «Close»').toBeLessThanOrEqual(row.close.left + EDGE);
    expect.soft(row.words.bottom, 'the loading words in the row of the title').toBeLessThanOrEqual(row.close.bottom + EDGE);
    await capture(page, `${KEY}-${lang}-loading-320x568`);
    await context.close();
  });
}

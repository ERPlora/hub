// flow: SALE-F01
// hub#630: on a low phone the check's drawer holds what a cashier needs to charge. With a check open in the drawer,
// «Charge» is whole inside the drawer and above the section tab bar, and a finger on it reaches it (on a 320x568
// phone it lay under the tab bar: the tap fell on «Quick notes»); the controls of the check's bar never sit on one
// another, nor does their text spill out of them («Assign customer» sat on «Open checks»); and the charge sheet opened
// from there shows its whole cash keypad above its foot as soon as it opens where it fits (375x667: the last row
// peeked half under «Charge»), and once scrolled to its end where it does not (320x568). The worst case of a real
// business: the red strip of a hub that cannot issue invoices yet takes 138 px over the till (hub `a`'s issuer is
// parked for the run and put back after it), with Tables and Kitchen on (their button and the «Check» / «Current
// order» tabs). What a run creates, its product `E2E-CARTFIT-<run>` and its check, is deleted after it.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, capture, login, psql, settled, shown } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { cleanSales, drawerOff, openTillCart, restoreDrawer, stamp, tillIsPhone } from './sale-helpers';

const KEY = 'FIX-HUB-630-CART-PHONE';
/** Hub `a`'s issuer, parked while the run needs the strip of a hub that cannot issue invoices yet. */
const PARKED = 'e2e_sale_cart_phone_fit_issuer';
const RUN = stamp();
const SIZES = [
  /** The narrowest phone (an iPhone SE of the first generation): the sheet's keypad is reached by scrolling it. */
  { label: '320x568', width: 320, height: 568, keypadOnOpen: false },
  /** The fleet's low phone (an iPhone SE): the whole keypad fits the sheet as it opens. */
  { label: '375x667', width: 375, height: 667, keypadOnOpen: true },
] as const;
/** A fraction of a pixel of rounding between two boxes that touch. */
const EDGE = 0.5;

type Box = { left: number; top: number; right: number; bottom: number };

let product: Product;

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser }) => {
  psql([`drop table if exists ${PARKED}`, `create table ${PARKED} as select * from invoice_issuer`, 'delete from invoice_issuer'].join('; '));
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  // Cash without a cash session: the drawer's lock is sale-cash-gate.spec.ts's.
  await drawerOff(context);
  product = await createProduct(context, { name: `E2E Cart fit ${RUN}`, sku: `E2E-CARTFIT-${RUN}`, price: 700, tax_category_key: 'restaurant.drink' });
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

/** The sheet's scroller at its end (again until it holds: a scroll while the sheet still grows into place is lost). */
async function toTheEnd(sheet: Locator): Promise<void> {
  const box = sheet.locator('.sale-checkout');
  await expect
    .poll(() => box.evaluate((el) => (el.scrollTo({ top: el.scrollHeight }), el.scrollHeight - el.clientHeight - el.scrollTop)), {
      message: 'the sheet scrolled to its end',
    })
    .toBeLessThanOrEqual(1);
}

async function cartFits(page: Page, size: (typeof SIZES)[number], lang: 'en' | 'es'): Promise<void> {
  const where = `${lang} ${size.label}`;
  await page.setViewportSize({ width: size.width, height: size.height });
  await expect(shown(page).locator('[data-testid=blocking-strip]'), 'the strip of a hub that cannot issue invoices yet').toBeVisible();
  const drawer = await openDrawer(page);
  await barInOrder(page, where);
  const charge = await chargeWithinReach(page, drawer, where);
  await capture(page, `${KEY}-${lang}-cart-${size.label}`);

  // A real tap on «Charge» opens the sheet (on main it timed out on the tab bar).
  await charge.click({ timeout: 5_000 });
  const sheet = page.locator('[data-testid=sale-checkout-modal]');
  await expect(sheet.locator('[data-testid=sale-checkout-keypad]')).toBeVisible();
  await expect(sheet.locator('[data-testid=sale-checkout-total]')).toContainText(/\d/);
  await settled(page);
  if (size.keypadOnOpen) {
    expect(await sheet.locator('.sale-checkout').evaluate((el) => el.scrollTop), `the sheet as it opens at ${where}`).toBe(0);
  } else {
    await toTheEnd(sheet);
  }
  await keysAboveFoot(sheet, where);
  await capture(page, `${KEY}-${lang}-sheet-${size.label}`);

  await sheet.locator('[data-testid=sale-checkout-close]').click();
  await expect(sheet).toBeHidden();
  await shown(page).locator('[data-testid=pos-cart-close]').click();
  await expect(drawer).toBeHidden();
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
      context = await browser.newContext({ baseURL: A, locale, viewport: { width: 1440, height: 900 } });
      page = await context.newPage();
      await login(page, A, '/sale/pos');
      // In the language under test (the Hub's language cookie, which the sign-in has just set from the account).
      await context.addCookies([{ name: 'django_language', value: lang, domain: new URL(A).hostname, path: '/' }]);
      await page.reload();
      await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
      await expect(shown(page).locator('[data-testid=customer-search-trigger]'), 'the bar in the language under test').toContainText(assign);
      await shown(page).locator(`[data-testid=pos-product-${product.id}]`).click();
      await expect(shown(page).locator('[data-testid^=pos-line-]').filter({ hasText: product.name }).first()).toBeAttached();
    });

    test.afterAll(async () => {
      await context.close();
    });

    for (const size of SIZES) {
      test(size.label, async () => {
        await cartFits(page, size, lang);
      });
    }
  });
}

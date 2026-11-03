// flow: SALE-F01
// hub#456: while the amount tendered is typed, the keypad of the charge sheet stays where it is under the finger, at
// every size and in both languages, from the first key to the change and back. On the QA's tablet the «Change» row
// appeared above the keypad and pushed it almost a finger down, so the next tap fell on the key above: «10», «.», «5»
// tendered 1,072.00 instead of 10.50. The sheet is as tall as its content, centred from 821 px and held to the bottom
// below, so anything of it that grows or shrinks while typing moves the keys, wherever it is. Here the taps go, blind,
// to where each key was when the sheet opened, as a cashier's do; the sheet is scrolled to its end first, where a
// sheet that shrinks would pull its content along. What a run creates, its product `E2E-KEYPAD-<run>` and its check,
// is deleted after it.
import { type Browser, expect, type Locator, type Page, test } from '@playwright/test';

import { A, capture, login, painted, shown } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { cleanSales, drawerOff, openTillCart, restoreDrawer, stamp } from './sale-helpers';

const KEY = 'FIX-HUB-456-KEYPAD';
/** Long enough for a figure on screen to catch up with a tap, short enough for a run that fails at every size. */
const SAYS_MS = 2000;
const RUN = stamp();
const SIZES = [
  /** The QA's tablet in landscape, in the native app (the status bar takes 24 of its 800). */
  { label: '1280x776', width: 1280, height: 776 },
  /** The same tablet in its browser, with its bars. */
  { label: '1280x680', width: 1280, height: 680 },
  /** The fleet's three: a desk, a tablet in portrait and a low phone (an iPhone SE). */
  { label: '1440x900', width: 1440, height: 900 },
  { label: '820x1180', width: 820, height: 1180 },
  { label: '375x667', width: 375, height: 667 },
  /** A tall phone, where the whole sheet fits. */
  { label: '390x844', width: 390, height: 844 },
  /** The narrowest phone: the longest reason takes two lines of the row over the keypad. */
  { label: '320x568', width: 320, height: 568 },
] as const;
type KeyId = '0' | '1' | '5' | 'clear' | 'dot';
/** The issue's way of tendering: the two digits that cover the total, then what makes them another figure. */
const TAPS: readonly KeyId[] = ['1', '0', 'dot', '5'];
type Places = Record<string, { x: number; y: number; width: number; height: number }>;

let product: Product;

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  // Cash without a cash session: the drawer's lock is sale-cash-gate.spec.ts's.
  await drawerOff(context);
  product = await createProduct(context, { name: `E2E Keypad ${RUN}`, sku: `E2E-KEYPAD-${RUN}`, price: 700, tax_category_key: 'restaurant.drink' });
  await context.close();
});

test.afterAll(() => {
  try {
    cleanSales();
    cleanInventory();
  } finally {
    restoreDrawer();
  }
});

/** The check on screen holds the run's product, once. */
async function aCheck(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  await shown(page).locator(`[data-testid=pos-product-${product.id}]`).click();
  await expect(shown(page).locator('[data-testid^=pos-line-]').filter({ hasText: product.name }).first()).toBeAttached();
}

async function openSheet(page: Page): Promise<Locator> {
  await openTillCart(page);
  await shown(page).locator('[data-testid=pos-charge]').click();
  const sheet = page.locator('[data-testid=sale-checkout-modal]');
  await expect(sheet.locator('[data-testid=sale-checkout-keypad]')).toBeVisible();
  await expect(sheet.locator('[data-testid=sale-checkout-total]')).toContainText(/\d/);
  // Both scrollers at their end: on a low screen, where the keys are reached; the column's from 821 px, the sheet's below.
  for (const scroller of ['.sale-checkout', '.pay-tender']) {
    await sheet.locator(scroller).evaluate((box) => box.scrollTo({ top: box.scrollHeight }));
  }
  await capture(page, `${KEY}-sheet`);
  return sheet;
}

/** Where every key is on screen, to the pixel's tenth, once the browser has painted the last tap. All in one read. */
async function places(page: Page, sheet: Locator): Promise<Places> {
  await painted(page);
  const keypad = sheet.locator('[data-testid=sale-checkout-keypad] > button');
  return keypad.evaluateAll((keys) => {
    const round = (n: number) => Math.round(n * 10) / 10;
    return Object.fromEntries(
      keys.map((key) => {
        const box = key.getBoundingClientRect();
        const id = (key.getAttribute('data-testid') ?? '').replace('sale-checkout-keypad-', '');
        return [id, { x: round(box.x), y: round(box.y), width: round(box.width), height: round(box.height) }];
      }),
    );
  });
}

/** A tap where the key was when the sheet opened, wherever it is now. */
async function tapBlind(page: Page, at: Places, key: KeyId): Promise<void> {
  await page.mouse.click(at[key].x + at[key].width / 2, at[key].y + at[key].height / 2);
}

const figure = (cents: number, separator: string): string => `${Math.floor(cents / 100)}${separator}${String(cents % 100).padStart(2, '0')}`;

/** The sheet's total in cents, as the screen says it. */
async function totalOf(sheet: Locator): Promise<number> {
  const digits = /(\d+)[.,](\d{2})/.exec(await sheet.locator('[data-testid=sale-checkout-total]').innerText());
  expect(digits, 'the total').not.toBeNull();
  return Number(digits![1]) * 100 + Number(digits![2]);
}

async function keypadStaysStill(page: Page, size: (typeof SIZES)[number], lang: 'en' | 'es'): Promise<void> {
  await page.setViewportSize({ width: size.width, height: size.height });
  const sheet = await openSheet(page);
  const at = await places(page, sheet);
  const where = `${lang} ${size.label}`;
  expect.soft(at['0'].y + at['0'].height, `the last row on screen at ${where}`).toBeLessThanOrEqual(size.height);
  const total = await totalOf(sheet);
  const separator = lang === 'es' ? ',' : '.';
  const tendered = sheet.locator('[data-testid=sale-checkout-tendered]');
  const change = sheet.locator('[data-testid=sale-checkout-change]');

  for (const key of TAPS) {
    await tapBlind(page, at, key);
    expect.soft(await places(page, sheet), `the keys after «${key}» at ${where}`).toEqual(at);
  }
  await expect.soft(tendered, `tendered at ${where}`).toContainText(figure(1050, separator), { timeout: SAYS_MS });
  await expect.soft(change, `change at ${where}`).toContainText(figure(1050 - total, separator), { timeout: SAYS_MS });
  await capture(page, `${KEY}-${lang}-covered-${size.label}`);

  // Cleared, the change goes and the keys still stay: the next figure is typed in the same place.
  await tapBlind(page, at, 'clear');
  await expect.soft(change, `no change after clearing at ${where}`).toHaveCount(0, { timeout: SAYS_MS });
  expect.soft(await places(page, sheet), `the keys after clearing at ${where}`).toEqual(at);
  await tapBlind(page, at, '1');
  expect.soft(await places(page, sheet), `the keys with too little at ${where}`).toEqual(at);
  await capture(page, `${KEY}-${lang}-short-${size.label}`);
  await tapBlind(page, at, 'clear');

  await sheet.locator('[data-testid=sale-checkout-close]').click();
  await expect(sheet).toBeHidden();
}

async function everySize(browser: Browser, lang: 'en' | 'es', tendered: string): Promise<void> {
  const context = await browser.newContext({ baseURL: A, locale: lang === 'es' ? 'es-ES' : 'en-US', viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  // In the language under test (the Hub's language cookie, which the sign-in has just set from the account).
  await context.addCookies([{ name: 'django_language', value: lang, domain: new URL(A).hostname, path: '/' }]);
  await page.reload();
  await aCheck(page);
  const sheet = await openSheet(page);
  await expect(sheet.locator('[data-testid=sale-checkout-tendered]'), 'the sheet in the language under test').toContainText(tendered);
  await sheet.locator('[data-testid=sale-checkout-close]').click();
  await expect(sheet).toBeHidden();
  for (const size of SIZES) await keypadStaysStill(page, size, lang);
  await context.close();
}

test('SALE-F01: in English, the keypad stays under the finger until the change is on screen', async ({ browser }) => {
  test.setTimeout(420_000);
  await everySize(browser, 'en', 'Tendered');
});

test('SALE-F01: in Spanish, the keypad stays under the finger until the change is on screen', async ({ browser }) => {
  test.setTimeout(420_000);
  await everySize(browser, 'es', 'Entregado');
});

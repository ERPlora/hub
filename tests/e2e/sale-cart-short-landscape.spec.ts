// flow: SALE-F20
// hub#820: on a small tablet on its side, or a window as low, the check's side column with Kitchen on shows a whole
// line of the check. Between the check's heading (95 px), its «Check» / «Current order» tabs (60 px with their margin)
// and «Send order» (67 px), a line (139 px) does not fit in a column of 360 px or less. There the whole column scrolls as
// the phone's drawer does, with «Send order» pinned at its bottom: a finger brings a line to the top and reads it whole
// above the bar. Where a line fits (1280x816 with the strip, 1024x712 without it, the desktop), the heading and the tabs
// stay in place and only the lines scroll, as they always did; the phone's and the tablet's drawer keep scrolling all as
// one. Both tabs, in English and in Spanish. What a run creates, its product
// `E2E-SHORTSIDE-<run>`, its check and the issuer of a hub that had none (with it, the strip goes as it does for a
// business with its data complete), is deleted after it; hub `a`'s issuer is parked only for the runs with the strip.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { capture, settled, shown } from './helpers';
import { type Product } from './inventory-helpers';
import { cleanTillAndIssuer, dishWithAnIssuer, openTillCart, stamp, TILL_LANGUAGES, tillIsPhone, tillUnderStrip } from './sale-helpers';

const KEY = 'FIX-HUB-820-SHORT-LANDSCAPE';
/** Hub `a`'s issuer, parked while a run needs the strip of a hub that cannot issue invoices yet. */
const PARKED = 'e2e_sale_cart_short_landscape_issuer';
const RUN = stamp();

interface Size {
  label: string;
  width: number;
  height: number;
  /** Whether the red strip of a hub that cannot issue invoices yet sits over the till. */
  strip: boolean;
  /** `short`: a side column where a line did not fit beside the heading, the tabs and the bar; `roomy`: one where it
   *  fits, which keeps its layout; `drawer`: the phone's and the tablet's check, which already scrolled all as one. */
  kind: 'short' | 'roomy' | 'drawer';
}

const SIZES: readonly Size[] = [
  // The issue's: a small tablet on its side and a low laptop window, without the strip, and a 1024x700 tablet with it.
  { label: '1024x600', width: 1024, height: 600, strip: false, kind: 'short' },
  { label: '1280x560', width: 1280, height: 560, strip: false, kind: 'short' },
  { label: '1024x700', width: 1024, height: 700, strip: true, kind: 'short' },
  // Measured beside them: an iPad on its side and a 720p laptop, with the strip.
  { label: '1024x768', width: 1024, height: 768, strip: true, kind: 'short' },
  { label: '1280x720', width: 1280, height: 720, strip: true, kind: 'short' },
  // That iPad in a browser, under its address bar and tabs (332 px), whatever the strip does.
  { label: '1024x672', width: 1024, height: 672, strip: false, kind: 'short' },
  // A laptop under the strip and a tablet window without it (356 and 360 px): a line of 115 px fitted there, one of 139
  // beside the tabs does not (hub#1435).
  { label: '1280x800', width: 1280, height: 800, strip: true, kind: 'short' },
  { label: '1024x700', width: 1024, height: 700, strip: false, kind: 'short' },
  // The lowest columns where a line fits (372 px: 152 for the lines), and the desktop.
  { label: '1280x816', width: 1280, height: 816, strip: true, kind: 'roomy' },
  { label: '1024x712', width: 1024, height: 712, strip: false, kind: 'roomy' },
  { label: '1440x900', width: 1440, height: 900, strip: true, kind: 'roomy' },
  // The tablet upright and the fleet's low phone: the drawer.
  { label: '820x1180', width: 820, height: 1180, strip: true, kind: 'drawer' },
  { label: '375x667', width: 375, height: 667, strip: true, kind: 'drawer' },
];

/** A real tap gives up well before the test does. */
const TAP = { timeout: 15_000 };

let dish: Product;

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser }) => {
  dish = await dishWithAnIssuer(browser, 'SHORTSIDE', RUN);
});

test.afterAll(cleanTillAndIssuer);

/** Whether `el` is whole in what the window shows, run in the page: its top, its middle and its bottom answer with
 *  itself under a finger. A scroller that clips it, or a bar pinned over it, answers with something else. */
function wholeInView(el: Element): { height: number; whole: boolean; hits: string[] } {
  const r = el.getBoundingClientRect();
  const x = (r.left + r.right) / 2;
  const hits = [r.top + 2, (r.top + r.bottom) / 2, r.bottom - 2].map((y) => {
    const hit = y >= 0 && y < window.innerHeight ? document.elementFromPoint(x, y) : null;
    if (hit && el.contains(hit)) return '';
    return hit ? `${hit.tagName.toLowerCase()} ${hit.getAttribute('data-testid') ?? hit.className}`.trim() : 'nothing';
  });
  return { height: r.height, whole: r.height > 0 && hits.every((hit) => hit === ''), hits };
}

async function expectWhole(control: Locator, name: string, where: string): Promise<void> {
  const seen = await control.evaluate(wholeInView);
  expect.soft(seen.height, `«${name}» has its height at ${where}`).toBeGreaterThan(0);
  expect(seen.whole, `«${name}» whole in view at ${where} (its top, middle and bottom touch: ${seen.hits.map((hit) => hit || 'itself').join(' / ')})`).toBe(true);
}

/** What scrolls in the check back at its top, the lines' own scroll too: as the tab opens. */
async function scrolledToTop(cart: Locator): Promise<void> {
  await cart.evaluate((el) => {
    for (const part of el.querySelectorAll('.pos-cart__scroll, .pos-cart__body')) part.scrollTo(0, 0);
  });
}

/** A finger brings the dish's line to the top of what scrolls, and reads it whole. */
async function aWholeLine(cart: Locator, where: string): Promise<void> {
  const line = cart.locator('[data-testid^=pos-line-]').filter({ hasText: dish.name }).first();
  await line.evaluate((el) => el.scrollIntoView({ block: 'start' }));
  await expectWhole(line, 'the line', where);
}

/** A column with room keeps its layout: the heading and the tabs stay in place, only the lines scroll. */
async function keepsItsLayout(cart: Locator, where: string): Promise<void> {
  const layout = await cart.evaluate((el) => {
    const column = el.querySelector('.pos-cart__scroll') as HTMLElement;
    const body = el.querySelector('.pos-cart__body') as HTMLElement;
    return { columnScrolls: column.scrollHeight - column.clientHeight > 1, lines: getComputedStyle(body).overflowY };
  });
  expect.soft(layout.lines, `the lines scroll on their own at ${where}`).toBe('auto');
  expect.soft(layout.columnScrolls, `the heading and the tabs stay in place at ${where}`).toBe(false);
}

/** Both tabs whole across the check: their strip keeps inside the column, which never scrolls sideways (hub#1435: the
 *  strip was as wide as the column plus its margin, and «Current order» lost 8 px past the edge). */
async function tabsAcross(cart: Locator, where: string): Promise<void> {
  const seen = await cart.evaluate((el) => {
    const column = el.querySelector('.pos-cart__scroll') as HTMLElement;
    const left = column.getBoundingClientRect().left;
    const tabs = [...el.querySelectorAll('[data-testid=pos-cart-tab-check], [data-testid=pos-cart-tab-round]')].map((tab) => {
      const r = tab.getBoundingClientRect();
      return { id: tab.getAttribute('data-testid') ?? '', left: r.left, right: r.right };
    });
    return { left, right: left + column.clientWidth, sideways: column.scrollWidth - column.clientWidth, tabs };
  });
  expect(seen.tabs.length, `both tabs at ${where}`).toBe(2);
  expect.soft(seen.sideways, `the check does not scroll sideways at ${where}`).toBeLessThanOrEqual(0);
  for (const tab of seen.tabs) {
    expect.soft(tab.left, `«${tab.id}» inside the check at ${where}`).toBeGreaterThanOrEqual(seen.left - 0.5);
    expect.soft(tab.right, `«${tab.id}» inside the check at ${where}`).toBeLessThanOrEqual(seen.right + 0.5);
  }
}

async function readsALine(page: Page, size: Size, lang: string): Promise<void> {
  const where = `${lang} ${size.label} ${size.strip ? 'with-strip' : 'no-strip'}`;
  await page.setViewportSize({ width: size.width, height: size.height });
  expect(await tillIsPhone(page), `the check is ${size.kind === 'drawer' ? 'a drawer' : 'a side column'} at ${where}`).toBe(size.kind === 'drawer');
  await openTillCart(page);
  await settled(page);
  const cart = shown(page).locator('[data-testid=pos-cart]');

  // «Current order»: in the side column «Send order» is pinned at the bottom from the start, and a line is whole above
  // it. A drawer as low as the phone's under the strip lets the bar scroll after the lines (hub#787,
  // sale-cart-phone-fit.spec.ts): there it is reached by scrolling.
  const round = cart.locator('[data-testid=pos-cart-tab-round]');
  await round.click(TAP);
  await expect(round, `«Current order» at ${where}`).toHaveAttribute('aria-selected', 'true');
  await settled(page);
  await scrolledToTop(cart);
  await tabsAcross(cart, `${where}, «Current order»`);
  const send = cart.locator('[data-testid=pos-kitchen-send]');
  const column = size.kind !== 'drawer';
  if (column) await expectWhole(send, 'Send order', `${where}, «Current order» as it opens`);
  if (size.kind === 'roomy') await keepsItsLayout(cart, `${where}, «Current order»`);
  await aWholeLine(cart, `${where}, «Current order»`);
  if (column) await expectWhole(send, 'Send order', `${where}, «Current order» with the line in view`);
  await capture(page, `${KEY}-${where.replaceAll(' ', '-')}-round`);
  if (!column) {
    await send.evaluate((el) => el.scrollIntoView({ block: 'end' }));
    await expectWhole(send, 'Send order', `${where}, «Current order» scrolled to it`);
  }
  await send.click({ ...TAP, trial: true });

  // «Check»: a line whole, and «Charge» under it.
  const check = cart.locator('[data-testid=pos-cart-tab-check]');
  await check.click(TAP);
  await expect(check, `«Check» at ${where}`).toHaveAttribute('aria-selected', 'true');
  await settled(page);
  await scrolledToTop(cart);
  if (size.kind === 'roomy') await keepsItsLayout(cart, `${where}, «Check»`);
  await aWholeLine(cart, `${where}, «Check»`);
  await expectWhole(cart.locator('[data-testid=pos-charge]'), 'Charge', `${where}, «Check»`);
  await capture(page, `${KEY}-${where.replaceAll(' ', '-')}-check`);

  if (size.kind === 'drawer') {
    await cart.locator('[data-testid=pos-cart-close]').click(TAP);
    await expect(shown(page).locator('[data-testid=pos-cart-drawer]')).toBeHidden();
  }
}

for (const strip of [false, true]) {
  for (const { name, lang, locale } of TILL_LANGUAGES) {
    test.describe(`SALE-F20: in ${name}, ${strip ? 'under the red strip' : 'without the strip'}, a low side column shows a whole line of the check`, () => {
      // The dish on the check, still to be sent: «Current order» has its line and its send bar.
      const till = tillUnderStrip({ strip, parked: PARKED, locale, lang }, async (page) => {
        await shown(page).locator(`[data-testid=pos-product-${dish.id}]`).click(TAP);
        await expect(shown(page).locator('[data-testid^=pos-line-]').filter({ hasText: dish.name }).first()).toBeAttached();
      });

      for (const size of SIZES.filter((s) => s.strip === strip)) {
        test(`${size.label} (${size.kind})`, async () => {
          await readsALine(till(), size, lang);
        });
      }
    });
  }
}

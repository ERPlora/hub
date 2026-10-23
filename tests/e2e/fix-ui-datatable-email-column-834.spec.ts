// flow: UI DataTable anchos de columna — FIX-UI-DATATABLE-EMAIL-COLUMN-834 (seen by the reviewer of APP-CART_CHECKOUT,
// hub#110): at 834×1112, in Cart & Checkout › Orders, the Email column cut «ana@example.c…» while the row had room to
// spare (Payment almost empty, a gap before Total). Every column without its own width took the same share of the row
// (`minmax(5.5rem, 1fr)`), whatever it holds: a long email got what «—» got. As in the market (Shopify, Odoo, Square)
// a column fits its content and only a table really out of room cuts with «…»: the widest text gives up first, the
// short columns keep theirs, and the ladder of W-19 (low columns out, actions folded, cards) is the one of before
// (erplora-old/hub#2717 was the same cut in Staff, at 820px). The header still lines up with its cells.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { cleanUp, code, orderFrom, signedIn, VIEWPORTS } from './cart-checkout-helpers';
import { record, shot, shown, untilStill } from './helpers';

const KEY = 'FIX-UI-DATATABLE-EMAIL-COLUMN-834';
const TABLE = 'cart-checkout-orders';
// Each is cut by an equal share of the row at 834px (117px) and fits whole beside the other four columns with room to
// spare, whatever the system font (ana.garcia.lopez@example.com sits within a pixel of the room there is).
const EMAILS = ['ana.garcia@example.com', 'bea@example.com', 'carlos.ruiz@example.com'];
/** An address no list at 834px holds whole next to its other four columns. */
const TOO_LONG = 'fix.ui.datatable.email.column.834.a.really.long.address@example.com';

test.beforeEach(cleanUp);
test.afterAll(cleanUp);

/** What the list paints, column by column: its width, how far its cells drift from its header (px), the texts
 *  it cuts (header label included) and the room its cells leave beside their text (px; negative = cut). */
interface Column {
  label: string;
  width: number;
  drift: number;
  cut: string[];
  room: number;
}
interface Painted {
  /** px the list scrolls sideways (0 = none). */
  overflow: number;
  columns: Column[];
}

async function painted(table: Locator): Promise<Painted> {
  return table.evaluate((root) => {
    const scroll = root.querySelector('.data-table__scroll') as HTMLElement;
    const head = root.querySelector('.data-table__row--head') as HTMLElement;
    const headers = [...head.querySelectorAll<HTMLElement>(':scope > [role=columnheader]')];
    const rows = [...root.querySelectorAll<HTMLElement>('.data-table__row--data')];
    const columns = headers.map((header, index) => {
      const own = header.getBoundingClientRect();
      const cut: string[] = [];
      const label = header.querySelector<HTMLElement>(':scope > span');
      if (label && label.scrollWidth > label.clientWidth) cut.push(`header ${label.textContent?.trim()}`);
      let drift = 0;
      let room = Infinity;
      for (const row of rows) {
        const cell = row.querySelectorAll<HTMLElement>(':scope > [role=cell]')[index];
        const box = cell.getBoundingClientRect();
        drift = Math.max(drift, Math.abs(box.left - own.left), Math.abs(box.right - own.right));
        for (const span of cell.querySelectorAll<HTMLElement>(':scope > span')) {
          if (span.scrollWidth > span.clientWidth) cut.push(span.textContent?.trim() ?? '');
          const style = getComputedStyle(cell);
          const inside = cell.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
          room = Math.min(room, inside - span.scrollWidth);
        }
      }
      return {
        label: header.textContent?.trim() ?? '',
        width: Math.round(own.width * 10) / 10,
        drift: Math.round(drift * 10) / 10,
        cut,
        room: Number.isFinite(room) ? Math.round(room) : 0,
      };
    });
    return { overflow: scroll.scrollWidth - scroll.clientWidth, columns };
  });
}

/** `painted` once two readings in a row agree: the list settles on its own resize in a few frames. */
async function steady(table: Locator): Promise<Painted> {
  let seen: Painted | undefined;
  let last = '';
  await expect
    .poll(async () => {
      seen = await painted(table);
      const now = JSON.stringify(seen);
      const same = now === last;
      last = now;
      return same;
    })
    .toBe(true);
  return seen!;
}

/** The orders list once it shows every seeded email and its ladder (W-19) stands still. */
async function listWith(page: Page, emails: string[]): Promise<Locator> {
  await page.goto(`/cart_checkout/orders`);
  const view = shown(page);
  for (const email of emails) await expect(view.locator(`[data-testid=${TABLE}-row]`, { hasText: email }).first()).toBeVisible();
  await untilStill(page);
  return view.locator('.data-table').first();
}

for (const [label, viewport] of [
  ['834', VIEWPORTS.tablet],
  ['1440', VIEWPORTS.desktop],
] as const) {
  test(`UI DataTable anchos de columna at ${label}: with room in the row, no email is cut and the header lines up`, async ({ browser }) => {
    const { context, page } = await signedIn(browser, '/cart_checkout/orders', viewport);
    try {
      for (const [index, email] of EMAILS.entries()) await orderFrom(context, code(`email-${label}-${index}`), { email });
      const table = await listWith(page, EMAILS);
      await expect(table.locator('.data-table__row--head')).toBeVisible();
      const seen = await steady(table);
      record(`${KEY}-${label}`, seen);
      const email = seen.columns.find((c) => c.label === 'Email');
      expect(email, 'the Email column is painted').toBeDefined();
      expect(email!.cut, `at ${label} every email is whole: ${JSON.stringify(seen.columns)}`).toEqual([]);
      for (const column of seen.columns) {
        expect(column.cut, `at ${label} «${column.label}» cuts nothing`).toEqual([]);
        expect(column.drift, `at ${label} «${column.label}» lines up with its cells`).toBeLessThanOrEqual(1);
      }
      expect(seen.overflow, `at ${label} nothing scrolls sideways`).toBeLessThanOrEqual(0);
      await page.screenshot({ path: shot(`${KEY}-${label}`) });
    } finally {
      await context.close();
    }
  });
}

test('UI DataTable anchos de columna at 834: out of room, the longest email gives up its width with «…» and its title', async ({ browser }) => {
  const { context, page } = await signedIn(browser, '/cart_checkout/orders', VIEWPORTS.tablet);
  try {
    const emails = [...EMAILS, TOO_LONG];
    for (const [index, email] of emails.entries()) await orderFrom(context, code(`tight-${index}`), { email });
    const table = await listWith(page, emails);
    const seen = await steady(table);
    record(`${KEY}-834-tight`, seen);
    const cut = table.locator('.data-table__row--data [role=cell] > span', { hasText: TOO_LONG });
    await expect(cut).toHaveAttribute('title', TOO_LONG);
    await expect(cut).toHaveCSS('text-overflow', 'ellipsis');
    const email = seen.columns.find((c) => c.label === 'Email')!;
    expect(email.cut, 'only the address that cannot fit is cut').toEqual([TOO_LONG]);
    // The columns beside it keep their text: what is cut is the widest one, not a share of every column.
    for (const column of seen.columns.filter((c) => c.label !== 'Email')) {
      expect(column.cut, `«${column.label}» keeps its text`).toEqual([]);
      expect(column.drift, `«${column.label}» lines up with its cells`).toBeLessThanOrEqual(1);
    }
    // The ladder of W-19 is untouched: still the list, its row actions out, nothing hidden sideways.
    await expect(table.locator('.data-table__row--data').first()).toBeVisible();
    await expect(table.locator('.data-table__card')).toHaveCount(0);
    expect(seen.overflow).toBeLessThanOrEqual(0);
  } finally {
    await context.close();
  }
});

test('UI DataTable anchos de columna at 390: a phone keeps its cards', async ({ browser }) => {
  const { context, page } = await signedIn(browser, '/cart_checkout/orders', VIEWPORTS.phone);
  try {
    for (const [index, email] of EMAILS.entries()) await orderFrom(context, code(`phone-${index}`), { email });
    await page.goto(`/cart_checkout/orders`);
    const view = shown(page);
    for (const email of EMAILS) await expect(view.locator(`[data-testid=${TABLE}-row]`, { hasText: email }).first()).toBeVisible();
    await untilStill(page);
    const table = view.locator('.data-table').first();
    await expect(table.locator('.data-table__card').first()).toBeVisible();
    await expect(table.locator('.data-table__row--data')).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
    await page.screenshot({ path: shot(`${KEY}-390`) });
  } finally {
    await context.close();
  }
});

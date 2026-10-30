// Shared steps of the inventory specs (apps/inventory/WORKBOOK.md) against hub `a` and the real Taxes
// app (no doubles): its data are named `E2E …` / `E2E-…` / `e2e …` so `cleanInventory()` (in each
// spec's `afterAll`) removes exactly them from the hub's database, with their movements and links.
import { type BrowserContext, expect, type Locator, type Page } from '@playwright/test';

import { A, api, capture, psql, shot, shown } from './helpers';

export const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
] as const;

/** A tax category of Taxes' Spanish factory catalogue. */
export const GENERIC = 'product.generic';

/** A unique suffix for this run's data. */
export const stamp = (): string => Date.now().toString(36).toUpperCase();

export interface Product {
  id: string;
  sku: string;
  name: string;
  stock: string;
  tax_category_key: string | null;
  needs_tax_setup: boolean;
  is_active: boolean;
  is_sold_out: boolean;
  category_ids: string[];
}

/** Deletes every `E2E` product, movement, category, link and learned text and `e2e.inv_*` tax category. */
export function cleanInventory(): void {
  const products = `select id from inventory_product where sku like 'E2E-%'`;
  const categories = `select id from inventory_category where name like 'E2E %'`;
  psql(`delete from inventory_stockmovement where product_id in (${products})`);
  psql(`delete from inventory_productcategory where product_id in (${products}) or category_id in (${categories})`);
  psql(`delete from inventory_product where sku like 'E2E-%'`);
  psql(`delete from inventory_category where name like 'E2E %'`);
  psql(`delete from tax_taxalias where alias like 'e2e %'`);
  psql(
    `delete from tax_taxcategory where key like 'e2e.inv%' and id not in (select tax_category_id from inventory_product where tax_category_id is not null) and id not in (select tax_category_id from inventory_category where tax_category_id is not null)`,
  );
}

/** A product made through the API (setup, never the check). */
export async function createProduct(context: BrowserContext, fields: Record<string, unknown>): Promise<Product> {
  const res = await api<Product>(context, A, 'POST', '/inventory/products', { price: 100, tax_category_key: GENERIC, ...fields });
  expect(res.status, `create ${String(fields.sku)}`).toBe(201);
  return res.data;
}

export async function productBySku(context: BrowserContext, sku: string): Promise<Product> {
  const res = await api<Product>(context, A, 'GET', `/inventory/products/detail?product=${encodeURIComponent(sku)}`);
  expect(res.status, `detail ${sku}`).toBe(200);
  return res.data;
}

/** Opens an `ion-select` and picks the option whose text matches (popover, or alert + OK for a multiple one). */
export async function pick(page: Page, select: Locator, text: string | RegExp): Promise<void> {
  await select.click();
  const overlay = page.locator('ion-popover:visible, ion-alert:visible').last();
  await overlay.waitFor({ state: 'visible' });
  const isAlert = await overlay.evaluate((el) => el.tagName === 'ION-ALERT');
  if (isAlert) {
    await overlay.locator('button.alert-tappable, button.alert-radio-button, button.alert-checkbox-button').filter({ hasText: text }).first().click();
    await overlay.locator('.alert-button-group button').last().click();
  } else {
    await overlay.locator('ion-radio, ion-item, ion-checkbox').filter({ hasText: text }).first().click();
  }
  await expect(overlay).toBeHidden();
}

/** Picks, in a `Combo` (a field that searches the server: the tax category, the product's categories),
 *  the option whose text matches, after typing `query`; choosing closes its list. */
export async function pickCombo(page: Page, field: Locator, query: string, text: string | RegExp): Promise<void> {
  const testid = await field.getAttribute('data-testid');
  const input = field.locator('input');
  await input.click();
  await input.fill(query);
  const options = page.locator(`[data-testid^="${testid}-option-"]`);
  await options.filter({ hasText: text }).first().click();
  await expect(options).toHaveCount(0);
}

/** The dialog of a FormModal (Ionic moves it to ion-app). */
export const dialog = (page: Page, testid: string): Locator => page.locator(`ion-modal[data-testid=${testid}]`);

/** Types into an Ionic field. */
export async function fill(scope: Locator, testid: string, value: string): Promise<void> {
  const input = scope.locator(`[data-testid=${testid}] input, [data-testid=${testid}] textarea`).first();
  await input.fill(value);
  await input.blur();
}

export const productsReady = (page: Page) =>
  shown(page).locator('[data-testid=inventory-products-row], [data-testid=inventory-products-empty]').first().waitFor({ state: 'visible' });

/** The row (or card) of the product with this SKU on the products list shown. */
export const productRow = (page: Page, sku: string): Locator =>
  shown(page).locator('[data-testid=inventory-products-row]', { hasText: sku });

/** Narrows the products list to `text` with its search box. */
export async function searchProducts(page: Page, text: string): Promise<void> {
  await shown(page).locator('[data-testid=inventory-products-search] input').fill(text);
}

/** Screenshots of the page shown at the three viewports, then back to `restore`. */
export async function shoot(page: Page, name: string, restore = { width: 1280, height: 860 }): Promise<string[]> {
  const files: string[] = [];
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    // The table refits to its box: `capture` waits until the page is painted at this size.
    await capture(page, `${name}-${viewport.label}`);
    files.push(shot(`${name}-${viewport.label}`));
  }
  await page.setViewportSize(restore);
  return files;
}

/** The screenshots of a flow of the migration (APP-INVENTORY): `APP-INVENTORY-<key>-<390|834|1440>`. */
export async function shootFlow(page: Page, key: string, restore = { width: 1280, height: 860 }): Promise<string[]> {
  return shoot(page, `APP-INVENTORY-${key}`, restore);
}

/** Runs a row action of the products list: its inline button, or the row's «⋮» menu when it folded there. */
export async function rowAction(page: Page, id: string, action: string): Promise<void> {
  const hook = `inventory-products-row-${id}-${action}`;
  const inline = shown(page).locator(`[data-testid=${hook}]`).first();
  const menu = shown(page).locator(`[data-testid=inventory-products-row-${id}-menu]`).first();
  // Right after a search the row may not be painted yet: choosing then took the menu and waited there for an
  // inline action until the test's time ran out. The row's buttons paint together, so wait for either.
  await expect(inline.or(menu).first()).toBeVisible();
  if (await inline.isVisible()) {
    await inline.click();
    return;
  }
  await menu.click();
  await page.locator(`ion-popover [data-testid=${hook}]`).click();
}

/** How a «Not configured» chip sits in its box (`within`: the table cell, the card's value or the form's field):
 *  what is wrong with it (none = its icon in sight and its text on one line, whole or ending in «…»; `whole`: it
 *  has to be whole; `titled`: its `title` is its whole text) and its measurements for the report. A part is in
 *  sight when it lies inside the box and inside every box between them that clips (`overflow` not `visible`, the
 *  chip itself included). */
export async function chipFit(
  chip: Locator,
  options: { within: string; whole?: boolean; titled?: boolean },
): Promise<{ problems: string[]; metrics: Record<string, unknown> }> {
  return chip.evaluate((el, { within: selector, whole: mustFit, titled }) => {
    const px = (n: number) => Math.round(n * 10) / 10;
    const box = el.closest(selector);
    if (!box) return { problems: [`no ${selector} around the chip`], metrics: {} };
    const sight = (node: Element) => {
      const r = box.getBoundingClientRect();
      const span = { left: r.left, right: r.right };
      for (let up = node.parentElement; up && up !== box; up = up.parentElement) {
        if (getComputedStyle(up).overflowX === 'visible') continue;
        const c = up.getBoundingClientRect();
        span.left = Math.max(span.left, c.left);
        span.right = Math.min(span.right, c.right);
      }
      return span;
    };
    const inSight = (node: Element) => {
      const r = node.getBoundingClientRect();
      const s = sight(node);
      return { ok: r.width >= 1 && r.left >= s.left - 0.5 && r.right <= s.right + 0.5, at: `${px(r.left)}–${px(r.right)}`, sight: `${px(s.left)}–${px(s.right)}` };
    };
    const problems: string[] = [];
    const chipAt = inSight(el);
    if (!chipAt.ok) problems.push(`the chip (${chipAt.at}) sticks out of its box (${chipAt.sight})`);
    const icon = el.querySelector('ion-icon');
    const iconAt = icon ? inSight(icon) : null;
    if (!icon || !iconAt || getComputedStyle(icon).visibility === 'hidden') problems.push('the chip has no icon');
    else if (!iconAt.ok) problems.push(`its icon (${iconAt.at}) is out of sight (${iconAt.sight})`);
    // The box that paints the text: the nearest ancestor of its text that is not inline.
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let text: Node | null = walker.nextNode();
    while (text && !text.textContent?.trim()) text = walker.nextNode();
    let painter: Element | null = text?.parentElement ?? null;
    while (painter && painter !== el && getComputedStyle(painter).display === 'inline') painter = painter.parentElement;
    const whole = (el.querySelector('ion-label')?.textContent ?? '').trim();
    if (!text || !painter || !whole) return { problems: [...problems, 'the chip has no text'], metrics: {} };
    const style = getComputedStyle(painter);
    const fits = painter.scrollWidth <= painter.clientWidth;
    const ellipsis = style.textOverflow === 'ellipsis' && style.overflowX === 'hidden' && style.whiteSpace === 'nowrap';
    if (mustFit && !fits) problems.push(`its text is not whole though the row has room (${painter.scrollWidth} > ${painter.clientWidth})`);
    else if (!fits && !ellipsis) {
      problems.push(
        `its text is cut with no «…» (${painter.scrollWidth} > ${painter.clientWidth}; text-overflow ${style.textOverflow}, overflow ${style.overflowX}, white-space ${style.whiteSpace})`,
      );
    }
    // One line: a chip that wraps its text is not whole on its row.
    const range = document.createRange();
    range.selectNodeContents(text);
    const lines = new Set([...range.getClientRects()].filter((r) => r.width > 0).map((r) => Math.round(r.top))).size;
    if (lines > 1) problems.push(`its text wraps to ${lines} lines`);
    const textAt = inSight(painter);
    if (!textAt.ok) problems.push(`its text (${textAt.at}) is cut by a box around it (${textAt.sight})`);
    const title = el.getAttribute('title');
    if (titled && title !== whole) problems.push(`its title «${title}» is not its whole text «${whole}»`);
    return {
      problems,
      metrics: {
        box: sight(el),
        chip: chipAt.at,
        icon: iconAt?.at,
        text: { at: textAt.at, scrollWidth: painter.scrollWidth, clientWidth: painter.clientWidth, fits, ellipsis, lines },
        title,
        whole,
      },
    };
  }, options);
}

/** A measurement's problems once the layout settles (`[]` = all is well): the table refits to its box after a resize
 *  (columns, cards) and a step on its way may look right, so a measurement counts only when the next one finds it
 *  unchanged. Soft: one run says what is wrong at every width. */
export async function settled<T extends { problems: string[] }>(measure: () => Promise<T>, message: string, empty: T): Promise<T> {
  let last = '';
  let fit = empty;
  await expect
    .configure({ soft: true })
    .poll(
      async () => {
        fit = await measure();
        const now = JSON.stringify(fit);
        const same = now === last;
        last = now;
        return same ? fit.problems : ['settling'];
      },
      { message },
    )
    .toEqual([]);
  return fit;
}

/** The chip's problems once the layout settles (`[]` = it fits; see `settled`). */
export const settledChipFit = (
  chip: Locator,
  options: Parameters<typeof chipFit>[1],
  message: string,
): Promise<Awaited<ReturnType<typeof chipFit>>> => settled(() => chipFit(chip, options), message, { problems: [], metrics: {} });

/** FIX-UI-DATATABLE-CELL-NO-WRAP-SQUEEZES-CHIP-BESIDE-BADGE - How a «Not configured» chip and the badge painted after
 *  it (`badge`, a selector inside the same box) share their box (`within`, as `chipFit`): what is wrong with them (none
 *  = the chip is whole or as wide as its box, never squeezed by the badge beside it; the badge whole and inside the box;
 *  neither over the other) and their measurements for the report. */
export async function chipBesideBadge(
  chip: Locator,
  options: { within: string; badge: string },
): Promise<{ problems: string[]; metrics: Record<string, unknown> }> {
  return chip.evaluate((el, { within: selector, badge: badgeSelector }) => {
    const px = (n: number) => Math.round(n * 10) / 10;
    const box = el.closest(selector);
    if (!box) return { problems: [`no ${selector} around the chip`], metrics: {} };
    const badge = box.querySelector(badgeSelector);
    if (!badge) return { problems: [`no ${badgeSelector} beside the chip`], metrics: {} };
    const problems: string[] = [];
    const boxStyle = getComputedStyle(box);
    const room = box.clientWidth - (parseFloat(boxStyle.paddingLeft) || 0) - (parseFloat(boxStyle.paddingRight) || 0);
    // The chip clips its text: its `scrollWidth` is its whole width while it is cut.
    const chipStyle = getComputedStyle(el);
    const borders = (parseFloat(chipStyle.borderLeftWidth) || 0) + (parseFloat(chipStyle.borderRightWidth) || 0);
    const natural = Math.max(el.scrollWidth, el.clientWidth) + borders;
    const chip = el.getBoundingClientRect();
    if (chip.width < Math.min(natural, room) - 1) {
      problems.push(`the chip is squeezed to ${px(chip.width)}px though it needs ${px(natural)}px and its box gives ${px(room)}px`);
    }
    const tag = badge.getBoundingClientRect();
    const frame = box.getBoundingClientRect();
    if (tag.width < 1) problems.push('the badge is not painted');
    else if (tag.left < frame.left - 0.5 || tag.right > frame.right + 0.5) {
      problems.push(`the badge (${px(tag.left)}–${px(tag.right)}) sticks out of its box (${px(frame.left)}–${px(frame.right)})`);
    }
    if (badge.scrollWidth > badge.clientWidth + 0.5) problems.push(`the badge's text is cut (${badge.scrollWidth} > ${badge.clientWidth})`);
    const across = Math.min(chip.right, tag.right) - Math.max(chip.left, tag.left);
    const down = Math.min(chip.bottom, tag.bottom) - Math.max(chip.top, tag.top);
    if (across > 0.5 && down > 0.5) problems.push(`the badge lies over the chip (${px(across)}×${px(down)}px)`);
    return {
      problems,
      metrics: {
        room: px(room),
        chip: { width: px(chip.width), natural: px(natural), top: px(chip.top) },
        badge: { left: px(tag.left), right: px(tag.right), top: px(tag.top) },
        under: tag.top >= chip.bottom - 0.5,
      },
    };
  }, options);
}

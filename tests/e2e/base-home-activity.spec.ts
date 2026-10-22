// «Activity» on the Home (BASE-F09) against the real Sales: a sale charged through its API shows up live in
// the table at `/#actividad` with its number, amount in euros and status, and its date and time are read whole
// in the three viewports (hub#2637: at about 820 px the old hub's «Date» column cut the time off).
// flow: BASE-F09
import { expect, type Locator, type Page, test } from '@playwright/test';

import { A, login, shot, shown, untilStill } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { chargeByApi, cleanSales, stamp } from './sale-helpers';

const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

const RUN = stamp();
let coffee: Product;

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/');
  coffee = await createProduct(context, { name: `E2E Home coffee ${RUN}`, sku: `E2E-HOME-${RUN}`, price: 150, tax_category_key: 'restaurant.drink' });
  await context.close();
});

test.afterAll(() => {
  cleanSales();
  cleanInventory();
});

/** What cuts `el`'s text: the boxes that clip it, up to its table cell (or card field). Empty = whole. */
function cuts(el: Locator): Promise<string[]> {
  return el.evaluate((node) => {
    const range = document.createRange();
    range.selectNodeContents(node);
    const text = range.getBoundingClientRect();
    const found: string[] = [];
    const cell = node.closest('.data-table__cell, .data-table__field-value') ?? node;
    for (let at: Element | null = node as Element; at; at = at.parentElement) {
      const style = getComputedStyle(at);
      const box = at.getBoundingClientRect();
      const clips = style.overflowX !== 'visible' || style.overflowY !== 'visible' || at === cell;
      if (clips && (text.left < box.left - 0.5 || text.right > box.right + 0.5)) {
        found.push(`text ${Math.round(text.left)}–${Math.round(text.right)} cut by ${at.tagName.toLowerCase()} ${Math.round(box.left)}–${Math.round(box.right)}`);
      }
      if (at === cell) break;
    }
    return found;
  });
}

type Box = { name: string; left: number; right: number; top: number; bottom: number };

/** The toolbar row of «Activity» and each control painted in it (`display: none` ones left out). */
function toolbarBoxes(page: Page): Promise<{ bar: Box; controls: Box[] }> {
  const bar = shown(page)
    .locator('.data-table__bar-main')
    .filter({ has: page.locator('[data-testid=home-activity-search]') });
  return bar.evaluate((row) => {
    const box = (el: Element, name: string) => {
      const r = el.getBoundingClientRect();
      return { name, left: r.left, right: r.right, top: r.top, bottom: r.bottom };
    };
    const style = getComputedStyle(row);
    const inner = row.getBoundingClientRect();
    const controls = [...row.children]
      .filter((el) => getComputedStyle(el).display !== 'none' && el.getBoundingClientRect().width > 0)
      .map((el) => box(el, el.getAttribute('data-testid') ?? el.className.toString().split(' ')[0]));
    return {
      bar: {
        name: 'bar',
        left: inner.left + parseFloat(style.paddingLeft),
        right: inner.right - parseFloat(style.paddingRight),
        top: inner.top,
        bottom: inner.bottom,
      },
      controls,
    };
  });
}

async function rowOf(page: Page, id: string): Promise<Locator> {
  const row = shown(page).locator(`[data-testid=home-activity-row][data-id="${id}"]`);
  await expect(row).toBeVisible();
  return row;
}

test('BASE-F09 — the address `/#actividad` opens «Activity» on a full load too (a link, a bookmark, a reload)', async ({ page }) => {
  await login(page, A, '/');
  await page.goto('about:blank');
  await page.goto(`${A}/#actividad`);
  await expect(shown(page).locator('[data-testid="tab-activity"]')).toHaveClass(/segment-button-checked/);
  await expect(shown(page).locator('[data-testid=home-activity-search]')).toBeVisible();
  await page.reload();
  await expect(shown(page).locator('[data-testid="tab-activity"]')).toHaveClass(/segment-button-checked/);
  await expect(page).toHaveURL(`${A}/#actividad`);
});

test('BASE-F09 — a sale shows up live in «Activity», its date and time whole at 390, 834 and 1440', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/');
  await page.goto(`${A}/#actividad`);
  await expect(shown(page).locator('[data-testid=home-activity-search]')).toBeVisible();

  // Charged elsewhere (the API, as another till would): the open table gets it without a reload.
  const sale = await chargeByApi(context, { lines: [{ product: coffee.sku }], payments: [{ method: 'card' }] });
  const row = await rowOf(page, sale.id);
  await expect(row).toContainText(sale.number);
  await expect(row).toContainText(/1[.,]50/);

  for (const vp of [VIEWPORTS[1], VIEWPORTS[0], VIEWPORTS[2]]) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto(`${A}/#actividad`);
    const seen = await rowOf(page, sale.id);
    const date = seen.locator('.data-table__cell, .data-table__field-value').first();
    // The date carries its time («22/10/2026, 9:30»), and nothing clips it.
    await expect(date).toHaveText(/\d{1,2}:\d{2}/);
    await expect.poll(() => cuts(date), `date at ${vp.label}`).toEqual([]);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `no sideways scroll at ${vp.label}`).toBeLessThanOrEqual(0);
    // The list/cards switch slides its indicator when the width changes the view: capture it settled.
    await untilStill(page);
    await page.screenshot({ path: shot(`APP-BASE-1-BASE-F09-sale-${vp.label}`) });
  }
});

/** The fleet's tablet (820) beside the old hub's reference sizes. */
const TOOLBAR_VIEWPORTS = [...VIEWPORTS, { label: '820', width: 820, height: 1180 }];

test('BASE-F09 — the toolbar of «Activity» is one row from 820 to 1440, as in the old hub, and spills nowhere', async ({ page }) => {
  await login(page, A, '/');
  for (const vp of TOOLBAR_VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto(`${A}/#actividad`);
    await expect(shown(page).locator('[data-testid=home-activity-filters-toggle]')).toBeVisible();
    const { bar, controls } = await toolbarBoxes(page);
    for (const control of controls) {
      expect(control.left, `${control.name} inside the bar at ${vp.label}`).toBeGreaterThanOrEqual(bar.left - 0.5);
      expect(control.right, `${control.name} inside the bar at ${vp.label}`).toBeLessThanOrEqual(bar.right + 0.5);
    }
    if (vp.label === '390') continue; // On a phone the search takes its own line (the old hub's too).
    // docs/reference/old-hub/dashboard-activity-834.png: search, columns, rows per page, list/cards and the
    // funnel on one line. Every control shares the search's line.
    const search = controls.find((c) => c.name === 'data-table__search');
    expect(search, `the search at ${vp.label}`).toBeDefined();
    for (const control of controls) {
      expect(control.top, `${control.name} on the search's line at ${vp.label}`).toBeLessThan(search!.bottom);
    }
  }
});

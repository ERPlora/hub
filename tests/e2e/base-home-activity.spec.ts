// «Activity» on the Home (BASE-G129) against the real Sales: a sale charged through its API shows up live in
// the table at `/#actividad` with its number, amount in euros and status, and its date and time are read whole
// in the three viewports (hub#2637: at about 820 px the old hub's «Date» column cut the time off).
// flow: BASE-G129
import { expect, type Locator, type Page, test } from '@playwright/test';

import { A, login, shot, shown } from './helpers';
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

async function rowOf(page: Page, id: string): Promise<Locator> {
  const row = shown(page).locator(`[data-testid=home-activity-row][data-id="${id}"]`);
  await expect(row).toBeVisible();
  return row;
}

test('BASE-G129 — a sale shows up live in «Activity», its date and time whole at 390, 834 and 1440', async ({ page, context }) => {
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
    await page.screenshot({ path: shot(`APP-BASE-1-BASE-G129-sale-${vp.label}`) });
  }
});

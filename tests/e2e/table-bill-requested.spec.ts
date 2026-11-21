// Tables in Chrome (apps/table/WORKBOOK.md, TABLE-F34), with the real Sales and Inventory apps: a waiter prints the
// bill of an occupied table in the till, and the floor plan another device keeps open marks that table «Bill
// requested» without a reload (its status in words and its own colour, its time, guests and bill still there), while
// the other occupied table stays «Occupied». Charging that check whole frees the table and the mark goes with it. The
// plan in three viewports. What the run creates lives in a zone named «E2E Tbr <stamp>…» and its checks; `afterAll`
// removes all of it, sales included.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, shot, shown } from './helpers';
import { cleanInventory, createProduct } from './inventory-helpers';
import { chargeByCard } from './sale-charge-helpers';
import { cleanRoom, cleanSales } from './sale-helpers';
import { ownerPage, post } from './service-helpers';

const TAG = 'E2E Tbr ';
const STAMP = Date.now().toString(36).toUpperCase();
const ROOM = `${TAG}${STAMP} Room`;
const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1194 },
  { label: '1440', width: 1440, height: 900 },
];

function cleanUp(): void {
  cleanSales();
  cleanRoom(TAG);
  cleanInventory();
}

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

const tile = (page: Page, id: string) => shown(page).locator(`[data-testid=table-floor-tile-${id}]`);

/** Seats three at a new table `number` of the room and puts one coffee on its check; returns the table and its check. */
async function seatedWithCoffee(context: BrowserContext, zone: string, number: string, coffee: string): Promise<{ table: string; order: string }> {
  const table = await post<{ id: string }>(context, '/table/tables', { zone_id: zone, number, capacity: 4 });
  const { order_id: order } = await post<{ order_id: string }>(context, '/table/sessions/open', { table_id: table.id, guests_count: 3 });
  const added = await api(context, A, 'POST', '/sale/orders/add_line', { order_id: order, product_id: coffee, quantity: '1' });
  expect(added.status, JSON.stringify(added.data)).toBe(200);
  return { table: table.id, order };
}

test('A table whose bill is printed shows «Bill requested» on the plan until its check is charged whole', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/table/floor-plan');
  const till = await ownerPage(browser, '/sale/pos');
  try {
    const zone = await post<{ id: string }>(context, '/table/zones', { name: ROOM });
    const coffee = await createProduct(context, { name: `E2E Tbr coffee ${STAMP}`, sku: `E2E-TBR-${STAMP}`, price: 150 });
    const methods = await api<{ rows: { id: string; type: string }[] }>(context, A, 'GET', '/sale/payment_methods');
    const card = methods.data.rows.find((row) => row.type === 'card')!.id;
    const asked = await seatedWithCoffee(context, zone.id, '1', coffee.id);
    const other = await seatedWithCoffee(context, zone.id, '2', coffee.id);
    await page.reload();
    await shown(page).locator(`[data-testid=table-floor-zone-tab-${zone.id}]`).click();
    await expect(tile(page, asked.table)).toContainText('Occupied');
    await expect(tile(page, asked.table)).not.toHaveAttribute('data-bill');

    // The till prints the table's bill: the browser's dialog stands in for a receipt printer when there is none.
    await till.page.goto(`${A}/sale/pos?order=${asked.order}`);
    await expect(shown(till.page).locator('[data-testid=pos-check-title]')).toHaveValue('Table 1');
    await till.page.evaluate(() => {
      window.print = () => {};
    });
    await shown(till.page).locator('[data-testid=pos-prebill]').click();
    const bill = till.page.locator('ion-modal[data-testid=pos-prebill]');
    await expect(bill.locator('[data-testid=pos-prebill-print]')).toBeEnabled();
    await bill.locator('[data-testid=pos-prebill-print]').click();
    await bill.locator('[data-testid=pos-prebill-close]').click();
    await expect(bill).toBeHidden();

    // The plan, open on another device, marks it at once and keeps its time, guests and bill; the other stays occupied.
    await expect(tile(page, asked.table)).toHaveAttribute('data-bill', 'requested', { timeout: 15_000 });
    await expect(tile(page, asked.table)).toContainText('Bill requested · 3/4 pax');
    await expect(tile(page, asked.table)).toContainText('€1.50');
    await expect(tile(page, asked.table).getByRole('button')).toHaveAccessibleName(/· Bill requested · 3 guests · \d+ min · Bill €1\.50/);
    await expect(tile(page, other.table)).toContainText('Occupied · 3/4 pax');
    await expect(tile(page, other.table)).not.toHaveAttribute('data-bill');
    await expect(shown(page).locator('[data-testid=table-floor-summary] [data-stat="occupied"]')).toContainText('2');
    for (const viewport of VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await expect(tile(page, asked.table)).toHaveAttribute('data-bill', 'requested');
      await expect(tile(page, asked.table)).toContainText('Bill requested');
      await page.screenshot({ path: shot(`table-floor-bill-requested-${viewport.label}`), fullPage: true });
    }
    await page.setViewportSize({ width: 1280, height: 860 });

    // Charged whole in the till, the table frees itself and the mark goes with its check.
    await chargeByCard(till.page, card, /1[.,]50/);
    await expect(tile(page, asked.table)).toContainText('Available', { timeout: 15_000 });
    await expect(tile(page, asked.table)).not.toHaveAttribute('data-bill');
    await expect(tile(page, other.table)).toContainText('Occupied');
  } finally {
    await till.context.close();
    await context.close();
  }
});

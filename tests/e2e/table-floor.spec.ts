// Tables in Chrome (apps/table/WORKBOOK.md), with the real Sales, Inventory and Customers apps: the owner
// draws a zone and its tables on the floor plan (Edit plan: «+», a drag that stays after a reload, «Edit
// table»), serves it (Service: seats a party, transfers it, merges two tables, charges in Sales — the plan
// frees the table by itself, live — and closes an empty table), and reads the checks in Sessions, the
// zones in Zones and the tables in Tables. Every screen in three viewports. What a run creates lives in a
// zone named «E2E Tbl <stamp>…» and its checks; `afterAll` removes all of it, sales included.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, psql, shot, shown } from './helpers';
import { cleanInventory, createProduct } from './inventory-helpers';
import { chargeByApi, cleanSales } from './sale-helpers';
import { ownerPage } from './service-helpers';

const STAMP = Date.now().toString(36).toUpperCase();
const ZONE = `E2E Tbl ${STAMP} Terrace`;
const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1194 },
  { label: '1440', width: 1440, height: 900 },
];

interface Check {
  id: string;
  order_id: string | null;
}
interface TableRow {
  id: string;
  number: string;
  status: string;
  position_x: number;
  position_y: number;
  shape: string;
  checks: Check[];
}

/** Every check of Sales a run's tables held: the empty ones (voided on close or merged) carry no E2E line. */
const orders = new Set<string>();

async function tableByNumber(context: BrowserContext, number: string): Promise<TableRow> {
  const zone = encodeURIComponent(ZONE);
  const res = await api<TableRow>(context, A, 'GET', `/table/tables/detail?table=${number}&zone=${zone}`);
  expect(res.status, `table ${number}`).toBe(200);
  for (const check of res.data.checks) if (check.order_id) orders.add(check.order_id);
  return res.data;
}

function cleanTables(): void {
  const zones = "select id from table_zone where name like 'E2E Tbl %'";
  const tables = `select id from table_table where zone_id in (${zones})`;
  const sessions = `select id from table_tablesession where table_id in (${tables})`;
  const known = [...orders].map((id) => `'${id}'`).join(',') || "'00000000-0000-0000-0000-000000000000'";
  const ownOrders = `select order_id from table_tablesession where table_id in (${tables}) and order_id is not null union select id from sale_order where id in (${known})`;
  psql(
    [
      `create temp table e2e_tbl_orders as ${ownOrders}`,
      'delete from customer_orderlink where order_id in (select order_id from e2e_tbl_orders)',
      "delete from sale_orderline where order_id in (select order_id from e2e_tbl_orders) and order_id not in (select order_id from sale_orderline where sku like 'E2E-%')",
      "delete from sale_order where id in (select order_id from e2e_tbl_orders) and id not in (select order_id from sale_orderline) and id not in (select order_id from sale_sale where order_id is not null)",
      `delete from table_sessionmove where session_id in (${sessions})`,
      `delete from table_hold where table_id in (${tables})`,
      `update table_tablesession set transferred_from_id = null, merged_into_id = null, split_from_id = null where id in (${sessions})`,
      `delete from table_tablesession where id in (${sessions})`,
      `delete from table_table where id in (${tables})`,
      `delete from table_zone where id in (${zones})`,
    ].join('; '),
  );
}

function cleanUp(): void {
  cleanSales();
  cleanTables();
  cleanInventory();
}

/** Screenshots of the page in the three viewports, each once `ready` says it painted. */
async function shots(page: Page, name: string, ready: () => Promise<void>): Promise<void> {
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await ready();
    await page.screenshot({ path: shot(`${name}-${viewport.label}`), fullPage: true });
  }
  await page.setViewportSize({ width: 1280, height: 860 });
}

const tile = (page: Page, id: string) => shown(page).locator(`[data-testid=table-floor-tile-${id}]`);
const sheet = (page: Page) => page.locator('ion-modal[data-testid=table-sheet]');

async function chooseZone(page: Page): Promise<void> {
  const zoneId = psql(`select id from table_zone where name = '${ZONE}'`);
  await shown(page).locator(`[data-testid=table-floor-zone-tab-${zoneId}]`).click();
}

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

test('Draw the room: a zone and its tables on the plan, a drag that stays, «Edit table»', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/table/floor-plan');
  try {
    const view = shown(page);
    await view.locator('[data-testid=table-floor-mode-edit]').click();
    await view.locator('[data-testid=table-floor-add]').click();
    await page.locator('[data-testid=table-add-zone-name] input').fill(ZONE);
    await page.locator('[data-testid=table-add-zone-submit]').click();
    await expect(page.locator('ion-modal[data-testid=table-add]')).toBeHidden();
    // The new zone is the chosen one: its first table is numbered by itself.
    for (const number of ['', '2']) {
      await view.locator('[data-testid=table-floor-add]').click();
      if (number) await page.locator('[data-testid=table-add-table-number] input').fill(number);
      await page.locator('[data-testid=table-add-table-submit]').click();
      await expect(page.locator('ion-modal[data-testid=table-add]')).toBeHidden();
    }
    const one = await tableByNumber(context, '1');
    const two = await tableByNumber(context, '2');
    await expect(tile(page, one.id)).toContainText('Available');
    await expect(tile(page, two.id)).toContainText('4 pax');

    // A drag saves the place at once; it is still there after a reload.
    const box = await tile(page, one.id).boundingBox();
    if (!box) throw new Error('table 1 has no box');
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 60, box.y + box.height / 2 + 140, { steps: 8 });
    await page.mouse.up();
    await expect.poll(async () => (await tableByNumber(context, '1')).position_y).toBeGreaterThan(one.position_y + 100);
    const moved = await tableByNumber(context, '1');
    await page.reload();
    await shown(page).locator('[data-testid=table-floor-mode-edit]').click();
    await chooseZone(page);
    await expect(tile(page, one.id)).toHaveCSS('top', `${moved.position_y}px`);

    // «Edit table»: round, for six.
    await tile(page, one.id).click();
    await page.locator('[data-testid=table-form-capacity] input').fill('6');
    await page.locator('[data-testid=table-form-shape]').click();
    await page.locator('ion-popover').getByText('Round', { exact: true }).click();
    await page.locator('[data-testid=table-form-submit]').click();
    await expect(page.locator('ion-modal[data-testid=table-form]')).toBeHidden();
    await expect(tile(page, one.id)).toHaveClass(/table-tile--round/);
    await expect(tile(page, one.id)).toContainText('6 pax');
    await shots(page, 'table-floor-edit', async () => {
      await expect(tile(page, two.id)).toBeVisible();
    });
  } finally {
    await context.close();
  }
});

test('Serve the room with the real till: seat, transfer, merge, charge and close', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/table/floor-plan');
  try {
    await chooseZone(page);
    const one = await tableByNumber(context, '1');
    const two = await tableByNumber(context, '2');
    const coffee = await createProduct(context, { name: `E2E Tbl coffee ${STAMP}`, sku: `E2E-TBL-${STAMP}`, price: 150 });

    // Seat three at table 1: its check opens in Sales titled «Table 1».
    await tile(page, one.id).click();
    await expect(sheet(page)).toBeVisible();
    await page.locator('[data-testid=table-guests-quick-3]').click();
    await expect(sheet(page)).toBeHidden();
    await expect(tile(page, one.id)).toContainText('Occupied');
    await expect(tile(page, one.id)).toContainText('3 pax · 0 min');
    const seated = await tableByNumber(context, '1');
    const orderId = seated.checks[0].order_id!;
    const check = await api<{ label: string; status: string }>(context, A, 'GET', `/sale/orders/detail?order_id=${orderId}`);
    expect([check.data.label, check.data.status]).toEqual(['Table 1', 'open']);
    await shots(page, 'table-floor-service', async () => {
      await expect(tile(page, one.id)).toContainText('Occupied');
    });

    // Charge goes to the till with the table's check.
    await tile(page, one.id).click();
    await page.locator('[data-testid=table-sheet-action-charge]').click();
    await expect(page).toHaveURL(new RegExp(`/sale/pos\\?order=${orderId}`));
    await page.goto(`${A}/table/floor-plan`);
    await chooseZone(page);

    // Transfer the party to table 2: the plan picks a free table.
    await tile(page, one.id).click();
    await page.locator('[data-testid=table-sheet-action-transfer]').click();
    await expect(shown(page).locator('[data-testid=table-floor-pick]')).toContainText('Transfer 1 to…');
    await tile(page, two.id).click();
    await expect(tile(page, two.id)).toContainText('Occupied');
    await expect(tile(page, one.id)).toContainText('Available');
    expect((await tableByNumber(context, '2')).checks[0].order_id).toBe(orderId);

    // Seat table 1 again and merge it into table 2: one check of Sales with every line.
    await tile(page, one.id).click();
    await page.locator('[data-testid=table-guests-quick-2]').click();
    await expect(tile(page, one.id)).toContainText('Occupied');
    const second = (await tableByNumber(context, '1')).checks[0].order_id!;
    for (const id of [orderId, second]) {
      const added = await api(context, A, 'POST', '/sale/orders/add_line', { order_id: id, product_id: coffee.id, quantity: '1' });
      expect(added.status).toBe(200);
    }
    await tile(page, one.id).click();
    await page.locator('[data-testid=table-sheet-action-merge]').click();
    await tile(page, two.id).click();
    await expect(tile(page, one.id)).toContainText('Available');
    const merged = await api<{ lines: unknown[] }>(context, A, 'GET', `/sale/orders/detail?order_id=${orderId}`);
    expect(merged.data.lines).toHaveLength(2);

    // Charged in Sales, the table frees itself on the plan (live, no reload).
    await chargeByApi(context, { order_id: orderId, payments: [{ method: 'card' }] });
    await expect(tile(page, two.id)).toContainText('Available', { timeout: 15_000 });

    // A party that leaves without ordering: «Close table» closes it, its empty check is voided.
    await tile(page, one.id).click();
    await page.locator('[data-testid=table-guests-quick-1]').click();
    await expect(tile(page, one.id)).toContainText('Occupied');
    await tableByNumber(context, '1');
    await tile(page, one.id).click();
    await page.locator('[data-testid=table-sheet-action-close]').click();
    await page.locator('[data-testid=table-sheet-close-confirm]').click();
    await expect(tile(page, one.id)).toContainText('Available');

    // Sessions: the closed checks with what they charged.
    await page.goto(`${A}/table/sessions`);
    const sessions = shown(page);
    await sessions.locator('[data-testid=table-sessions-segment-closed]').click();
    await expect(sessions.locator('[data-testid=table-sessions-row]', { hasText: '€3.00' }).first()).toBeVisible();
    await shots(page, 'table-sessions', async () => {
      await expect(sessions.locator('[data-testid=table-sessions-row]').first()).toBeVisible();
    });
  } finally {
    await context.close();
  }
});

test('Zones and Tables: the lists of the room', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/table/zones');
  try {
    let view = shown(page);
    await view.locator('[data-testid=table-zones-search] input').fill(STAMP);
    const zoneRow = view.locator('[data-testid=table-zones-row]', { hasText: ZONE });
    await expect(zoneRow).toContainText('2 / 2');
    await shots(page, 'table-zones', async () => {
      await expect(zoneRow).toBeVisible();
    });

    await page.goto(`${A}/table/tables`);
    view = shown(page);
    await view.locator('[data-testid=table-tables-row]').first().waitFor({ state: 'visible' });
    const zoneId = psql(`select id from table_zone where name = '${ZONE}'`);
    const rows = await api<{ rows: { number: string }[] }>(context, A, 'GET', `/table/tables?zone_id=${zoneId}`);
    expect(rows.data.rows.map((row) => row.number)).toEqual(['1', '2']);
    await shots(page, 'table-tables', async () => {
      await expect(view.locator('[data-testid=table-tables-row]').first()).toBeVisible();
    });
  } finally {
    await context.close();
  }
});

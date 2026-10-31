// «Choose table» in the till (SALE-F19; Tables' TABLE-F12, F13) in Chrome, with the real Tables, Sales
// and Inventory apps: the owner opens a check with a product, seats it at the run's table from the
// check's bar (searched on the server), sees the table chip and the check retitled «Table N», and then
// takes the table off the check: the table frees and the check stays on the till. The sheet in three
// viewports. And «Merge» from Tables (TABLE-F16, SALE-F24) with the till still behind it (hub#459): the
// till's check is the one absorbed, and the till says it was joined and shows the one that stays, never
// «closed on another device». What a run creates — its zone «E2E Tbl <stamp> Till», its tables, the table
// checks and their moves, its checks and lines, its product — is deleted after it.
import { expect, type Page, test } from '@playwright/test';

import { A, api, login, openApps, psql, shown } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { cleanSales, shots, stamp } from './sale-helpers';

const RUN = stamp();
const ZONE = `E2E Tbl ${RUN} Till`;
/** The run's table number: unique, so the till's search finds only it. */
const NUMBER = RUN;
const SKU = `E2E-TBLPOS-${RUN}`;
const CURRENT_CHECK_KEY = 'erplora.sale.pos.currentCheck';

let coffee: Product;
let zoneId: string;
let tableId: string;

interface TableCheck {
  id: string;
  status: string;
  table_id: string | null;
}

/** This spec's zones (any run's), their tables and holds, and every table check of those tables or of
 *  this spec's checks (a parked one has no table) with its moves. Before the sales: they name the checks. */
function cleanTables(): void {
  const zones = "select id from table_zone where name like 'E2E Tbl % Till'";
  const tables = `select id from table_table where zone_id in (${zones})`;
  const orders = "select order_id from sale_orderline where sku like 'E2E-TBLPOS-%'";
  psql(
    [
      `create temp table e2e_tblpos_sessions as select session_id as id from table_sessionmove where table_id in (${tables}) union select id from table_tablesession where table_id in (${tables}) or order_id in (${orders})`,
      'delete from table_sessionmove where session_id in (select id from e2e_tblpos_sessions)',
      `delete from table_hold where table_id in (${tables})`,
      'update table_tablesession set transferred_from_id = null, merged_into_id = null, split_from_id = null where id in (select id from e2e_tblpos_sessions)',
      'delete from table_tablesession where id in (select id from e2e_tblpos_sessions)',
      `delete from table_table where id in (${tables})`,
      `delete from table_zone where id in (${zones})`,
    ].join('; '),
  );
}

test.beforeAll(async ({ browser }) => {
  cleanTables();
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  coffee = await createProduct(context, { name: `E2E Table coffee ${RUN}`, sku: SKU, price: 150, tax_category_key: 'restaurant.drink' });
  const zone = await api<{ id: string }>(context, A, 'POST', '/table/zones', { name: ZONE });
  expect(zone.status, `zone ${JSON.stringify(zone.data)}`).toBe(201);
  zoneId = zone.data.id;
  const table = await api<{ id: string }>(context, A, 'POST', '/table/tables', { zone_id: zoneId, number: NUMBER, capacity: 4 });
  expect(table.status, `table ${JSON.stringify(table.data)}`).toBe(201);
  tableId = table.data.id;
  await context.close();
});

test.afterAll(() => {
  cleanTables();
  cleanSales();
  cleanInventory();
});

async function tillReady(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid^=pos-product-], [data-testid=pos-grid-empty]').first().waitFor({ state: 'visible' });
}

/** Adds a product the way a person finds it: the magnifier, its SKU, the result. */
async function addBySearch(page: Page, product: Product): Promise<void> {
  await shown(page).locator('[data-testid=pos-search-trigger]').click();
  const search = page.locator('[data-testid=pos-search]');
  await search.locator('input').fill(product.sku);
  await search.locator(`[data-testid=pos-search-${product.id}]`).click();
}

const lineOf = (page: Page, name: string) => shown(page).locator('[data-testid^=pos-line-]').filter({ hasText: name }).first();

test('SALE-F19: the till seats its check at a table and takes the table off again', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  await tillReady(page);
  await addBySearch(page, coffee);
  await expect(lineOf(page, coffee.name)).toBeVisible();
  await expect.poll(() => page.evaluate((key) => localStorage.getItem(key), CURRENT_CHECK_KEY)).not.toBeNull();
  const orderId = await page.evaluate((key) => localStorage.getItem(key), CURRENT_CHECK_KEY);
  const till = shown(page);
  const trigger = till.locator('[data-testid=pos-table-trigger]');
  await expect(trigger).toHaveAttribute('title', 'Assign table');

  // «Choose table»: the run's table, searched on the server, free.
  await trigger.click();
  const sheet = page.locator('ion-modal[data-testid=pos-table]');
  await expect(sheet).toBeVisible();
  await sheet.locator('ion-searchbar input').fill(NUMBER);
  const tile = sheet.locator(`[data-testid=pos-table-tile-${tableId}]`);
  await expect(tile).toContainText('Available');
  await expect(tile).toContainText(ZONE);
  await expect(sheet.locator('[data-testid^=pos-table-tile-]')).toHaveCount(1);
  await shots(page, 'sale-table-picker', async () => {
    await expect(tile).toBeVisible();
  });

  // Seated: the chip, the button and the check's title name the table; Tables holds the check.
  await tile.click();
  await expect(sheet).toBeHidden();
  await expect(till.locator('[data-testid=pos-table-chip]')).toHaveText(`Table ${NUMBER}`);
  await expect(till.locator('[data-testid=pos-check-title]')).toHaveValue(`Table ${NUMBER}`);
  await expect(trigger).toHaveAttribute('title', `Assign table: Table ${NUMBER}`);
  const seated = await api<{ rows: TableCheck[] }>(context, A, 'GET', `/table/sessions/by_order?order_id=${orderId}`);
  expect(seated.data.rows.map((row) => [row.status, row.table_id])).toEqual([['open', tableId]]);

  // «Remove from table»: the table frees, the check stays on the till with its line.
  await trigger.click();
  await expect(sheet).toBeVisible();
  await sheet.locator('[data-testid=pos-table-remove]').click();
  await expect(sheet).toBeHidden();
  await expect(till.locator('[data-testid=pos-table-chip]')).toHaveCount(0);
  await expect(trigger).toHaveAttribute('title', 'Assign table');
  await expect(lineOf(page, coffee.name)).toBeVisible();
  expect(await page.evaluate((key) => localStorage.getItem(key), CURRENT_CHECK_KEY)).toBe(orderId);
  const parked = await api<{ rows: TableCheck[] }>(context, A, 'GET', `/table/sessions/by_order?order_id=${orderId}`);
  expect(parked.data.rows.map((row) => [row.status, row.table_id])).toEqual([['parked', null]]);
  const freed = await api<{ status: string }>(context, A, 'GET', `/table/tables/detail?id=${tableId}`);
  expect(freed.data.status).toBe('available');
});

test('TABLE-F16, SALE-F24: merging the table of the till check from Tables says it was joined, not closed on another device', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  await tillReady(page);
  await addBySearch(page, coffee);
  await expect(lineOf(page, coffee.name)).toBeVisible();
  await expect.poll(() => page.evaluate((key) => localStorage.getItem(key), CURRENT_CHECK_KEY)).not.toBeNull();
  const absorbed = (await page.evaluate((key) => localStorage.getItem(key), CURRENT_CHECK_KEY))!;
  const seated = await api<TableCheck>(context, A, 'POST', '/table/sessions/open', { table_id: tableId, order_id: absorbed });
  expect(seated.status, `seat the till's check ${JSON.stringify(seated.data)}`).toBe(201);

  // Another occupied table of the run's zone, with a coffee of its own. Created here, after «Choose table»
  // above has searched the run's number: its number holds that one, and the search would find two tiles.
  const other = `${NUMBER}J`;
  const table = await api<{ id: string }>(context, A, 'POST', '/table/tables', { zone_id: zoneId, number: other, capacity: 4 });
  expect(table.status, `table ${JSON.stringify(table.data)}`).toBe(201);
  const opened = await api<TableCheck & { order_id: string }>(context, A, 'POST', '/table/sessions/open', { table_id: table.data.id });
  expect(opened.status, `open ${JSON.stringify(opened.data)}`).toBe(201);
  const stays = opened.data.order_id;
  const added = await api(context, A, 'POST', '/sale/orders/add_line', { order_id: stays, product_id: coffee.id, quantity: '1' });
  expect(added.status, JSON.stringify(added.data)).toBe(200);

  // To Tables from the shell, with the till still mounted behind (Ionic keeps the stack): «Merge» the till's table into the other.
  const apps = await openApps(page);
  await apps.locator('[data-testid=apps-launcher-app]', { hasText: 'Tables' }).click();
  const floor = shown(page);
  await floor.locator('[data-testid=table-floor-mode-service]').click();
  await floor.locator(`[data-testid=table-floor-zone-tab-${zoneId}]`).click();
  await floor.locator(`[data-testid=table-floor-tile-${tableId}]`).click();
  await page.locator('ion-modal[data-testid=table-sheet] [data-testid=table-sheet-action-merge]').click();
  await expect(floor.locator('[data-testid=table-floor-pick]')).toContainText(`Merge ${NUMBER} with…`);
  await floor.locator(`[data-testid=table-floor-tile-${table.data.id}]`).click();
  await expect(floor.locator(`[data-testid=table-floor-tile-${tableId}]`)).toContainText('Available');

  // The till behind says the check was joined (neutral), never that it was closed on another device.
  const toasts = page.locator('ion-toast');
  await expect(toasts.filter({ hasText: 'That check was joined with another one' }).first()).toBeVisible();
  await expect(toasts.filter({ hasText: 'closed on another device' })).toHaveCount(0);
  expect((await api<{ status: string; merged_into_id: string | null }>(context, A, 'GET', `/sale/orders/detail?order_id=${absorbed}`)).data).toMatchObject({
    status: 'voided',
    merged_into_id: stays,
  });

  // Back on the till: the check that stays, with both coffees, and nothing lost.
  await page.goBack();
  const till = shown(page);
  await till.locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  await expect(till.locator('[data-testid=pos-check-title]')).toHaveValue(`Table ${other}`);
  expect(await page.evaluate((key) => localStorage.getItem(key), CURRENT_CHECK_KEY)).toBe(stays);
  await expect(till.locator('[data-testid^=pos-line-]').filter({ hasText: coffee.name })).not.toHaveCount(0);
  const joined = await api<{ status: string; lines: { sku: string }[] }>(context, A, 'GET', `/sale/orders/detail?order_id=${stays}`);
  expect(joined.data.status).toBe('open');
  expect(joined.data.lines.filter((line) => line.sku === SKU)).toHaveLength(2);
  await expect(toasts.filter({ hasText: 'closed on another device' })).toHaveCount(0);
});

// Tables in Chrome (apps/table/WORKBOOK.md), with the real Sales, Inventory and Customers apps: the owner
// draws a zone and its tables on the floor plan (Edit plan: «+», a drag that stays after a reload, «Edit
// table», a long table by its width and height), serves it (Service: seats a party, transfers it, merges two tables, charges in Sales — the plan
// frees the table by itself, live — and closes an empty table), and reads the checks in Sessions, the
// zones in Zones and the tables in Tables. Every screen in three viewports. What a run creates lives in a
// zone named «E2E Tbl <stamp>…» and its checks; `afterAll` removes all of it, sales included.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, capture, psql, settled, shot, shown } from './helpers';
import { cleanInventory, createProduct } from './inventory-helpers';
import { chargeByApi, cleanSales } from './sale-helpers';
import { ownerPage, post } from './service-helpers';

const STAMP = Date.now().toString(36).toUpperCase();
const ZONE = `E2E Tbl ${STAMP} Terrace`;
const HALL = `E2E Tbl ${STAMP} Hall`;
const PATIO = `E2E Tbl ${STAMP} Patio`;
const LONG = `E2E Tbl ${STAMP} Long`;
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

    // A drag saves the place at once (the plan is spread on screen: 140 px are more than 50 of the plan); it is
    // still there after a reload.
    const box = await tile(page, one.id).boundingBox();
    if (!box) throw new Error('table 1 has no box');
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 60, box.y + box.height / 2 + 140, { steps: 8 });
    await page.mouse.up();
    await expect.poll(async () => (await tableByNumber(context, '1')).position_y).toBeGreaterThan(one.position_y + 50);
    const moved = await tableByNumber(context, '1');
    await page.reload();
    await shown(page).locator('[data-testid=table-floor-mode-edit]').click();
    await chooseZone(page);
    await expect(tile(page, one.id)).toHaveAttribute('data-y', String(moved.position_y));

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

test('A long table: «Edit table» takes its width and height, and the plan paints its box as long as it is', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/table/floor-plan');
  try {
    const zone = await post<{ id: string }>(context, '/table/zones', { name: LONG });
    const table = await post<{ id: string }>(context, '/table/tables', { zone_id: zone.id, number: '8', capacity: 8 });
    const detail = async () => (await api<TableRow & { width: number; height: number }>(context, A, 'GET', `/table/tables/detail?id=${table.id}`)).data;
    const ratio = async () => {
      const box = await tile(page, table.id).boundingBox();
      if (!box) throw new Error('table 8 has no box');
      return box.width / box.height;
    };
    const view = shown(page);
    await view.locator('[data-testid=table-floor-mode-edit]').click();
    await view.locator(`[data-testid=table-floor-zone-tab-${zone.id}]`).click();
    expect(await ratio()).toBeCloseTo(1, 1);

    await tile(page, table.id).click();
    const form = page.locator('ion-modal[data-testid=table-form]');
    await expect(form.locator('[data-testid=table-form-width] input')).toHaveValue('72');
    await form.locator('[data-testid=table-form-shape]').click();
    await page.locator('ion-popover').getByText('Rectangular', { exact: true }).click();
    // A side the server does not take is said under it, and nothing is saved.
    await form.locator('[data-testid=table-form-width] input').fill('10');
    await form.locator('[data-testid=table-form-submit]').click();
    await expect(form.locator('[data-testid=table-form-width] .error-text')).toHaveText('Ensure this value is greater than or equal to 24.');
    expect(await detail()).toMatchObject({ width: 72, height: 72, shape: 'square' });

    await form.locator('[data-testid=table-form-width] input').fill('160');
    await shots(page, 'table-form-size', async () => {
      await expect(form.locator('[data-testid=table-form-height] input')).toHaveValue('72');
    });
    await form.locator('[data-testid=table-form-submit]').click();
    await expect(form).toBeHidden();
    expect(await detail()).toMatchObject({ width: 160, height: 72, shape: 'rectangle' });
    await expect(tile(page, table.id)).toHaveClass(/table-tile--rectangle/);
    await expect.poll(ratio).toBeGreaterThan(2.1);
    expect(await ratio()).toBeCloseTo(160 / 72, 1);
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
    await expect(tile(page, one.id)).toContainText('3/6 pax');
    await expect(tile(page, one.id)).toContainText('0:00');
    const seated = await tableByNumber(context, '1');
    const orderId = seated.checks[0].order_id!;
    const check = await api<{ label: string; status: string }>(context, A, 'GET', `/sale/orders/detail?order_id=${orderId}`);
    expect([check.data.label, check.data.status]).toEqual(['Table 1', 'open']);
    await shots(page, 'table-floor-service', async () => {
      await expect(tile(page, one.id)).toContainText('Occupied');
    });

    // Charge goes to the till with the table's check: waited for by what the till shows, not by its URL (the
    // till drops `?order=` as soon as it has loaded the check, sometimes before a URL check sees it).
    await tile(page, one.id).click();
    await page.locator('[data-testid=table-sheet-action-charge]').click();
    await expect(shown(page).locator('[data-testid=pos-check-title]')).toHaveValue('Table 1');
    await expect(page).toHaveURL(/\/sale\/pos(\?|$)/);
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

interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

const overlaps = (a: Box, b: Box): boolean => a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;
const inside = (a: Box, b: Box): boolean => a.x >= b.x - 1 && a.y >= b.y - 1 && a.x + a.width <= b.x + b.width + 1 && a.y + a.height <= b.y + b.height + 1;

/** Ten tables made at once in a new zone, in every state the plan paints. */
async function glanceRoom(context: BrowserContext): Promise<string[]> {
  const zone = await post<{ id: string }>(context, '/table/zones', { name: HALL });
  const made = await post<{ rows: { id: string }[] }>(context, '/table/tables/bulk_create', { zone_id: zone.id, count: 10 });
  const ids = made.rows.map((table) => table.id);
  await post(context, '/table/tables/update', { id: ids[1], shape: 'round' }, 200);
  await post(context, '/table/tables/update', { id: ids[7], shape: 'rectangle', capacity: 6 }, 200);
  for (const [index, guests] of [[1, 3], [2, 2], [3, 4], [7, 5]]) await post(context, '/table/sessions/open', { table_id: ids[index], guests_count: guests });
  const since = (index: number, minutes: number) =>
    `update table_tablesession set opened_at = now() - interval '${minutes} minutes' where table_id = '${ids[index]}' and status = 'open'`;
  psql([since(2, 70), since(3, 100)].join('; '));
  const hold = (index: number, label: string, from: number) => ({
    table_id: ids[index],
    source_ref: `e2e-${STAMP}-${index}`,
    held_from: new Date(Date.now() + from * 60_000).toISOString(),
    held_until: new Date(Date.now() + (from + 90) * 60_000).toISOString(),
    party_size: 4,
    label,
  });
  await post(context, '/table/holds', hold(4, 'Maximiliana Fernández de la Concepción', 30));
  await post(context, '/table/tables/update', { id: ids[5], blocked: true }, 200);
  return ids;
}

test('The default zone fits the stage with every status apart, and a phone lists it as cards', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/table/floor-plan');
  try {
    const ids = await glanceRoom(context);
    const zoneId = psql(`select id from table_zone where name = '${HALL}'`);
    await shown(page).locator(`[data-testid=table-floor-zone-tab-${zoneId}]`).click();
    await expect(tile(page, ids[3])).toHaveAttribute('data-timer', 'critical');
    await expect(tile(page, ids[2])).toHaveAttribute('data-timer', 'warning');
    await expect(tile(page, ids[4])).toHaveAttribute('data-status', 'reserved');
    await expect(tile(page, ids[5])).toHaveAttribute('data-status', 'blocked');
    for (const viewport of [VIEWPORTS[2], VIEWPORTS[1]]) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      // The plan fits again once the stage has its new size and the tables have come in: measured still.
      await settled(page);
      const stage = await shown(page).locator('[data-testid=table-floor-stage]').boundingBox();
      if (!stage) throw new Error('the plan has no stage');
      const boxes: Box[] = [];
      for (const id of ids) {
        const table = await tile(page, id).locator('.table-tile__button').boundingBox();
        const label = await tile(page, id).locator('.table-tile__caption').boundingBox();
        if (!table || !label) throw new Error(`table ${id} is not painted`);
        expect(inside(table, stage), `table ${id} inside the stage at ${viewport.label}`).toBe(true);
        expect(inside(label, stage), `the label of table ${id} inside the stage at ${viewport.label}`).toBe(true);
        expect(overlaps(table, label), `table ${id} clear of its own label at ${viewport.label}`).toBe(false);
        boxes.push(table, label);
      }
      for (const [index, box] of boxes.entries()) {
        for (const other of boxes.slice(index + (index % 2 ? 1 : 2))) expect(overlaps(box, other), `${viewport.label}: ${JSON.stringify([box, other])}`).toBe(false);
      }
      // A long name is cut with an ellipsis inside the place of its table; its hour never is.
      const name = tile(page, ids[4]).locator('[data-part=hold-name]');
      expect(await name.evaluate((el) => el.scrollWidth > el.clientWidth), `the long name is cut at ${viewport.label}`).toBe(true);
      await expect(tile(page, ids[4]).locator('[data-part=hold-time]')).toBeVisible();
      for (const theme of ['light', 'dark']) {
        await page.evaluate((dark) => document.documentElement.classList.toggle('ion-palette-dark', dark), theme === 'dark');
        await capture(page, `table-floor-glance-${viewport.label}-${theme}`);
      }
      await page.evaluate(() => document.documentElement.classList.remove('ion-palette-dark'));
    }
    await page.setViewportSize({ width: VIEWPORTS[0].width, height: VIEWPORTS[0].height });
    await expect(shown(page).locator('[data-testid=table-floor-cards]')).toBeVisible();
    await expect(shown(page).locator('[data-testid=table-floor-canvas]')).toHaveCount(0);
    await expect(shown(page).locator('[data-testid^=table-floor-tile-]')).toHaveCount(10);
    for (const theme of ['light', 'dark']) {
      await page.evaluate((dark) => document.documentElement.classList.toggle('ion-palette-dark', dark), theme === 'dark');
      await capture(page, `table-floor-glance-390-${theme}`);
    }
  } finally {
    await context.close();
  }
});

const centre = (box: Box) => ({ x: box.x + box.width / 2, y: box.y + box.height / 2 });

async function savedX(context: BrowserContext, table: TableRow): Promise<number> {
  const res = await api<TableRow>(context, A, 'GET', `/table/tables/detail?table=${table.number}&zone=${encodeURIComponent(PATIO)}`);
  return res.data.position_x;
}

test('Edit plan on a tablet: the farthest table of a new zone goes past it, under the pointer, and the others stay', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/table/floor-plan', { width: VIEWPORTS[1].width, height: VIEWPORTS[1].height });
  try {
    const zone = await post<{ id: string }>(context, '/table/zones', { name: PATIO });
    const made = await post<{ rows: TableRow[] }>(context, '/table/tables/bulk_create', { zone_id: zone.id, count: 10 });
    const far = made.rows.reduce((best, table) => (table.position_x > best.position_x ? table : best));
    const view = shown(page);
    await view.locator('[data-testid=table-floor-mode-edit]').click();
    await view.locator(`[data-testid=table-floor-zone-tab-${zone.id}]`).click();
    await expect(tile(page, far.id)).toBeVisible();
    await settled(page);
    const button = (id: string) => tile(page, id).locator('.table-tile__button');
    const others = made.rows.filter((table) => table.id !== far.id).map((table) => table.id);
    const before = await Promise.all(others.map((id) => button(id).boundingBox()));
    const from = await button(far.id).boundingBox();
    if (!from) throw new Error('the farthest table is not painted');
    const start = centre(from);
    await page.mouse.move(start.x, start.y);
    await page.mouse.down();
    await page.mouse.move(start.x + 56, start.y, { steps: 8 });
    await page.mouse.up();
    await expect.poll(() => savedX(context, far)).toBeGreaterThan(far.position_x);
    await settled(page);
    const to = await button(far.id).boundingBox();
    if (!to) throw new Error('the dropped table is not painted');
    expect(Math.abs(centre(to).x - (start.x + 56)), 'the dropped table is under the pointer').toBeLessThan(3);
    expect(Math.abs(centre(to).y - start.y), 'the dropped table is under the pointer').toBeLessThan(3);
    const after = await Promise.all(others.map((id) => button(id).boundingBox()));
    for (const [index, id] of others.entries()) {
      const was = before[index];
      const now = after[index];
      if (!was || !now) throw new Error(`table ${id} is not painted`);
      expect(Math.abs(now.x - was.x) + Math.abs(now.y - was.y), `table ${id} did not move`).toBeLessThan(0.5);
    }
    await capture(page, 'table-floor-edit-834-full', { fullPage: true });
  } finally {
    await context.close();
  }
});

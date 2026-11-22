// flow: SALE-F16, TABLE-F09, KITCHEN-F18 — who serves a table's check is the check's, kept in the Hub, not a state of
// one screen. A waiter seats a table on the plan, opens its check, says Lucia serves it and adds a dish (hers), moves a
// second dish to Marta, leaves the check and opens it again from the plan: the chip still says Lucia, each line names
// its professional, the round sent to the kitchen names Lucia and the table's window says Lucia serves it. Seen at
// 1440×900, 834×1112 and 375×667. In Chrome with the real Tables, Sales, Kitchen, Staff and Inventory apps. What a run
// creates (its zone «E2E Srv <stamp>», its table, the check with its lines and kitchen ticket, its dishes and the two
// team members) is deleted after it.
import { expect, type Page, test } from '@playwright/test';

import { A, api, capture, login, psql, shown } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { cleanSales, dishForTheTill, linesOf, openTillCart, restoreDrawer, stamp, zoneWithTable } from './sale-helpers';
import { toastSaying } from './toast-helpers';

const RUN = stamp();
const ZONE = `E2E Srv ${RUN}`;
const LUCIA = `E2E Lucia ${RUN}`;
const MARTA = `E2E Marta ${RUN}`;
const SIZES = [
  { label: '1440', width: 1440, height: 900 },
  { label: '834', width: 834, height: 1112 },
  { label: '375', width: 375, height: 667 },
] as const;

let soup: Product;
let steak: Product;
let zoneId: string;
let tableId: string;
const members: Record<string, string> = {};

/** This spec's zones (any run's), their tables and their table checks with their moves; then the sales and their
 *  kitchen tickets, the dishes and the team members. */
function cleanUp(): void {
  const zones = "select id from table_zone where name like 'E2E Srv %'";
  const tables = `select id from table_table where zone_id in (${zones})`;
  psql(
    [
      `create temp table e2e_srv_sessions as select session_id as id from table_sessionmove where table_id in (${tables}) union select id from table_tablesession where table_id in (${tables})`,
      'delete from table_sessionmove where session_id in (select id from e2e_srv_sessions)',
      `delete from table_hold where table_id in (${tables})`,
      'update table_tablesession set transferred_from_id = null, merged_into_id = null, split_from_id = null where id in (select id from e2e_srv_sessions)',
      'delete from table_tablesession where id in (select id from e2e_srv_sessions)',
      `delete from table_table where id in (${tables})`,
      `delete from table_zone where id in (${zones})`,
    ].join('; '),
  );
  cleanSales();
  cleanInventory();
  psql("delete from staff_member where first_name like 'E2E Lucia %' or first_name like 'E2E Marta %'");
}

test.use({ locale: 'en-US' });

test.beforeAll(async ({ browser }) => {
  cleanUp();
  soup = await dishForTheTill(browser, 'SRVSOUP', RUN);
  const context = await browser.newContext({ baseURL: A });
  await login(await context.newPage(), A, '/table/floor-plan');
  steak = await createProduct(context, { name: `E2E SRVSTEAK Dish ${RUN}`, sku: `E2E-SRVSTEAK-${RUN}`, price: 1800, tax_category_key: 'restaurant.food' });
  ({ zoneId, tableId } = await zoneWithTable(context, ZONE, RUN));
  for (const name of [LUCIA, MARTA]) {
    const member = await api<{ id: string }>(context, A, 'POST', '/staff/members', { first_name: name, last_name: 'Garcia' });
    expect(member.status, `the member ${JSON.stringify(member.data)}`).toBe(201);
    members[name] = member.data.id;
  }
  await context.close();
});

test.afterAll(() => {
  try {
    cleanUp();
  } finally {
    restoreDrawer();
  }
});

const tile = (page: Page) => shown(page).locator(`[data-testid=table-floor-tile-${tableId}]`);
const chip = (page: Page) => shown(page).locator('[data-testid=pos-staff-chip]');

/** The floor plan in service, on this spec's zone. */
async function floor(page: Page): Promise<void> {
  await page.goto(`${A}/table/floor-plan`);
  await shown(page).locator('[data-testid=table-floor-mode-service]').click();
  await shown(page).locator(`[data-testid=table-floor-zone-tab-${zoneId}]`).click();
  await tile(page).waitFor({ state: 'visible' });
}

/** The professional named under the line of `dish`. */
async function staffOf(page: Page, dish: Product) {
  const id = (await linesOf(page, dish).first().getAttribute('data-testid'))?.replace('pos-line-', '');
  return shown(page).locator(`[data-testid=pos-line-${id}-staff]`);
}

async function pick(page: Page, name: string): Promise<void> {
  await page.locator(`[data-testid=pos-staff-${members[name]}]:visible`).click();
}

test('SALE-F16 (hub#2002): a table’s check left and opened again from the plan keeps who serves it and each line’s professional', async ({ page }) => {
  test.setTimeout(150_000);
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/table/floor-plan');
  await floor(page);

  // Seat two and open the table's check: Lucia serves it, the soup is hers and the steak is moved to Marta.
  await tile(page).click();
  await page.locator('[data-testid=table-guests-quick-2]').click();
  await expect(tile(page)).toContainText('Occupied');
  await tile(page).click();
  await expect(shown(page).locator('[data-testid=pos-check-title]')).toHaveValue(`Table ${RUN}`);
  await expect(chip(page)).toContainText('Served by me');
  await chip(page).click();
  await pick(page, LUCIA);
  await expect(chip(page)).toContainText(`Served by ${LUCIA} Garcia`);
  await shown(page).locator(`[data-testid=pos-product-${soup.id}]`).click();
  await shown(page).locator(`[data-testid=pos-product-${steak.id}]`).click();
  await expect(await staffOf(page, soup)).toHaveText(`${LUCIA} Garcia`);
  await (await staffOf(page, steak)).click();
  await pick(page, MARTA);
  await expect(await staffOf(page, steak)).toHaveText(`${MARTA} Garcia`);

  // Out of the check, and back to it from the plan.
  await floor(page);
  await tile(page).click();
  await expect(shown(page).locator('[data-testid=pos-check-title]')).toHaveValue(`Table ${RUN}`);
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await openTillCart(page);
    await expect(chip(page)).toContainText(`Served by ${LUCIA} Garcia`);
    await expect(await staffOf(page, soup)).toHaveText(`${LUCIA} Garcia`);
    await expect(await staffOf(page, steak)).toHaveText(`${MARTA} Garcia`);
    await expect(shown(page).locator('[data-testid=pos-total]')).toContainText('25.00');
    await capture(page, `APP-SALE-SALE-F16-reopened-${size.label}`);
  }

  // The round sent to the kitchen names who serves the check.
  await page.setViewportSize({ width: 1440, height: 900 });
  await shown(page).locator('[data-testid=pos-kitchen-send]').click();
  await expect(toastSaying(page, 'Order 1 sent to the kitchen.')).toBeVisible();
  const orderId = psql(`select order_id from table_tablesession where table_id = '${tableId}' and status = 'open'`);
  const waiter = psql(
    `select distinct t.waiter from kitchen_ticket t join kitchen_ticketitem i on i.ticket_id = t.id join sale_orderline l on l.id = i.sale_line_id where l.order_id = '${orderId}'`,
  );
  expect(waiter, 'the kitchen ticket names who serves the check').toBe(`${LUCIA} Garcia`);

  // The table's window says who serves it.
  await floor(page);
  await tile(page).click({ button: 'right' });
  await expect(page.locator('[data-testid=table-sheet-summary]:visible')).toContainText(`Served by ${LUCIA} Garcia`);
  await capture(page, 'APP-TABLE-TABLE-F09-served-by-1440');
});

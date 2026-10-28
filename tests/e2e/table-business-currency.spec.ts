// flow: table-business-currency (FIX-HUB-TABLE-CHARGES-IN-EUR-WHATEVER-THE-COUNTRY; apps/table/WORKBOOK.md «Sesiones»,
// TABLE-F17 and TABLE-F22)
// Tables paints money in the currency it was charged in and, what is not charged yet, in the business's: its country's,
// as erplora.com registered it (`PUT /internal/hubs/{id}`, signed the way the SaaS sends it), never a fixed euro. Against
// the real Sales and Inventory, no mocks: a check of the run is charged in euros while hub `a` is in Spain; then `a`
// moves to Poland and a second check is charged there (Sales keeps each sale's currency). In 390, 834 and 1440, Tables →
// Sessions «Closed» reads the Polish check's «Charged» in złoty and the Spanish one's still in euros (a record is never
// rewritten), «Details» of the Polish one says złoty, and «Split check» of an open table paints its lines in złoty
// (captures `FIX-HUB-TABLE-CHARGES-IN-EUR-WHATEVER-THE-COUNTRY-<width>` and `…-split-<width>`). Back in Spain the open
// table splits in euros and the Polish check keeps its złoty (`…-es-1440`). What the run creates is deleted after it and
// `a`'s registration put back, also when a test fails.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, login, psql, registerBusinessIn, registrationOf, type Registration, shot, shown } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { chargeByApi, cleanSales, stamp } from './sale-helpers';
import { noHorizontalScroll, post, rowAction, settled } from './service-helpers';

const KEY = 'FIX-HUB-TABLE-CHARGES-IN-EUR-WHATEVER-THE-COUNTRY';
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;
const RUN = stamp();
const TAG = `E2E Tbc ${RUN}`;
const ZONE = `${TAG} Room`;
const SKU = `E2E-TBC-${RUN}`;
/** Two dishes at 12,50 as a till in Poland writes them: «25,00 zł», «zł 25.00». */
const CHARGED_IN_ZLOTY = /zł\s?25[.,]00|25[.,]00\s?zł/;
/** One dish at 12,50 charged in Spain before the move. */
const CHARGED_IN_EUROS = /€\s?12[.,]50|12[.,]50\s?€/;
/** A line of the open check: one dish at 12,50. */
const LINE_IN_ZLOTY = /zł\s?12[.,]50|12[.,]50\s?zł/;
const LINE_IN_EUROS = /€\s?12[.,]50|12[.,]50\s?€/;

/** `a`'s registration as the run found it (put back after). */
let original: Registration;
let zoneId = '';
let dish: Product;
/** The run's checks: charged in Spain, charged in Poland, and the open one (its table and its line). */
const run = { spanish: '', polish: '', openTable: '', line: '' };

test.describe.configure({ mode: 'serial' });
test.use({ actionTimeout: 30_000 });

/** Deletes the run's room: its checks' history, its checks, its tables and its zone (Sales cleans its checks). */
function cleanUp(): void {
  const zones = "select id from table_zone where name like 'E2E Tbc %'";
  const tables = `select id from table_table where zone_id in (${zones})`;
  psql(
    [
      `delete from table_sessionmove where table_id in (${tables}) or session_id in (select id from table_tablesession where table_id in (${tables}))`,
      `update table_tablesession set transferred_from_id = null, merged_into_id = null, split_from_id = null where table_id in (${tables})`,
      `delete from table_tablesession where table_id in (${tables})`,
      `delete from table_table where id in (${tables})`,
      `delete from table_zone where id in (${zones})`,
    ].join('; '),
  );
}

/** Seats two at the run's table `number` and puts `dishes` on its check; returns the check and its order. */
async function seatWith(context: BrowserContext, number: string, dishes: number): Promise<{ id: string; order_id: string; line: string }> {
  const table = await post<{ id: string }>(context, '/table/tables', { zone_id: zoneId, number, capacity: 4 });
  const check = await post<{ id: string; order_id: string }>(context, '/table/sessions/open', { table_id: table.id, guests_count: 2 });
  let line = '';
  for (let i = 0; i < dishes; i += 1) {
    const added = await api<{ lines: { id: string; sku: string }[] }>(context, A, 'POST', '/sale/orders/add_line', {
      order_id: check.order_id,
      product_id: dish.id,
      quantity: '1',
    });
    expect(added.status, JSON.stringify(added.data)).toBe(200);
    line = added.data.lines.filter((l) => l.sku === SKU).at(-1)!.id;
  }
  return { ...check, line };
}

/** Seats and charges a check at table `number` with `dishes` by card, through Sales; returns the check's id. */
async function chargedCheck(context: BrowserContext, number: string, dishes: number, currency: string): Promise<string> {
  const check = await seatWith(context, number, dishes);
  const sale = await chargeByApi(context, { order_id: check.order_id, payments: [{ method: 'card' }] });
  expect(sale.currency, `the check of table ${number} is charged in the business's currency`).toBe(currency);
  return check.id;
}

/** The row (or card, on a phone) of check `id` in Tables → Sessions «Closed». */
async function closedRow(page: Page, id: string): Promise<Locator> {
  await page.goto(`${A}/table/sessions`);
  await shown(page).locator('[data-testid=table-sessions-segment-closed]').click();
  const row = shown(page).locator(`[data-testid=table-sessions-row][data-id="${id}"]`);
  await expect(row).toBeVisible();
  return row;
}

/** «Split check» of the run's open table, on the plan (Service); returns the line's checkbox. */
async function splitLine(page: Page): Promise<Locator> {
  await page.goto(`${A}/table/floor-plan`);
  await shown(page).locator('[data-testid=table-floor-mode-service]').click();
  await shown(page).locator(`[data-testid=table-floor-zone-tab-${zoneId}]`).click();
  await shown(page).locator(`[data-testid=table-floor-tile-${run.openTable}]`).click();
  const sheet = page.locator('ion-modal[data-testid=table-sheet]');
  await expect(sheet).toBeVisible();
  await settled(page);
  await sheet.locator('[data-testid=table-sheet-action-split]').click();
  const line = sheet.locator(`[data-testid=table-sheet-split-line-${run.line}]`);
  await expect(line).toBeVisible();
  return line;
}

test.beforeAll(async ({ browser }) => {
  original = registrationOf('a');
  cleanUp();
  await registerBusinessIn(original, 'ES');
  const context = await browser.newContext({ baseURL: A, locale: 'en-US' });
  try {
    await login(await context.newPage(), A, '/table/sessions');
    dish = await createProduct(context, { name: `${TAG} dish`, sku: SKU, price: 1250, tax_category_key: 'restaurant.drink' });
    zoneId = (await post<{ id: string }>(context, '/table/zones', { name: ZONE })).id;
    // Charged while the business is in Spain: its sale keeps the euro.
    run.spanish = await chargedCheck(context, '1', 1, 'EUR');
  } finally {
    await context.close();
  }
});

test.afterAll(async () => {
  if (original) await registerBusinessIn(original, original.country);
  cleanUp();
  cleanSales();
  cleanInventory();
});

test(`${KEY}: table-business-currency a business in Poland reads Sessions, Details and Split check in złoty in 390, 834 and 1440`, async ({
  page,
  context,
}) => {
  await registerBusinessIn(original, 'PL');
  await login(page, A, '/table/sessions');
  // The owner's session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  run.polish = await chargedCheck(context, '2', 2, 'PLN');
  const open = await seatWith(context, '3', 1);
  run.openTable = psql(`select table_id from table_tablesession where id = '${open.id}'`);
  run.line = open.line;

  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    const polish = await closedRow(page, run.polish);
    await expect(polish, size.name).toContainText(CHARGED_IN_ZLOTY);
    await expect(polish, size.name).not.toContainText('€');
    // Charged in euros before the move: it stays in euros.
    const spanish = shown(page).locator(`[data-testid=table-sessions-row][data-id="${run.spanish}"]`);
    await expect(spanish, size.name).toContainText(CHARGED_IN_EUROS);
    await expect(spanish, size.name).not.toContainText('zł');
    await settled(page);
    await noHorizontalScroll(page, size.name);
    await page.screenshot({ path: shot(`${KEY}-${size.name}`) });

    await rowAction(page, 'table-sessions', run.polish, 'detail');
    const detail = page.locator('ion-modal[data-testid=table-session-detail]');
    await expect(detail.locator('[data-testid=table-session-detail-paid]'), size.name).toHaveText(CHARGED_IN_ZLOTY);
    await expect(detail.locator('[data-testid=table-session-detail-paid]')).toBeInViewport();
    await settled(page);
    await page.screenshot({ path: shot(`${KEY}-detail-${size.name}`) });
    await detail.locator('[data-testid=table-session-detail-done]').click();
    await expect(detail).toBeHidden();

    const line = await splitLine(page);
    await expect(line, size.name).toContainText(LINE_IN_ZLOTY);
    await expect(line, size.name).not.toContainText('€');
    await settled(page);
    await page.screenshot({ path: shot(`${KEY}-split-${size.name}`) });
  }
});

test(`${KEY}: table-business-currency back in Spain an open table splits in euros and the check charged in Poland keeps its złoty`, async ({
  page,
}) => {
  await registerBusinessIn(original, 'ES');
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/table/sessions');
  const polish = await closedRow(page, run.polish);
  await expect(polish).toContainText(CHARGED_IN_ZLOTY);
  const line = await splitLine(page);
  await expect(line).toContainText(LINE_IN_EUROS);
  await expect(line).not.toContainText('zł');
  await settled(page);
  await page.screenshot({ path: shot(`${KEY}-es-1440`) });
});

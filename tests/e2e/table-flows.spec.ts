// Every flow of Tables with a screen, in Chrome and in three sizes (apps/table/WORKBOOK.md, TABLE-F01 to F32),
// against the real apps it works with: Sales (each table's check, its lines, charges and voids, the till's
// «Choose table»), Customers (the card of a check, its erasure), Reservations (a confirmed reservation holds its
// table; moving, cancelling or not showing up moves or frees it; seating spends it) and Schedules (the book open
// all day). Each test sets up what it needs through the apps' own APIs (setup, never the check), looks at the
// screen and takes its screenshots `APP-TABLE-<flow>-{390,834,1440}`. TABLE-F07, F29 and F30 have no screen
// (assistant and API, as in the old module; the hourly sweep): their evidence is in apps/table/tests. What this
// file creates is named «E2E Tbf <stamp>…» and deleted after it, with its checks, sales, cards and reservations;
// the room's settings go back as they were.
import { spawnSync } from 'node:child_process';

import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, HUB_DIR, psql, shot, shown } from './helpers';
import { cleanInventory, createProduct, pick, type Product } from './inventory-helpers';
import { chargeByApi, cleanSales, openTillCart, stamp } from './sale-helpers';
import { ownerPage, post, rowAction, settled } from './service-helpers';
import { bookingDays, bookingTimes, type BookingTimes, RESERVED_LEAD_MINUTES, untilMidnight } from './table-clock';

const RUN = stamp();
const TAG = `E2E Tbf ${RUN}`;
const ZONE = `${TAG} Patio`;
const SKU = `E2E-TBF-${RUN}`;
/** The maximum every slot of the run carries: how `cleanUp` knows them (slots have no name). */
const SENTINEL = 79;

/** The three sizes of every flow's screenshots (390×844, 834×1112, 1440×900). */
const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

interface Check {
  id: string;
  order_id: string | null;
  customer_name: string | null;
}
interface TableRow {
  id: string;
  number: string;
  status: string;
  position_y: number;
  checks: Check[];
  hold: { label: string; erased: boolean } | null;
}

let zoneId = '';
let coffee: Product;
const settingsBefore: Record<string, unknown> = {};

// One room built by the first tests and served by the next ones: a failure stops the rest (a new worker would
// clean the room up before them).
test.describe.configure({ mode: 'serial' });

/** `APP-TABLE-<flow>-<size>` for each of `flows`, in the three sizes, each once `ready` says it painted. */
async function flowShots(page: Page, flows: string[], ready: () => Promise<void>): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await ready();
    await settled(page);
    // A new size relays the shell out (menu, tabs): one page header on screen once it settled, never a second
    // copy of the page under the first (as cash-register-flows.spec.ts waits for it).
    await expect
      .poll(() =>
        page.evaluate(
          () =>
            [...document.querySelectorAll('ion-header')].filter((header) => {
              const box = header.getBoundingClientRect();
              const inside = box.bottom > 0 && box.top < window.innerHeight && box.right > 0 && box.left < window.innerWidth;
              return !header.closest('ion-modal, ion-menu') && box.height > 0 && inside;
            }).length,
        ),
      )
      .toBe(1);
    for (const flow of flows) await page.screenshot({ path: shot(`APP-TABLE-${flow}-${size.label}`) });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

/** The times of a test's reservations (table-clock.ts). In the last minutes of the day none of today is left: the
 *  test waits for midnight first (less than ten minutes), its timeout stretched by exactly that wait. */
async function reservationTimes(): Promise<BookingTimes> {
  const now = new Date();
  const times = bookingTimes(now);
  if (times) return times;
  const wait = untilMidnight(now) + 1_000;
  test.setTimeout(test.info().timeout + wait);
  await new Promise((done) => setTimeout(done, wait));
  const after = bookingTimes(new Date());
  expect(after, 'a time of the new day after midnight').not.toBeNull();
  return after!;
}

/** A wall-clock time («20:00») as the plan paints it (`clock` of `apps/table/frontend/lib/format.ts`): the
 *  browser's own Intl in the page's language («8:00 PM» in English), never a 24-hour string by hand. */
function painted(page: Page, time: string): Promise<string> {
  const [hours, minutes] = time.split(':').map(Number);
  return page.evaluate(
    ([h, m]) =>
      new Intl.DateTimeFormat(document.documentElement.lang, { hour: 'numeric', minute: '2-digit', timeZone: 'UTC' }).format(
        Date.UTC(2000, 0, 1, h, m),
      ),
    [hours, minutes] as const,
  );
}

/** The outbox relay as the worker runs it on every tick (`base.relay.run`), on this run's database, tick after
 *  tick until a pass finds nothing to do: the e2e stack runs no worker, so what other specs recorded waits too. */
function relayPass(): void {
  const code = [
    'from django.utils import timezone',
    'from base import relay',
    'for _ in range(200):',
    '    done = relay.run(timezone.now())',
    '    if not (done.taken or done.delivered): break',
    'print(done)',
  ].join('\n');
  const out = spawnSync('uv', ['run', 'python', 'manage.py', 'shell', '-c', code], { cwd: HUB_DIR, env: process.env, encoding: 'utf8' });
  expect(out.status, `relay pass: ${out.stderr}`).toBe(0);
}

function cleanUp(): void {
  const zones = "select id from table_zone where name like 'E2E Tbf %'";
  const tables = `select id from table_table where zone_id in (${zones})`;
  const reservations = "select id from reservation_reservation where guest_name like 'E2E Tbf %' or customer_id in (select id from customer_customer where name like 'E2E Tbf %' or (erased_at is not null and id in (select customer_id from reservation_reservation where table_id in (" + tables + "))))";
  const cards = `select id from customer_customer where name like 'E2E Tbf %' or id in (select customer_id from reservation_reservation where table_id in (${tables}))`;
  psql(
    [
      `create temp table e2e_tbf_sessions as select session_id as id from table_sessionmove where table_id in (${tables}) union select id from table_tablesession where table_id in (${tables}) or order_id in (select order_id from sale_orderline where sku like 'E2E-TBF-%')`,
      'create temp table e2e_tbf_orders as select order_id from table_tablesession where id in (select id from e2e_tbf_sessions) and order_id is not null',
      `create temp table e2e_tbf_cards as ${cards}`,
      `create temp table e2e_tbf_reservations as ${reservations} or table_id in (${tables})`,
      'delete from customer_orderlink where order_id in (select order_id from e2e_tbf_orders)',
      'delete from table_sessionmove where session_id in (select id from e2e_tbf_sessions)',
      `delete from table_hold where table_id in (${tables}) or source_ref in (select id::text from e2e_tbf_reservations)`,
      'update table_tablesession set transferred_from_id = null, merged_into_id = null, split_from_id = null where id in (select id from e2e_tbf_sessions)',
      'delete from table_tablesession where id in (select id from e2e_tbf_sessions)',
      'delete from reservation_reservation where id in (select id from e2e_tbf_reservations)',
      "delete from sale_orderline where order_id in (select order_id from e2e_tbf_orders) and sku not like 'E2E-%'",
      'delete from sale_order where id in (select order_id from e2e_tbf_orders) and id not in (select order_id from sale_orderline) and id not in (select order_id from sale_sale where order_id is not null)',
      `delete from table_table where id in (${tables})`,
      `delete from table_zone where id in (${zones})`,
      ...['customer_activity', 'customer_consent', 'customer_customer_groups', 'customer_customer_tags', 'customer_customfieldvalue', 'customer_orderlink', 'customer_purchase'].map(
        (table) => `delete from ${table} where customer_id in (select id from e2e_tbf_cards)`,
      ),
      'delete from customer_customer where id in (select id from e2e_tbf_cards)',
      `delete from reservation_timeslot where max_reservations = ${SENTINEL}`,
      "delete from schedule_overrideinterval where override_id in (select id from schedule_override where reason like 'E2E Tbf %')",
      "delete from schedule_override where reason like 'E2E Tbf %'",
    ].join('; '),
  );
}

const tile = (page: Page, id: string): Locator => shown(page).locator(`[data-testid=table-floor-tile-${id}]`);
const sheet = (page: Page): Locator => page.locator('ion-modal[data-testid=table-sheet]');
const guests = (page: Page): Locator => page.locator('[data-testid=table-guests]');

/** Closes the table's window if it is open (Escape, as a keyboard user would). */
async function closeSheet(page: Page): Promise<void> {
  if (await sheet(page).isVisible()) await page.keyboard.press('Escape');
  await expect(sheet(page)).toBeHidden();
}

async function tableNo(context: BrowserContext, number: string): Promise<TableRow> {
  const res = await api<TableRow>(context, A, 'GET', `/table/tables/detail?table=${number}&zone=${encodeURIComponent(ZONE)}`);
  expect(res.status, `table ${number}`).toBe(200);
  return res.data;
}

/** The plan in Service (or Edit plan), on the run's zone. */
async function floor(page: Page, mode: 'service' | 'edit' = 'service'): Promise<void> {
  if (!page.url().endsWith('/table/floor-plan')) await page.goto(`${A}/table/floor-plan`);
  await shown(page).locator(`[data-testid=table-floor-mode-${mode}]`).click();
  await shown(page).locator(`[data-testid=table-floor-zone-tab-${zoneId}]`).click();
}

/** Seats `count` at the free table `id` from the plan (Service). */
async function seat(page: Page, id: string, count: number): Promise<void> {
  await tile(page, id).click();
  await expect(sheet(page)).toBeVisible();
  await page.locator(`[data-testid=table-guests-quick-${count}]`).click();
  await expect(sheet(page)).toBeHidden();
  await expect(tile(page, id)).toContainText('Occupied');
}

async function openCheck(context: BrowserContext, number: string): Promise<string> {
  const row = await tableNo(context, number);
  expect(row.checks.length, `checks of table ${number}`).toBeGreaterThan(0);
  return row.checks[0].order_id!;
}

async function addCoffee(context: BrowserContext, orderId: string): Promise<string> {
  const added = await api<{ lines: { id: string; sku: string }[] }>(context, A, 'POST', '/sale/orders/add_line', { order_id: orderId, product_id: coffee.id, quantity: '1' });
  expect(added.status, JSON.stringify(added.data)).toBe(200);
  return added.data.lines.filter((line) => line.sku === SKU).at(-1)!.id;
}

test.beforeAll(async ({ browser }) => {
  cleanUp();
  const { context } = await ownerPage(browser, '/table/floor-plan');
  try {
    coffee = await createProduct(context, { name: `${TAG} coffee`, sku: SKU, price: 150, tax_category_key: 'restaurant.drink' });
    const settings = await api<Record<string, unknown>>(context, A, 'GET', '/table/settings');
    for (const key of ['prompt_guests_on_seat', 'timer_warning_minutes', 'timer_critical_minutes']) settingsBefore[key] = settings.data[key];
    // The book open all day today and tomorrow, where a run that waits for midnight books (a slot each day and a
    // change of Schedules open 24 h).
    const [today, tomorrow] = bookingDays(new Date());
    for (const day of [today, tomorrow]) {
      await post(context, '/reservation/time_slots', { day_of_week: day.weekday, start_time: '00:00', end_time: '23:59', max_reservations: SENTINEL });
    }
    await post(context, '/schedule/overrides', {
      start_date: today.date,
      end_date: tomorrow.date,
      reason: `${TAG} open`,
      is_closed: false,
      intervals: [{ open_time: '00:00', close_time: '00:00' }],
    });
  } finally {
    await context.close();
  }
});

test.afterAll(async ({ browser }) => {
  const { context } = await ownerPage(browser, '/table/settings');
  try {
    if (Object.keys(settingsBefore).length) await post(context, '/table/settings', settingsBefore, 200);
  } finally {
    await context.close();
  }
  cleanSales();
  cleanUp();
  cleanInventory();
});

test('TABLE-F01, F06: the zones of the room in Zones (add, rename, delete an empty one)', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/table/zones');
  try {
    const view = shown(page);
    await view.locator('[data-testid=table-zones-add]').click();
    const form = page.locator('ion-modal[data-testid=table-zone-form]');
    await form.locator('[data-testid=table-zone-form-name] input').fill(ZONE);
    await form.locator('[data-testid=table-zone-form-submit]').click();
    await expect(form).toBeHidden();
    await view.locator('[data-testid=table-zones-search] input').fill(RUN);
    await expect(view.locator('[data-testid=table-zones-row]', { hasText: ZONE })).toContainText('0 / 0');
    zoneId = psql(`select id from table_zone where name = '${ZONE}'`);
    await flowShots(page, ['TABLE-F01'], async () => {
      await expect(view.locator('[data-testid=table-zones-row]', { hasText: ZONE })).toBeVisible();
    });

    // A second zone renamed and deleted (empty: «Delete zone» is on).
    const spare = await post<{ id: string }>(context, '/table/zones', { name: `${TAG} Spare` });
    await expect(view.locator('[data-testid=table-zones-row]', { hasText: `${TAG} Spare` })).toBeVisible();
    await rowAction(page, 'table-zones', spare.id, 'edit');
    await form.locator('[data-testid=table-zone-form-name] input').fill(`${TAG} Terrace`);
    await form.locator('[data-testid=table-zone-form-submit]').click();
    await expect(form).toBeHidden();
    await expect(view.locator('[data-testid=table-zones-row]', { hasText: `${TAG} Terrace` })).toBeVisible();
    await rowAction(page, 'table-zones', spare.id, 'delete');
    const removal = page.locator('ion-modal[data-testid=table-zones-delete]');
    await expect(removal).toContainText('0 tables in this zone');
    await flowShots(page, ['TABLE-F06'], async () => {
      await expect(removal.locator('[data-testid=table-zones-delete-submit]')).toBeEnabled();
    });
    await removal.locator('[data-testid=table-zones-delete-submit]').click();
    await expect(removal).toBeHidden();
    await expect(view.locator('[data-testid=table-zones-row]', { hasText: `${TAG} Terrace` })).toHaveCount(0);
  } finally {
    await context.close();
  }
});

test('TABLE-F02, F03, F04, F05: tables on the plan (add, drag, edit, delete, block) and in Tables', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/table/floor-plan');
  try {
    await floor(page, 'edit');
    const add = page.locator('ion-modal[data-testid=table-add]');
    for (const number of ['', '2', '3']) {
      await shown(page).locator('[data-testid=table-floor-add]').click();
      if (number) await add.locator('[data-testid=table-add-table-number] input').fill(number);
      await add.locator('[data-testid=table-add-table-submit]').click();
      await expect(add).toBeHidden();
    }
    const one = await tableNo(context, '1');
    const two = await tableNo(context, '2');
    await expect(tile(page, one.id)).toContainText('4 pax');
    await flowShots(page, ['TABLE-F02'], async () => {
      await expect(tile(page, two.id)).toBeVisible();
    });

    // TABLE-F03: a drag saves the place at once and it stays after a reload.
    const box = await tile(page, one.id).boundingBox();
    if (!box) throw new Error('table 1 has no box');
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 40, box.y + box.height / 2 + 160, { steps: 8 });
    await page.mouse.up();
    await expect.poll(async () => (await tableNo(context, '1')).position_y).toBeGreaterThan(one.position_y + 100);
    const moved = await tableNo(context, '1');
    await page.reload();
    await floor(page, 'edit');
    await expect(tile(page, one.id)).toHaveCSS('top', `${moved.position_y}px`);
    await flowShots(page, ['TABLE-F03'], async () => {
      await expect(tile(page, one.id)).toBeVisible();
    });

    // TABLE-F04: «Edit table» (round, for six), then table 3 deleted after asking.
    await tile(page, one.id).click();
    const form = page.locator('ion-modal[data-testid=table-form]');
    await form.locator('[data-testid=table-form-capacity] input').fill('6');
    await pick(page, form.locator('[data-testid=table-form-shape]'), 'Round');
    await flowShots(page, ['TABLE-F04'], async () => {
      await expect(form.locator('[data-testid=table-form-submit]')).toBeEnabled();
    });
    await form.locator('[data-testid=table-form-submit]').click();
    await expect(form).toBeHidden();
    await expect(tile(page, one.id)).toHaveClass(/table-tile--round/);
    await expect(tile(page, one.id)).toContainText('6 pax');
    const three = await tableNo(context, '3');
    await tile(page, three.id).click();
    await form.locator('[data-testid=table-form-delete]').click();
    await page.locator('ion-modal[data-testid=table-form-delete-confirm] [data-testid=table-form-delete-confirm-submit]').click();
    await expect(tile(page, three.id)).toHaveCount(0);

    // TABLE-F05: table 2 blocked: grey on the plan and not seated; then back in service.
    await tile(page, two.id).click();
    await pick(page, form.locator('[data-testid=table-form-status]'), 'Blocked');
    await form.locator('[data-testid=table-form-submit]').click();
    await expect(form).toBeHidden();
    await floor(page, 'service');
    await expect(tile(page, two.id)).toContainText('Blocked');
    await tile(page, two.id).click();
    await expect(sheet(page).locator('[data-testid=table-sheet-blocked]')).toBeVisible();
    await flowShots(page, ['TABLE-F05'], async () => {
      await expect(sheet(page).locator('[data-testid=table-sheet-blocked]')).toBeVisible();
    });
    await sheet(page).locator('[data-testid=table-sheet-done]').click();
    await post(context, '/table/tables/update', { id: two.id, blocked: false }, 200);
    await expect(tile(page, two.id)).toContainText('Available');

    // The other door of TABLE-F02: the list of Tables.
    await page.goto(`${A}/table/tables`);
    const rows = shown(page).locator('[data-testid=table-tables-row]', { hasText: ZONE });
    await expect(rows).toHaveCount(2);
    await flowShots(page, ['TABLE-F02-list'], async () => {
      await expect(rows.first()).toBeVisible();
    });
  } finally {
    await context.close();
  }
});

test('TABLE-F08: the room settings (guests on seating, amber and red)', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/table/settings');
  try {
    const view = shown(page);
    const amber = view.locator('[data-testid=table-settings-timer_warning_minutes] input');
    const red = view.locator('[data-testid=table-settings-timer_critical_minutes] input');
    await amber.fill('50');
    await red.fill('40');
    await view.locator('[data-testid=table-settings-save]').click();
    await expect(view.locator('[data-testid=table-settings]')).toContainText('The red warning cannot come before the amber one.');
    await red.fill('80');
    await view.locator('[data-testid=table-settings-save]').click();
    await expect(view.locator('[data-testid=table-settings-saved]')).toBeVisible();
    const saved = await api<{ timer_warning_minutes: number; timer_critical_minutes: number }>(context, A, 'GET', '/table/settings');
    expect([saved.data.timer_warning_minutes, saved.data.timer_critical_minutes]).toEqual([50, 80]);
    await flowShots(page, ['TABLE-F08'], async () => {
      await expect(view.locator('[data-testid=table-settings-save]')).toBeVisible();
    });
  } finally {
    await context.close();
  }
});

test('TABLE-F09, F10, F32, F14, F11: seat a party with its customer, correct the guests, go to charge', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/table/floor-plan');
  try {
    const ana = await post<{ id: string; name: string }>(context, '/customer/customers', { name: `${TAG} Ana`, phone: `6${RUN.slice(-8).replace(/\D/g, '1').padStart(8, '1')}` });
    await floor(page);
    const one = await tableNo(context, '1');
    const two = await tableNo(context, '2');
    await flowShots(page, ['TABLE-F09'], async () => {
      await expect(tile(page, two.id)).toContainText('Available');
    });

    // TABLE-F10 with TABLE-F32: the guests prompt starts from the capacity; the customer goes on the check.
    await tile(page, one.id).click();
    await expect(guests(page).locator('[data-testid=table-guests-value]')).toContainText('6');
    await sheet(page).locator('[data-testid=customer-search-trigger]').click();
    const search = page.locator('ion-modal[data-testid=customer-search-modal]');
    await search.locator('[data-testid=customer-picker-search] input').fill(ana.name);
    await search.locator(`[data-testid=customer-picker-result-${ana.id}]`).click();
    await expect(search).toBeHidden();
    await flowShots(page, ['TABLE-F10'], async () => {
      await expect(guests(page)).toBeVisible();
    });
    await page.locator('[data-testid=table-guests-quick-3]').click();
    await expect(sheet(page)).toBeHidden();
    await expect(tile(page, one.id)).toContainText('3 pax · 0 min');
    const seated = await tableNo(context, '1');
    expect(seated.checks.map((check) => check.customer_name)).toEqual([ana.name]);
    const check = await api<{ label: string; status: string }>(context, A, 'GET', `/sale/orders/detail?order_id=${seated.checks[0].order_id}`);
    expect([check.data.label, check.data.status]).toEqual(['Table 1', 'open']);
    await tile(page, one.id).click();
    await expect(sheet(page)).toContainText(ana.name);
    await flowShots(page, ['TABLE-F32'], async () => {
      await expect(sheet(page).locator('[data-testid=table-sheet-summary]')).toBeVisible();
    });

    // TABLE-F14: the guests corrected.
    await sheet(page).locator('[data-testid=table-sheet-action-guests]').click();
    await expect(guests(page).locator('[data-testid=table-guests-value]')).toContainText('3');
    await page.locator('[data-testid=table-guests-more]').click();
    await page.locator('[data-testid=table-guests-confirm]').click();
    await expect(tile(page, one.id)).toContainText('4 pax');
    // Each size opens the window afresh: a new size may relay the page out under an open window.
    await flowShots(page, ['TABLE-F14'], async () => {
      await closeSheet(page);
      await tile(page, one.id).click();
      await sheet(page).locator('[data-testid=table-sheet-action-guests]').click();
      await expect(guests(page).locator('[data-testid=table-guests-value]')).toContainText('4');
    });
    await closeSheet(page);

    // TABLE-F11: «Charge» opens the till with the table's check on screen.
    await tile(page, one.id).click();
    await sheet(page).locator('[data-testid=table-sheet-action-charge]').click();
    await expect(shown(page).locator('[data-testid=pos-check-title]')).toHaveValue('Table 1');
    await flowShots(page, ['TABLE-F11'], async () => {
      await expect(shown(page).locator('[data-testid=pos-check-title]')).toHaveValue('Table 1');
    });
    await expect(shown(page).locator('[data-testid=pos-customer-chip]')).toContainText(ana.name);

    // sales#569 (TABLE-F32): back on the plan, the next free table starts its check without her.
    await page.goBack();
    await page.waitForURL(/\/table\/floor-plan$/);
    await floor(page);
    await seat(page, two.id, 2);
    await tile(page, two.id).click();
    await sheet(page).locator('[data-testid=table-sheet-action-charge]').click();
    await expect(shown(page).locator('[data-testid=pos-check-title]')).toHaveValue('Table 2');
    await expect(shown(page).locator('[data-testid=pos-customer-chip]')).toHaveCount(0);
    const next = (await tableNo(context, '2')).checks;
    expect(next.map((row) => row.customer_name)).toEqual([null]);
    await post(context, '/table/sessions/close', { id: next[0].id, order_id: next[0].order_id }, 200);
  } finally {
    await context.close();
  }
});

test('TABLE-F12: the till brings its open check to a table («Choose table»)', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/sale/pos');
  try {
    const two = await tableNo(context, '2');
    const order = await post<{ id: string }>(context, '/sale/orders', { label: '' });
    await addCoffee(context, order.id);
    await page.goto(`${A}/sale/pos?order=${order.id}`);
    const till = shown(page);
    await expect(till.locator('[data-testid^=pos-line-]').filter({ hasText: coffee.name }).first()).toBeVisible();
    // The check has its window on a wide screen and in the cart's drawer on a phone: the one on screen counts.
    const picker = page.locator('ion-modal[data-testid=pos-table]').filter({ visible: true });
    const option = picker.locator(`[data-testid=pos-table-tile-${two.id}]`);
    const choose = async () => {
      if (await picker.isVisible()) await page.keyboard.press('Escape');
      await expect(picker).toBeHidden();
      // On a phone the check lives behind the cart's button; the till lays itself out for a new size a frame late.
      await openTillCart(page);
      // The sheet slides in after its tables render: wait for Ionic to say it presented (its animation over).
      const presented = page.evaluate(
        () =>
          new Promise<void>((resolve, reject) => {
            document.addEventListener('ionModalDidPresent', () => resolve(), { once: true });
            setTimeout(() => reject(new Error('«Choose table» did not present within 10 s')), 10_000);
          }),
      );
      await till.locator('[data-testid=pos-table-trigger]').filter({ visible: true }).click();
      await presented;
      await expect(option).toContainText('Available');
      // The shot shows the sheet in place, not on its way up: read now, not retried, its table lies inside the window.
      const inside = await option.evaluate((el) => {
        const box = el.getBoundingClientRect();
        return box.top >= 0 && box.bottom <= window.innerHeight;
      });
      expect(inside, '«Choose table» has presented: its table lies inside the window').toBe(true);
    };
    // Each size opens «Choose table» afresh: a new size may relay the page out under an open window.
    await flowShots(page, ['TABLE-F12'], choose);
    await choose();
    await option.click();
    await expect(picker).toBeHidden();
    await expect(till.locator('[data-testid=pos-table-chip]').filter({ visible: true })).toHaveText('Table 2');
    const brought = await tableNo(context, '2');
    expect(brought.checks.map((row) => row.order_id)).toEqual([order.id]);
  } finally {
    await context.close();
  }
});

test('TABLE-F15, F16, F17: transfer a check, merge two tables and split a check', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/table/floor-plan');
  try {
    await floor(page);
    const one = await tableNo(context, '1');
    const two = await tableNo(context, '2');
    const orderOne = one.checks[0].order_id!;
    const orderTwo = two.checks[0].order_id!;
    await addCoffee(context, orderOne);

    // TABLE-F16: table 2 (the till's check) merged into table 1: one check of Sales with both lines.
    await tile(page, two.id).click();
    await sheet(page).locator('[data-testid=table-sheet-action-merge]').click();
    await expect(shown(page).locator('[data-testid=table-floor-pick]')).toContainText('Merge 2 with…');
    await flowShots(page, ['TABLE-F16'], async () => {
      await expect(shown(page).locator('[data-testid=table-floor-pick]')).toBeVisible();
    });
    await tile(page, one.id).click();
    await expect(tile(page, two.id)).toContainText('Available');
    const merged = await api<{ lines: { id: string }[] }>(context, A, 'GET', `/sale/orders/detail?order_id=${orderOne}`);
    expect(merged.data.lines).toHaveLength(2);
    const absorbed = await api<{ status: string }>(context, A, 'GET', `/sale/orders/detail?order_id=${orderTwo}`);
    expect(absorbed.data.status).toBe('voided');

    // TABLE-F15: table 1's check moves to table 2, with its guests and its title.
    await tile(page, one.id).click();
    await sheet(page).locator('[data-testid=table-sheet-action-transfer]').click();
    await expect(shown(page).locator('[data-testid=table-floor-pick]')).toContainText('Transfer 1 to…');
    await flowShots(page, ['TABLE-F15'], async () => {
      await expect(shown(page).locator('[data-testid=table-floor-pick]')).toBeVisible();
    });
    await tile(page, two.id).click();
    await expect(tile(page, two.id)).toContainText('Occupied');
    await expect(tile(page, one.id)).toContainText('Available');
    const moved = await tableNo(context, '2');
    expect(moved.checks.map((row) => row.order_id)).toEqual([orderOne]);
    const titled = await api<{ label: string }>(context, A, 'GET', `/sale/orders/detail?order_id=${orderOne}`);
    expect(titled.data.label).toBe('Table 2');

    // TABLE-F17: one line goes to a second check at the same table.
    const [firstLine] = merged.data.lines;
    await tile(page, two.id).click();
    await expect(sheet(page)).toBeVisible();
    await settled(page);
    await sheet(page).locator('[data-testid=table-sheet-action-split]').click();
    const mark = sheet(page).locator(`[data-testid=table-sheet-split-line-${firstLine.id}]`);
    await mark.click();
    await expect(mark).toHaveClass(/checkbox-checked/);
    await flowShots(page, ['TABLE-F17'], async () => {
      await expect(mark).toHaveClass(/checkbox-checked/);
    });
    await sheet(page).locator('[data-testid=table-sheet-split-confirm]').click();
    await expect.poll(async () => (await tableNo(context, '2')).checks.length).toBe(2);
    // The line marked went to the new check; the other stayed.
    const halves = (await tableNo(context, '2')).checks;
    const linesOf = async (orderId: string | null) =>
      (await api<{ lines: { id: string }[] }>(context, A, 'GET', `/sale/orders/detail?order_id=${orderId}`)).data.lines.map((line) => line.id);
    const split = await Promise.all(halves.map((half) => linesOf(half.order_id)));
    expect(split.map((lines) => lines.length).sort()).toEqual([1, 1]);
  } finally {
    await context.close();
  }
});

test('TABLE-F18, F19, F20: Sales charges, voids and deletes the checks of the tables', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/table/floor-plan');
  try {
    await floor(page);
    const two = await tableNo(context, '2');
    const [first, second] = two.checks;

    // TABLE-F18: one half charged, the table stays occupied; the other half charged, it frees by itself.
    const sale = await chargeByApi(context, { order_id: first.order_id, payments: [{ method: 'card' }] });
    await expect.poll(async () => (await tableNo(context, '2')).checks.length).toBe(1);
    await expect(tile(page, two.id)).toContainText('Occupied');
    await chargeByApi(context, { order_id: second.order_id, payments: [{ method: 'card' }] });
    await expect(tile(page, two.id)).toContainText('Available', { timeout: 15_000 });
    await flowShots(page, ['TABLE-F18'], async () => {
      await expect(tile(page, two.id)).toContainText('Available');
    });

    // TABLE-F19: the charge voided in Sales no longer counts in «Charged».
    await page.goto(`${A}/table/sessions`);
    const sessions = shown(page);
    await sessions.locator('[data-testid=table-sessions-segment-closed]').click();
    const charged = sessions.locator('[data-testid=table-sessions-row]', { hasText: '€1.50' });
    await expect(charged.first()).toBeVisible();
    const voided = await api(context, A, 'POST', '/sale/sales/void', { sale_id: sale.id, reason: `${TAG} wrong table` });
    expect(voided.status, JSON.stringify(voided.data)).toBe(200);
    await expect(charged).toHaveCount(1, { timeout: 15_000 });
    await flowShots(page, ['TABLE-F19'], async () => {
      await expect(sessions.locator('[data-testid=table-sessions-row]').first()).toBeVisible();
    });

    // TABLE-F20: a table's open check deleted in Sales frees the table.
    await floor(page);
    const one = await tableNo(context, '1');
    await seat(page, one.id, 2);
    const orderId = await openCheck(context, '1');
    await addCoffee(context, orderId);
    const removed = await api(context, A, 'POST', '/sale/orders/void', { order_id: orderId });
    expect(removed.status, JSON.stringify(removed.data)).toBe(200);
    await expect(tile(page, one.id)).toContainText('Available', { timeout: 15_000 });
    await flowShots(page, ['TABLE-F20'], async () => {
      await expect(tile(page, one.id)).toContainText('Available');
    });
  } finally {
    await context.close();
  }
});

test('TABLE-F21, F22, F23, F13, F24: the checks of the room in Sessions', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/table/floor-plan');
  try {
    await floor(page);
    const one = await tableNo(context, '1');

    // TABLE-F21: a party that ordered nothing, closed by hand from Sessions.
    await seat(page, one.id, 2);
    const check = (await tableNo(context, '1')).checks[0];
    await page.goto(`${A}/table/sessions`);
    const sessions = shown(page);
    await rowAction(page, 'table-sessions', check.id, 'close');
    const closing = page.locator('ion-modal[data-testid=table-sessions-close]');
    await expect(closing).toContainText('Table 1');
    await flowShots(page, ['TABLE-F21'], async () => {
      await expect(closing.locator('[data-testid=table-sessions-close-submit]')).toBeEnabled();
    });
    await closing.locator('[data-testid=table-sessions-close-submit]').click();
    await expect(closing).toBeHidden();
    expect((await tableNo(context, '1')).status).toBe('available');

    // TABLE-F22: the closed checks with what they charged; «Details».
    await sessions.locator('[data-testid=table-sessions-segment-closed]').click();
    await rowAction(page, 'table-sessions', check.id, 'detail');
    const detail = page.locator('ion-modal[data-testid=table-session-detail]');
    await expect(detail).toContainText(ZONE);
    await flowShots(page, ['TABLE-F22'], async () => {
      await expect(detail.locator('[data-testid=table-session-detail-done]')).toBeVisible();
    });
    await detail.locator('[data-testid=table-session-detail-done]').click();

    // TABLE-F23: the owner deletes it from the history.
    await rowAction(page, 'table-sessions', check.id, 'delete');
    const removal = page.locator('ion-modal[data-testid=table-sessions-delete]');
    await flowShots(page, ['TABLE-F23'], async () => {
      await expect(removal.locator('[data-testid=table-sessions-delete-submit]')).toBeEnabled();
    });
    await removal.locator('[data-testid=table-sessions-delete-submit]').click();
    await expect(removal).toBeHidden();
    await expect(sessions.locator(`[data-testid=table-sessions-row-${check.id}-detail], [data-testid=table-sessions-row-${check.id}-menu]`)).toHaveCount(0);

    // TABLE-F13: «Remove table» parks the check; the table frees and the check stays open in Sales.
    await floor(page);
    await seat(page, one.id, 2);
    const parked = (await tableNo(context, '1')).checks[0];
    await tile(page, one.id).click();
    await flowShots(page, ['TABLE-F13'], async () => {
      await expect(sheet(page).locator('[data-testid=table-sheet-action-park]')).toBeVisible();
    });
    await sheet(page).locator('[data-testid=table-sheet-action-park]').click();
    await expect(tile(page, one.id)).toContainText('Available');
    const order = await api<{ status: string }>(context, A, 'GET', `/sale/orders/detail?order_id=${parked.order_id}`);
    expect(order.data.status).toBe('open');

    // TABLE-F24: «Seat again» from Sessions, at a free table.
    await page.goto(`${A}/table/sessions`);
    await sessions.locator('[data-testid=table-sessions-segment-all]').click();
    await rowAction(page, 'table-sessions', parked.id, 'restore');
    const restore = page.locator('ion-modal[data-testid=table-restore]');
    // Table 1 of the run's zone: another zone of a shared database may have a table 1 too.
    await pick(page, restore.locator('[data-testid=table-restore-table]'), new RegExp(`^\\s*1 · ${ZONE}\\s*$`));
    await flowShots(page, ['TABLE-F24'], async () => {
      await expect(restore.locator('[data-testid=table-restore-submit]')).toBeEnabled();
    });
    await restore.locator('[data-testid=table-restore-submit]').click();
    await expect(restore).toBeHidden();
    expect((await tableNo(context, '1')).status).toBe('occupied');
    await post(context, '/table/sessions/close', { id: parked.id, order_id: parked.order_id }, 200);
  } finally {
    await context.close();
  }
});

test('TABLE-F25, F26, F27, F28: a reservation holds its table, moves it, frees it and is seated', async ({ browser }) => {
  const { soon, evening } = await reservationTimes();
  const { context, page } = await ownerPage(browser, '/table/floor-plan');
  try {
    await floor(page);
    // `soon` is chosen within the lead the plan paints Reserved from: the running server says the same lead.
    const room = await api<{ reserved_lead_minutes: number }>(context, A, 'GET', '/table/settings');
    expect(room.data.reserved_lead_minutes).toBe(RESERVED_LEAD_MINUTES);
    const one = await tableNo(context, '1');
    const two = await tableNo(context, '2');
    const reserve = async (guest: string, tableId: string, phone: string, at = soon) => {
      const made = await post<{ id: string }>(context, '/reservation/reservations', {
        guest_name: guest,
        guest_phone: phone,
        date: at.date,
        time: at.time,
        party_size: 2,
        table_id: tableId,
      });
      await post(context, '/reservation/reservations/confirm', { id: made.id }, 200);
      return made.id;
    };
    const hour = tile(page, one.id).locator('.table-tile__hold-time');

    // TABLE-F25: a reservation of tonight paints its hour on the plan in the page's language («8:00 PM» in
    // English). Always an afternoon one of today, whatever the time of the run (before noon an hour reads the
    // same in 24 h and in 12 h).
    const tonight = await painted(page, evening.time);
    expect(tonight).toContain('PM');
    const noa = await reserve(`${TAG} Noa`, one.id, `6${RUN.slice(-8).replace(/\D/g, '6').padStart(8, '6')}`, evening);
    await expect(hour).toContainText(tonight);
    await post(context, '/reservation/reservations/cancel', { id: noa }, 200);
    await expect(hour).toHaveCount(0);

    // TABLE-F25: confirmed, the table is Reserved (within the hour) with the name — a long one — and the hour.
    const marta = await reserve(`${TAG} Marta de la Concepción Fernández-Villaverde`, one.id, `6${RUN.slice(-8).replace(/\D/g, '2').padStart(8, '2')}`);
    await expect(tile(page, one.id)).toContainText('Reserved');
    await expect(hour).toContainText(await painted(page, soon.time));
    await flowShots(page, ['TABLE-F25'], async () => {
      await expect(hour).toBeVisible();
    });

    // TABLE-F26: the reservation moves to table 2: the hold goes with it.
    await post(context, '/reservation/reservations/update', { id: marta, table_id: two.id }, 200);
    await expect(tile(page, two.id)).toContainText('Reserved');
    await expect(tile(page, one.id)).toContainText('Available');
    await flowShots(page, ['TABLE-F26'], async () => {
      await expect(tile(page, two.id)).toContainText('Reserved');
    });

    // TABLE-F27: one cancelled and one not shown leave table 1 Available.
    const luis = await reserve(`${TAG} Luis`, one.id, `6${RUN.slice(-8).replace(/\D/g, '3').padStart(8, '3')}`);
    await expect(tile(page, one.id)).toContainText('Reserved');
    await post(context, '/reservation/reservations/cancel', { id: luis }, 200);
    await expect(tile(page, one.id)).toContainText('Available');
    const eva = await reserve(`${TAG} Eva`, one.id, `6${RUN.slice(-8).replace(/\D/g, '4').padStart(8, '4')}`);
    await expect(tile(page, one.id)).toContainText('Reserved');
    await post(context, '/reservation/reservations/no_show', { id: eva }, 200);
    await expect(tile(page, one.id)).toContainText('Available');
    await flowShots(page, ['TABLE-F27'], async () => {
      await expect(tile(page, one.id)).toContainText('Available');
    });

    // TABLE-F28: the party of table 2 arrives: the prompt starts from its party and seating spends the hold.
    await tile(page, two.id).click();
    await expect(sheet(page).locator('[data-testid=table-sheet-hold]')).toContainText('Marta');
    await expect(guests(page).locator('[data-testid=table-guests-value]')).toContainText('2');
    await flowShots(page, ['TABLE-F28'], async () => {
      await expect(guests(page)).toBeVisible();
    });
    await page.locator('[data-testid=table-guests-confirm]').click();
    await expect(tile(page, two.id)).toContainText('Occupied');
    expect((await tableNo(context, '2')).hold).toBeNull();
    const check = (await tableNo(context, '2')).checks[0];
    await post(context, '/table/sessions/close', { id: check.id, order_id: check.order_id }, 200);
  } finally {
    await context.close();
  }
});

test('TABLE-F31: a customer whose data is erased leaves the plan without her name', async ({ browser }) => {
  const { soon } = await reservationTimes();
  const { context, page } = await ownerPage(browser, '/table/floor-plan');
  try {
    await floor(page);
    const one = await tableNo(context, '1');
    const card = await post<{ id: string; name: string }>(context, '/customer/customers', { name: `${TAG} Sara`, phone: `6${RUN.slice(-8).replace(/\D/g, '5').padStart(8, '5')}` });
    const made = await post<{ id: string }>(context, '/reservation/reservations', {
      customer_id: card.id,
      date: soon.date,
      time: soon.time,
      party_size: 2,
      table_id: one.id,
    });
    await post(context, '/reservation/reservations/confirm', { id: made.id }, 200);
    await expect(tile(page, one.id)).toContainText(card.name);
    await post(context, '/customer/customers/erase', { id: card.id, reason: `${TAG} asked for it` }, 200);
    relayPass();
    await expect(tile(page, one.id)).toContainText('Deleted customer', { timeout: 15_000 });
    await expect(tile(page, one.id)).not.toContainText(card.name);
    await expect(tile(page, one.id)).toContainText('Reserved');
    expect((await tableNo(context, '1')).hold).toMatchObject({ label: '', erased: true });
    await flowShots(page, ['TABLE-F31'], async () => {
      await expect(tile(page, one.id)).toContainText('Deleted customer');
    });
    await post(context, '/reservation/reservations/cancel', { id: made.id }, 200);
  } finally {
    await context.close();
  }
});

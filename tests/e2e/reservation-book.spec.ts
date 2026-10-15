// Reservations in Chrome (apps/reservation/WORKBOOK.md), with the real Tables, Sales, Customers and
// Schedules apps: the owner takes a reservation for half an hour from now at a table of the floor plan
// (its card is made in Customers), confirms it — the floor plan shows the table Reserved, an hour before
// —, seats it from the book — the table is Occupied with its check open in Sales — and completes it; keeps
// the waitlist (add, contacted, convert); and reads the day's occupancy, adds a slot and blocks a date in
// Availability. Every screen in three viewports. What a run creates is named «E2E Rsv <stamp>…» (a zone,
// its table, guests, slots, a blocked date and a temporary change of Schedules open all day); `afterAll`
// removes all of it, with the holds, the table's checks and their orders.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, psql, shot, shown } from './helpers';
import { ownerPage, pick, post, rowAction } from './service-helpers';

const STAMP = Date.now().toString(36).toUpperCase();
const TAG = `E2E Rsv ${STAMP}`;
const ZONE = `${TAG} Room`;
const GUEST = `${TAG} Ana`;
const WAITING = `${TAG} Luis`;
const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1194 },
  { label: '1440', width: 1440, height: 900 },
];

/** The business's wall clock (Madrid in phase 1), `now + minutes`, rounded up to 5 minutes. */
function madrid(minutes = 0): { date: string; time: string; weekday: number } {
  const at = new Date(Date.now() + minutes * 60_000);
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Europe/Madrid',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    })
      .formatToParts(at)
      .map((part) => [part.type, part.value]),
  );
  const date = `${parts.year}-${parts.month}-${parts.day}`;
  const weekday = (new Date(`${date}T00:00:00Z`).getUTCDay() + 6) % 7;
  return { date, time: `${parts.hour}:${parts.minute}`, weekday };
}

function roundedUp(time: string): string {
  const [hours, minutes] = time.split(':').map(Number);
  const total = Math.min(hours * 60 + Math.ceil(minutes / 5) * 5, 23 * 60 + 55);
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
}

const TODAY = madrid();
const SOON = madrid(30);
const SOON_TIME = roundedUp(SOON.time);
/** The maximum every slot the run makes carries: how `cleanUp` knows them (slots have no name). */
const SENTINEL = 77;
/** The run's table and zone, made once per worker by `beforeAll`. */
let tableId = '';
let zoneId = '';

function cleanUp(): void {
  const reservations = `select id from reservation_reservation where guest_name like 'E2E Rsv %'`;
  const zones = "select id from table_zone where name like 'E2E Rsv %'";
  const tables = `select id from table_table where zone_id in (${zones})`;
  const sessions = `select id from table_tablesession where table_id in (${tables})`;
  const orders = `select order_id from table_tablesession where table_id in (${tables}) and order_id is not null`;
  const cards = "select id from customer_customer where name like 'E2E Rsv %'";
  psql(
    [
      `delete from table_hold where source_ref in (select id::text from reservation_reservation where guest_name like 'E2E Rsv %') or table_id in (${tables})`,
      `update reservation_waitlistentry set reservation_id = null where guest_name like 'E2E Rsv %'`,
      `delete from reservation_waitlistentry where guest_name like 'E2E Rsv %'`,
      `delete from reservation_reservation where id in (${reservations})`,
      "delete from reservation_blockeddate where reason like 'E2E Rsv %'",
      `create temp table e2e_rsv_orders as ${orders}`,
      'delete from customer_orderlink where order_id in (select order_id from e2e_rsv_orders)',
      `delete from table_sessionmove where session_id in (${sessions})`,
      `delete from table_tablesession where id in (${sessions})`,
      'delete from sale_orderline where order_id in (select order_id from e2e_rsv_orders)',
      'delete from sale_order where id in (select order_id from e2e_rsv_orders)',
      `delete from table_table where id in (${tables})`,
      `delete from table_zone where id in (${zones})`,
      ...['customer_activity', 'customer_consent', 'customer_customer_groups', 'customer_customer_tags', 'customer_customfieldvalue', 'customer_orderlink', 'customer_purchase'].map(
        (table) => `delete from ${table} where customer_id in (${cards})`,
      ),
      `delete from customer_customer where id in (${cards})`,
      `delete from reservation_timeslot where max_reservations = ${SENTINEL}`,
      "delete from schedule_overrideinterval where override_id in (select id from schedule_override where reason like 'E2E Rsv %')",
      "delete from schedule_override where reason like 'E2E Rsv %'",
    ].join('; '),
  );
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

/** The book open all day on the run's days — a slot each (the dev database has no other: only these runs
 *  make slots) and a temporary change of Schedules open 24 hours, so the run never depends on the dev
 *  database's hours — and a zone with its table 51. */
async function openTheBook(context: BrowserContext): Promise<void> {
  for (const weekday of new Set([TODAY.weekday, SOON.weekday])) {
    await post(context, '/reservation/time_slots', { day_of_week: weekday, start_time: '00:00', end_time: '23:59', max_reservations: SENTINEL });
  }
  await post(context, '/schedule/overrides', {
    start_date: TODAY.date,
    end_date: SOON.date,
    reason: `${TAG} open`,
    is_closed: false,
    intervals: [{ open_time: '00:00', close_time: '00:00' }],
  });
  const zone = await post<{ id: string }>(context, '/table/zones', { name: ZONE });
  const table = await post<{ id: string }>(context, '/table/tables', { zone_id: zone.id, number: '51', capacity: 4 });
  zoneId = zone.id;
  tableId = table.id;
}

const book = (page: Page) => shown(page).locator('[data-testid=reservation-list-row]', { hasText: GUEST });
const tile = (page: Page, id: string) => shown(page).locator(`[data-testid=table-floor-tile-${id}]`);

// Once per worker (a failed test restarts it): what a previous run left goes, and the book opens again.
test.beforeAll(async ({ browser }) => {
  cleanUp();
  const { context } = await ownerPage(browser, '/reservation/reservations');
  try {
    await openTheBook(context);
  } finally {
    await context.close();
  }
});
test.afterAll(cleanUp);

test('Take a reservation at a table, confirm it, see it Reserved on the plan, seat it and complete it', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/reservation/reservations');
  try {
    const view = shown(page);
    await expect(view.locator('[data-testid=reservation-day]')).toHaveAttribute('data-day', TODAY.date);

    // «New reservation»: the guest and her phone (Customers makes her card), half an hour from now, table 51.
    await view.locator('[data-testid=reservation-list-add]').click();
    const form = page.locator('[data-testid=reservation-form]');
    await form.locator('[data-testid=reservation-form-guest_name] input').fill(GUEST);
    await form.locator('[data-testid=reservation-form-guest_phone] input').fill(`6${String(Date.now()).slice(-8)}`);
    await form.locator('[data-testid=reservation-form-date] input').fill(SOON.date);
    await form.locator('[data-testid=reservation-form-time] input').fill(SOON_TIME);
    await form.locator('[data-testid=reservation-form-party_size] input').fill('3');
    await pick(page, 'reservation-form-table', '51', `51 (${ZONE})`);
    await form.locator('[data-testid=reservation-form-submit]').click();
    await expect(form).toBeHidden();

    if (SOON.date !== TODAY.date) await view.locator('[data-testid=reservation-day-next]').click();
    await expect(book(page)).toContainText('Pending');
    await expect(book(page)).toContainText(`51 (${ZONE})`);
    const id = (await book(page).getAttribute('data-id'))!;
    const card = psql(`select count(*) from customer_customer where name = '${GUEST}'`);
    expect(card).toBe('1');

    await rowAction(page, 'reservation-list', id, 'confirm');
    await expect(book(page)).toContainText('Confirmed');
    await shots(page, 'reservation-book', async () => {
      await expect(book(page)).toBeVisible();
    });

    // The floor plan: the table is held for her and painted Reserved (her time is within the hour).
    await page.goto(`${A}/table/floor-plan`);
    await shown(page).locator(`[data-testid=table-floor-zone-tab-${zoneId}]`).click();
    await expect(tile(page, tableId)).toContainText('Reserved');

    // Back to the book: «Seat» seats the table and opens its check; the plan says Occupied.
    await page.goto(`${A}/reservation/reservations`);
    if (SOON.date !== TODAY.date) await shown(page).locator('[data-testid=reservation-day-next]').click();
    await rowAction(page, 'reservation-list', id, 'seat');
    await expect(shown(page).locator('[data-testid=reservation-list-outcome]')).toContainText(`is seated at table 51 (${ZONE})`);
    await expect(book(page)).toContainText('Seated');
    const seated = await api<{ table_session_id: string | null }>(context, A, 'GET', `/reservation/reservations/detail?id=${id}`);
    expect(seated.data.table_session_id).not.toBeNull();
    await page.goto(`${A}/table/floor-plan`);
    await shown(page).locator(`[data-testid=table-floor-zone-tab-${zoneId}]`).click();
    await expect(tile(page, tableId)).toContainText('Occupied');

    await page.goto(`${A}/reservation/reservations`);
    if (SOON.date !== TODAY.date) await shown(page).locator('[data-testid=reservation-day-next]').click();
    await rowAction(page, 'reservation-list', id, 'complete');
    await expect(book(page)).toContainText('Completed');
  } finally {
    await context.close();
  }
});

test('Keep the waitlist: add a guest, mark her contacted and convert her into a reservation', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/reservation/waitlist');
  try {
    const view = shown(page);
    await view.locator('[data-testid=reservation-waitlist-add]').click();
    const form = page.locator('[data-testid=reservation-waitlist-form]');
    await form.locator('[data-testid=reservation-waitlist-form-guest_name] input').fill(WAITING);
    await form.locator('[data-testid=reservation-waitlist-form-date] input').fill(SOON.date);
    await form.locator('[data-testid=reservation-waitlist-form-preferred_time] input').fill(SOON_TIME);
    await form.locator('[data-testid=reservation-waitlist-form-submit]').click();
    await expect(form).toBeHidden();
    const row = view.locator('[data-testid=reservation-waitlist-row]', { hasText: WAITING });
    await expect(row).toContainText('Waiting');
    const id = (await row.getAttribute('data-id'))!;
    await rowAction(page, 'reservation-waitlist', id, 'contact');
    await expect(row).toContainText('Yes');
    await rowAction(page, 'reservation-waitlist', id, 'convert');
    await expect(row).toContainText('Converted');
    await expect(view.locator('[data-testid=reservation-waitlist-outcome]')).toContainText(`${WAITING} now has a reservation`);
    const booked = await api<{ rows: Array<{ guest_name: string; source: string }> }>(
      context,
      A,
      'GET',
      `/reservation/reservations?search=${encodeURIComponent(WAITING)}`,
    );
    expect(booked.data.rows.map((r) => [r.guest_name, r.source])).toEqual([[WAITING, 'waitlist']]);
    await shots(page, 'reservation-waitlist', async () => {
      await expect(row).toBeVisible();
    });
  } finally {
    await context.close();
  }
});

test('Availability: the day’s occupancy, a blocked date and a slot added and removed', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/reservation/availability');
  try {
    const view = shown(page);
    await view.locator('[data-testid=reservation-availability-date] input').fill(SOON.date);
    await expect(view.locator('[data-testid=reservation-availability-hours]')).toContainText('12:00 AM');
    const occupancy = view.locator('[data-testid=reservation-availability-occupancy-row]').first();
    await expect(occupancy).toContainText('12:00 AM–11:59 PM');

    // Block a far date for an event, then unblock it.
    await view.locator('[data-testid=reservation-availability-blocked-add]').click();
    const blockForm = page.locator('[data-testid=reservation-blocked-form]');
    await blockForm.locator('[data-testid=reservation-blocked-form-date] input').fill('2030-12-24');
    await blockForm.locator('[data-testid=reservation-blocked-form-reason] input').fill(`${TAG} event`);
    await blockForm.locator('[data-testid=reservation-blocked-form-submit]').click();
    await expect(blockForm).toBeHidden();
    const blocked = view.locator('[data-testid=reservation-availability-blocked-row]', { hasText: `${TAG} event` });
    await expect(blocked).toContainText('Whole day');

    // A slot on a weekday the run left free, then removed.
    const free = [0, 1, 2, 3, 4, 5, 6].find((day) => day !== TODAY.weekday && day !== SOON.weekday)!;
    await view.locator('[data-testid=reservation-availability-slots-add]').click();
    const slotForm = page.locator('[data-testid=reservation-slot-form]');
    await slotForm.locator('[data-testid=reservation-slot-form-day_of_week]').click();
    const names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
    await page.locator('ion-popover').getByText(names[free], { exact: true }).click();
    await slotForm.locator('[data-testid=reservation-slot-form-start_time] input').fill('03:00');
    await slotForm.locator('[data-testid=reservation-slot-form-end_time] input').fill('04:00');
    await slotForm.locator('[data-testid=reservation-slot-form-max_reservations] input').fill(String(SENTINEL));
    await slotForm.locator('[data-testid=reservation-slot-form-submit]').click();
    await expect(slotForm).toBeHidden();
    const slot = view.locator('[data-testid=reservation-availability-slots-row]', { hasText: '3:00 AM' });
    await expect(slot).toContainText('4:00 AM');

    await shots(page, 'reservation-availability', async () => {
      await expect(view.locator('[data-testid=reservation-availability-occupancy-row]').first()).toBeVisible();
    });

    const slotId = (await slot.getAttribute('data-id'))!;
    await rowAction(page, 'reservation-availability-slots', slotId, 'remove');
    await page.locator('[data-testid=reservation-availability-remove-slot-submit]').click();
    await expect(slot).toBeHidden();
    const blockedId = (await blocked.getAttribute('data-id'))!;
    await rowAction(page, 'reservation-availability-blocked', blockedId, 'remove');
    await page.locator('[data-testid=reservation-availability-remove-blocked-submit]').click();
    await expect(blocked).toBeHidden();
  } finally {
    await context.close();
  }
});

test('Settings: the owner changes the default duration and it is kept', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/reservation/settings');
  const before = await api<{ default_duration_minutes: number }>(context, A, 'GET', '/reservation/settings');
  try {
    const view = shown(page);
    const duration = view.locator('[data-testid=reservation-settings-default_duration_minutes] input');
    await duration.fill('105');
    await view.locator('[data-testid=reservation-settings-save]').click();
    await expect(view.locator('[data-testid=reservation-settings-saved]')).toContainText('Settings saved.');
    const after = await api<{ default_duration_minutes: number }>(context, A, 'GET', '/reservation/settings');
    expect(after.data.default_duration_minutes).toBe(105);
    await shots(page, 'reservation-settings', async () => {
      await expect(duration).toBeVisible();
    });
  } finally {
    await api(context, A, 'POST', '/reservation/settings', { default_duration_minutes: before.data.default_duration_minutes });
    await context.close();
  }
});

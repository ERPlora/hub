// Reservations in Chrome (apps/reservation/WORKBOOK.md), with the real Tables, Sales, Customers and
// Schedules apps: the owner takes a reservation for half an hour from now at a table of the floor plan
// (its card is made in Customers), confirms it — the floor plan shows the table Reserved, an hour before
// —, seats it from the book — the table is Occupied with its check open in Sales — and completes it; keeps
// the waitlist (add, contacted, convert); and reads the day's occupancy, adds a slot and blocks a date in
// Availability. It also edits, cancels with a reason, marks a no-show and deletes (F08–F10, F20), confirms by
// itself (F04), and seats a late party leaving the next reservation of its table Reserved (F11). Every screen in
// three viewports, one capture per flow (`APP-RESERVATION-<flow>-<width>`). What a run creates is named «E2E Rsv
// <stamp>…» (a zone, its table, guests, slots, a blocked date and a temporary change of Schedules open all day);
// `afterAll` removes all of it, with the holds, the table's checks and their orders.
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
  { label: '834', width: 834, height: 1112 },
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

/** Screenshots of the page in the three viewports, each once `ready` says it painted: `APP-RESERVATION-<flow>-<width>`. */
async function shots(page: Page, flow: string, ready: () => Promise<void>): Promise<void> {
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await ready();
    await page.screenshot({ path: shot(`APP-RESERVATION-${flow}-${viewport.label}`), fullPage: true });
  }
  await page.setViewportSize({ width: 1280, height: 860 });
}

/** A reservation taken through the API (the form is the first test's), on the run's day and with its tag. */
async function bookByApi(context: BrowserContext, guest: string, time: string, more: Record<string, unknown> = {}) {
  return post<{ id: string; status: string }>(context, '/reservation/reservations', {
    guest_name: guest,
    guest_phone: `6${String(Date.now()).slice(-8)}`,
    date: SOON.date,
    time,
    party_size: 2,
    ...more,
  });
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

// flow: RESERVATION-F06, RESERVATION-F23, RESERVATION-F07, RESERVATION-F11, RESERVATION-F12
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
    await shots(page, 'RESERVATION-F23', async () => {
      await expect(form.locator('[data-testid=reservation-form-table]')).toBeVisible();
    });
    await shots(page, 'RESERVATION-F06', async () => {
      await expect(form.locator('[data-testid=reservation-form-guest_name]')).toBeVisible();
    });
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
    await shots(page, 'RESERVATION-F07', async () => {
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
    await shots(page, 'RESERVATION-F12', async () => {
      await expect(book(page)).toBeVisible();
    });
  } finally {
    await context.close();
  }
});

// flow: RESERVATION-F14, RESERVATION-F15, RESERVATION-F16
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
    await shots(page, 'RESERVATION-F14', async () => {
      await expect(row).toBeVisible();
    });
    const id = (await row.getAttribute('data-id'))!;
    await rowAction(page, 'reservation-waitlist', id, 'contact');
    await expect(row).toContainText('Yes');

    // Somebody who no longer waits is removed, after confirming.
    const gone = await post<{ id: string }>(context, '/reservation/waitlist', {
      guest_name: `${TAG} Mar`,
      date: SOON.date,
      preferred_time: SOON_TIME,
      party_size: 2,
    });
    const goneRow = view.locator(`[data-testid=reservation-waitlist-row][data-id="${gone.id}"]`);
    await expect(goneRow).toBeVisible();
    await shots(page, 'RESERVATION-F15', async () => {
      await expect(row).toContainText('Yes');
    });
    await rowAction(page, 'reservation-waitlist', gone.id, 'remove');
    await page.locator('[data-testid=reservation-waitlist-remove-submit]').click();
    await expect(goneRow).toBeHidden();

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
    await shots(page, 'RESERVATION-F16', async () => {
      await expect(row).toBeVisible();
    });
  } finally {
    await context.close();
  }
});

// flow: RESERVATION-F05, RESERVATION-F02, RESERVATION-F01
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
    await shots(page, 'RESERVATION-F02', async () => {
      await expect(blocked).toBeVisible();
    });

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

    await shots(page, 'RESERVATION-F01', async () => {
      await expect(slot).toBeVisible();
    });
    await shots(page, 'RESERVATION-F05', async () => {
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

// flow: RESERVATION-F03
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
    await shots(page, 'RESERVATION-F03', async () => {
      await expect(duration).toBeVisible();
    });
  } finally {
    await api(context, A, 'POST', '/reservation/settings', { default_duration_minutes: before.data.default_duration_minutes });
    await context.close();
  }
});

// flow: RESERVATION-F04
test('Settings: with «Confirm new reservations automatically» a new reservation is born Confirmed', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/reservation/settings');
  try {
    const view = shown(page);
    const toggle = view.locator('[data-testid=reservation-settings-auto_confirm]');
    await expect(toggle).toHaveAttribute('aria-checked', 'false');
    await toggle.click();
    await view.locator('[data-testid=reservation-settings-save]').click();
    await expect(view.locator('[data-testid=reservation-settings-saved]')).toContainText('Settings saved.');
    await shots(page, 'RESERVATION-F04', async () => {
      await expect(toggle).toHaveAttribute('aria-checked', 'true');
    });
    const born = await bookByApi(context, `${TAG} Auto`, SOON_TIME);
    expect(born.status).toBe('confirmed');
  } finally {
    await api(context, A, 'POST', '/reservation/settings', { auto_confirm: false });
    await context.close();
  }
});

// flow: RESERVATION-F08, RESERVATION-F09, RESERVATION-F10, RESERVATION-F20
test('Edit a reservation, cancel one with a reason, mark a no-show and delete one', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/reservation/reservations');
  try {
    const edited = await bookByApi(context, `${TAG} Eva`, SOON_TIME);
    const cancelled = await bookByApi(context, `${TAG} Pau`, SOON_TIME);
    const absent = await bookByApi(context, `${TAG} Rui`, SOON_TIME);
    const view = shown(page);
    if (SOON.date !== TODAY.date) await view.locator('[data-testid=reservation-day-next]').click();
    const rowOf = (id: string) => view.locator(`[data-testid=reservation-list-row][data-id="${id}"]`);
    await expect(rowOf(edited.id)).toBeVisible();

    // Edit: the party grows from 2 to 5 (F08).
    await rowAction(page, 'reservation-list', edited.id, 'edit');
    const form = page.locator('[data-testid=reservation-form]');
    await form.locator('[data-testid=reservation-form-party_size] input').fill('5');
    await shots(page, 'RESERVATION-F08', async () => {
      await expect(form.locator('[data-testid=reservation-form-party_size] input')).toHaveValue('5');
    });
    await form.locator('[data-testid=reservation-form-submit]').click();
    await expect(form).toBeHidden();
    await expect(rowOf(edited.id)).toContainText('5');

    // Cancel with a reason (F09).
    await rowAction(page, 'reservation-list', cancelled.id, 'cancel');
    const reason = page.locator('[data-testid=reservation-step-cancel-reason] textarea');
    await reason.fill('Plans changed');
    await page.locator('[data-testid=reservation-step-cancel-submit]').click();
    await expect(rowOf(cancelled.id)).toContainText('Cancelled');
    const detail = await api<{ cancellation_reason: string }>(context, A, 'GET', `/reservation/reservations/detail?id=${cancelled.id}`);
    expect(detail.data.cancellation_reason).toBe('Plans changed');
    await shots(page, 'RESERVATION-F09', async () => {
      await expect(rowOf(cancelled.id)).toBeVisible();
    });

    // No-show (F10).
    await rowAction(page, 'reservation-list', absent.id, 'no_show');
    await page.locator('[data-testid=reservation-step-no_show-submit]').click();
    await expect(rowOf(absent.id)).toContainText('No-show');
    await shots(page, 'RESERVATION-F10', async () => {
      await expect(rowOf(absent.id)).toBeVisible();
    });

    // Delete for good, after confirming (F20).
    await rowAction(page, 'reservation-list', edited.id, 'delete');
    await page.locator('[data-testid=reservation-step-delete-submit]').click();
    await expect(rowOf(edited.id)).toBeHidden();
    await shots(page, 'RESERVATION-F20', async () => {
      await expect(rowOf(absent.id)).toBeVisible();
    });
    const deleted = await api(context, A, 'GET', `/reservation/reservations/detail?id=${edited.id}`);
    expect(deleted.status).toBe(404);
  } finally {
    await context.close();
  }
});

// flow: RESERVATION-F11
test('Seating a party leaves the next reservation of its table held: Reserved again when the party leaves', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/reservation/reservations');
  try {
    // A soon, for 40 minutes, and B right after it, both at a table of their own (52) and confirmed: both already
    // paint it.
    const own = await post<{ id: string }>(context, '/table/tables', { zone_id: zoneId, number: '52', capacity: 4 });
    const first = await bookByApi(context, `${TAG} Ada`, roundedUp(madrid(5).time), { table_id: own.id, duration_minutes: 40 });
    const next = await bookByApi(context, `${TAG} Bea`, roundedUp(madrid(50).time), { table_id: own.id });
    for (const reservation of [first, next]) {
      await post(context, '/reservation/reservations/confirm', { id: reservation.id }, 200);
    }
    const view = shown(page);
    if (madrid(5).date !== TODAY.date) await view.locator('[data-testid=reservation-day-next]').click();
    await rowAction(page, 'reservation-list', first.id, 'seat');
    await expect(view.locator('[data-testid=reservation-list-outcome]')).toContainText(`is seated at table 52 (${ZONE})`);
    expect(psql(`select status from table_hold where source_ref = '${next.id}'`)).toBe('held');

    // A leaves: her empty check is closed and the table is Reserved again, for B.
    const seated = await api<{ table_session_id: string }>(context, A, 'GET', `/reservation/reservations/detail?id=${first.id}`);
    await post(context, '/table/sessions/close', { id: seated.data.table_session_id }, 200);
    await page.goto(`${A}/table/floor-plan`);
    await shown(page).locator(`[data-testid=table-floor-zone-tab-${zoneId}]`).click();
    await expect(tile(page, own.id)).toContainText('Reserved');
    await shots(page, 'RESERVATION-F11', async () => {
      await expect(tile(page, own.id)).toContainText('Reserved');
    });
  } finally {
    await context.close();
  }
});

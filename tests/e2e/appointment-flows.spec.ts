// flow: APPOINTMENT-F01 APPOINTMENT-F02 APPOINTMENT-F03 APPOINTMENT-F04 APPOINTMENT-F05 APPOINTMENT-F07 APPOINTMENT-F08 APPOINTMENT-F09 APPOINTMENT-F10 APPOINTMENT-F11 APPOINTMENT-F12 APPOINTMENT-F13 APPOINTMENT-F14 APPOINTMENT-F15 APPOINTMENT-F16 APPOINTMENT-F17 APPOINTMENT-F19 APPOINTMENT-F20 APPOINTMENT-F22 APPOINTMENT-F27
// Every flow of Appointments that has a screen, end to end in each of the three sizes (apps/appointment/WORKBOOK.md),
// with one screenshot per flow and size (`APP-APPOINTMENT-<flow>-<width>`), against the real Customers, Services,
// Staff, Schedules and Sales: the owner of hub `a` saves the settings (F19); books from «Add appointment» with a
// free time (F02, F01); edits its notes and its time (F22, F04) and reads its history (F10); confirms a booking the
// customer made herself (F03); starts and completes the first one (F07, F08); charges the second at the till
// (F17); cancels a third with its reason (F05) and deletes it (F11); marks a past one as a no-show (F09). On «By
// professional» the day paints a block (F16) and the week its appointments (F27). In «Repeating» a series is created
// (F12), booked again (F13), edited from an occurrence on (F14), paused, reactivated and deleted (F15); the
// customer's card shows her visits (F20). Each size works on a day of its own; what it creates is «E2E Apf …»,
// removed before and after, and the settings of Citas are put back at the end.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, psql, shot, shown } from './helpers';
import { FLOW_VIEWPORTS, ownerPage, pick, post, rowAction, settled } from './service-helpers';

const TAG = 'E2E Apf';
const RUN = Date.now().toString(36);
const named = (label: string): string => `${TAG} ${label} ${RUN}`;

/** A Monday `weeks` + five weeks ahead (inside the 90 days of advance), as `YYYY-MM-DD`. */
function aMonday(weeks: number): string {
  const day = new Date();
  day.setUTCDate(day.getUTCDate() + 35 + 7 * weeks + ((8 - day.getUTCDay()) % 7));
  return day.toISOString().slice(0, 10);
}

/** Two days ago, as `YYYY-MM-DD`: a day whose appointments are already in the past on the business's clock. */
const PAST = new Date(Date.now() - 2 * 86_400_000).toISOString().slice(0, 10);

function cleanUp(): void {
  const customers = `select id from customer_customer where name like '${TAG}%'`;
  const appointments = `select id from appointment_appointment where customer_id in (${customers})`;
  const series = `select id from appointment_recurring where customer_id in (${customers})`;
  const services = `select id from service_service where name like '${TAG}%'`;
  const members = `select id from staff_member where first_name like '${TAG}%'`;
  const orders = `select id from sale_order where appointment_id in (${appointments})`;
  psql(
    [
      `delete from sale_orderline where order_id in (${orders})`,
      `delete from sale_order where id in (${orders})`,
      `delete from appointment_history where appointment_id in (${appointments})`,
      `delete from appointment_appointmentservice where appointment_id in (${appointments})`,
      `delete from appointment_appointment where id in (${appointments})`,
      `delete from appointment_recurringservice where recurring_id in (${series})`,
      `delete from appointment_recurring where id in (${series})`,
      `delete from appointment_blockedtime where title like '${TAG}%'`,
      `delete from schedule_specialdayinterval where special_day_id in (select id from schedule_specialday where name like '${TAG}%')`,
      `delete from schedule_specialday where name like '${TAG}%'`,
      `delete from service_assignment where service_id in (${services}) or member_id in (${members})`,
      `delete from service_service where name like '${TAG}%'`,
      `delete from staff_member where first_name like '${TAG}%'`,
      `delete from customer_activity where customer_id in (${customers})`,
      `delete from customer_consent where customer_id in (${customers})`,
      `delete from customer_customer where name like '${TAG}%'`,
    ].join('; '),
  );
}

/** The business's own settings of Citas, kept before the spec changes them and put back after. */
let savedSettings: Record<string, unknown> | null = null;

test.beforeAll(async ({ browser }) => {
  cleanUp();
  const { context } = await ownerPage(browser, '/appointment/agenda');
  try {
    const current = await api<Record<string, unknown>>(context, A, 'GET', '/appointment/settings');
    expect(current.status).toBe(200);
    // The zone is the business's, not a setting of Citas.
    savedSettings = Object.fromEntries(Object.entries(current.data).filter(([key]) => key !== 'timezone'));
    // The days in the past this spec marks as no-shows open from 09:00, whatever the business's week says.
    await openDay(context, PAST);
  } finally {
    await context.close();
  }
});

test.afterAll(async ({ browser }) => {
  cleanUp();
  if (!savedSettings) return;
  const { context } = await ownerPage(browser, '/appointment/agenda');
  try {
    await post(context, '/appointment/settings', savedSettings, 200);
  } finally {
    await context.close();
  }
});

interface Cast {
  customer: { id: string; name: string };
  service: { id: string; name: string };
  member: { id: string; full_name: string };
}

async function openDay(context: BrowserContext, day: string): Promise<void> {
  await post(context, '/schedule/special_days', {
    date: day,
    name: named(`Open ${day}`),
    is_closed: false,
    intervals: [{ open_time: '09:00', close_time: '18:00' }],
  });
}

/** Through each app's own API: a card, a service a professional performs, and `day` open from 09:00 to 18:00. */
async function cast(context: BrowserContext, label: string, day: string): Promise<Cast> {
  const customer = await post<{ id: string; name: string }>(context, '/customer/customers', {
    name: named(`Lucía ${label}`),
    phone: `6${String(Date.now()).slice(-8)}`,
  });
  const service = await post<{ id: string; name: string }>(context, '/service/services', {
    name: named(`Haircut ${label}`),
    price: 2000,
    duration_minutes: 30,
    tax_category_key: 'service.generic',
  });
  const member = await post<{ id: string; full_name: string }>(context, '/staff/members', {
    first_name: named(`Ana ${label}`),
    last_name: 'Stylist',
  });
  await post(context, '/service/assignments/assign', { service_id: service.id, member_id: member.id }, 200);
  await openDay(context, day);
  return { customer, service, member };
}

/** Books `who` at `start` (`YYYY-MM-DDTHH:MM`) through the API, as the front desk or with `source`. */
async function book(context: BrowserContext, who: Cast, start: string, source = 'counter'): Promise<{ id: string; number: string; status: string }> {
  return post(context, '/appointment/appointments', {
    customer_id: who.customer.id,
    services: [{ service_id: who.service.id }],
    staff_id: who.member.id,
    start,
    source,
  });
}

const statusOf = (id: string): string => psql(`select status from appointment_appointment where id = '${id}'`);

async function goToDay(page: Page, day: string): Promise<void> {
  const calendar = shown(page).locator('[data-testid=appointment-toolbar-calendar] input');
  await calendar.fill(day);
  await calendar.press('Tab');
  await expect(shown(page).locator('[data-testid=appointment-toolbar-date]')).not.toBeEmpty();
}

/** «Customer» of the open panel `modal`: her card, searched by name in Customers' own search. */
async function chooseCustomer(page: Page, modal: string, who: Cast): Promise<void> {
  await page.locator(`ion-modal[data-testid=${modal}] [data-testid=customer-search-trigger]`).click();
  const search = page.locator('ion-modal[data-testid=customer-search-modal]');
  await search.locator('[data-testid=customer-picker-search] input').fill(who.customer.name);
  await search.locator(`[data-testid=customer-picker-result-${who.customer.id}]`).click();
  await expect(search).toBeHidden();
}

/** Waits until the agenda's row of appointment `id` shows `status`: the live list has caught up with the change. */
async function showsStatus(page: Page, id: string, status: string): Promise<void> {
  await expect(shown(page).locator(`[data-testid=appointment-list-row][data-id="${id}"]`).first()).toContainText(status);
}

/** The fields of `form` whose label does not fit and is cut with «…» (none should be). */
async function cutLabels(form: Locator): Promise<string[]> {
  return form.locator('ion-input, ion-select, ion-textarea').evaluateAll((fields) =>
    fields.flatMap((field) => {
      const label = field.shadowRoot?.querySelector('.label-text') ?? field.querySelector('.label-text');
      return label && label.scrollWidth > label.clientWidth + 1 ? [field.getAttribute('data-testid') ?? field.tagName] : [];
    }),
  );
}

/** The searched word of a name built by `named` («E2E Apf <word> …»). */
const word = (name: string): string => name.split(' ')[2];

/** `day` plus `days`, as `YYYY-MM-DD`. */
const plus = (day: string, days: number): string => new Date(Date.parse(`${day}T00:00:00Z`) + days * 86_400_000).toISOString().slice(0, 10);

FLOW_VIEWPORTS.forEach((vp, index) => {
  // A Monday of its own per size; the grid's test opens the Tuesday and the series' the Wednesday after.
  const DAY = aMonday(3 * index);
  const GRID_DAY = plus(DAY, 1);
  const SERIES_DAY = plus(DAY, 2);
  const capture = async (page: Page, flow: string): Promise<void> => {
    await settled(page);
    await page.screenshot({ path: shot(`APP-APPOINTMENT-${flow}-${vp.label}`), animations: 'disabled' });
  };

  test(`Appointments flows at ${vp.label}: settings, booking, its states, charge, cancel, delete and no-show`, async ({ browser }) => {
    test.setTimeout(300_000);
    const { context, page } = await ownerPage(browser, '/appointment/settings', vp);
    try {
      // APPOINTMENT-F19: a setting changed and saved; only what changed is sent.
      const duration = shown(page).locator('[data-testid=appointment-settings-default_duration] input');
      await expect(duration).toBeVisible();
      await duration.fill(String(45 + index));
      await shown(page).locator('[data-testid=appointment-settings-save]').click();
      await expect(shown(page).locator('[data-testid=appointment-settings-saved]')).toContainText('Settings saved.');
      await capture(page, 'APPOINTMENT-F19');
      // Every field and switch fits the screen: a long label wraps, it never pushes the form past the edge.
      const overflow = await shown(page)
        .locator('form[data-testid=appointment-settings]')
        .evaluate((form) => form.scrollWidth - form.clientWidth);
      expect(overflow, `the settings form overflows at ${vp.label}`).toBeLessThanOrEqual(0);
      expect(psql('select default_duration from appointment_settings')).toBe(String(45 + index));
      // The customer's own bookings wait for the business (F03).
      await post(context, '/appointment/settings', { auto_confirm_online: false }, 200);

      const who = await cast(context, vp.label, DAY);
      await page.goto(`${A}/appointment/agenda`);
      await goToDay(page, DAY);
      const view = shown(page);
      await view.locator('[data-testid=appointment-list-empty], [data-testid=appointment-list-row]').first().waitFor({ state: 'visible' });

      // APPOINTMENT-F02, F01: «Add appointment» with her card, the service, its professional and a free time.
      await view.locator('[data-testid=appointment-list-add]').click();
      const form = page.locator('ion-modal[data-testid=appointment-form]');
      await chooseCustomer(page, 'appointment-form', who);
      await pick(page, 'appointment-form-service-add', word(who.service.name), who.service.name);
      await pick(page, 'appointment-form-staff', word(who.member.full_name), who.member.full_name);
      const dayInput = form.locator('[data-testid=appointment-form-day] input');
      await dayInput.fill(DAY);
      await dayInput.press('Tab');
      const free = form.locator('[data-testid=appointment-slots-time]', { hasText: /^10:00\s?AM$/ });
      await expect(free).toBeVisible();
      expect(await cutLabels(form), `labels cut in the appointment form at ${vp.label}`).toEqual([]);
      await capture(page, 'APPOINTMENT-F02');
      await free.click();
      await form.locator('[data-testid=appointment-form-submit]').click();
      await expect(form).toBeHidden();
      const first = JSON.parse(
        psql(`select row_to_json(a) from appointment_appointment a where customer_id = '${who.customer.id}' order by start limit 1`),
      ) as { id: string; number: string; status: string };
      expect(first.status).toBe('confirmed');
      await expect(view.getByText(first.number).first()).toBeVisible();
      await capture(page, 'APPOINTMENT-F01');
      // appointments#93, #206, #243: the day's bar is one or two rows (three on a phone), never half the screen
      // above the first appointment, as the old agenda.
      const bar = (await view.locator('[data-testid=appointment-toolbar]').boundingBox())!;
      expect(bar.height, `the day's bar at ${vp.label}`).toBeLessThan(vp.width < 640 ? 190 : 130);

      // APPOINTMENT-F22, F04: «Edit» changes its notes and moves it an hour; the panel shows the history below.
      await rowAction(page, 'appointment-list', first.id, 'edit');
      await expect(form).toBeVisible();
      await expect(form.locator('ion-title')).toHaveText('Edit appointment');
      await form.locator('[data-testid=appointment-form-notes] textarea').fill('Bring the colour reference');
      await capture(page, 'APPOINTMENT-F22');
      await form.locator('[data-testid=appointment-form-time] input').fill('11:00');
      await capture(page, 'APPOINTMENT-F04');
      await form.locator('[data-testid=appointment-form-submit]').click();
      await expect(form).toBeHidden();
      await expect
        .poll(() => psql(`select to_char(start at time zone 'Europe/Madrid', 'HH24:MI') || ' ' || notes from appointment_appointment where id = '${first.id}'`))
        .toBe('11:00 Bring the colour reference');

      // APPOINTMENT-F10: «History» says what changed, on the business's clock.
      await rowAction(page, 'appointment-list', first.id, 'history');
      const history = page.locator('ion-modal[data-testid=appointment-history-modal]');
      await expect(history).toBeVisible();
      await expect(history).toContainText('Time changed');
      await expect(history).toContainText('Booked');
      await capture(page, 'APPOINTMENT-F10');
      await page.keyboard.press('Escape');
      await expect(history).toBeHidden();

      // APPOINTMENT-F03: a booking she made herself waits («N to confirm») until the business confirms it.
      const online = await book(context, who, `${DAY}T15:00`, 'online');
      expect(online.status).toBe('pending');
      await expect(view.locator('[data-testid=appointment-toolbar-to-confirm]')).toContainText('to confirm');
      await rowAction(page, 'appointment-list', online.id, 'confirm');
      await expect.poll(() => statusOf(online.id)).toBe('confirmed');
      await showsStatus(page, online.id, 'Confirmed');
      await capture(page, 'APPOINTMENT-F03');

      // APPOINTMENT-F07, F08: the first one starts and is completed.
      await rowAction(page, 'appointment-list', first.id, 'start');
      await expect.poll(() => statusOf(first.id)).toBe('in_progress');
      await showsStatus(page, first.id, 'In progress');
      await capture(page, 'APPOINTMENT-F07');
      await rowAction(page, 'appointment-list', first.id, 'complete');
      await expect.poll(() => statusOf(first.id)).toBe('completed');
      await showsStatus(page, first.id, 'Completed');
      await capture(page, 'APPOINTMENT-F08');

      // APPOINTMENT-F05, F11: a third one is cancelled with its reason, then deleted (asked first).
      const third = await book(context, who, `${DAY}T16:00`);
      await rowAction(page, 'appointment-list', third.id, 'cancel');
      const cancel = page.locator('ion-modal[data-testid=appointment-cancel]');
      await expect(cancel).toBeVisible();
      await expect(cancel).toContainText(`Cancel ${who.customer.name}'s appointment`);
      await cancel.locator('[data-testid=appointment-cancel-reason] textarea').fill('Ill');
      await capture(page, 'APPOINTMENT-F05');
      await cancel.locator('[data-testid=appointment-cancel-submit]').click();
      await expect.poll(() => statusOf(third.id)).toBe('cancelled');
      await rowAction(page, 'appointment-list', third.id, 'delete');
      const remove = page.locator('ion-modal[data-testid=appointment-delete]');
      await expect(remove).toBeVisible();
      await expect(remove).toContainText(third.number);
      await capture(page, 'APPOINTMENT-F11');
      await remove.locator('[data-testid=appointment-delete-submit]').click();
      await expect.poll(() => psql(`select deleted_at is not null from appointment_appointment where id = '${third.id}'`)).toBe('t');
      await expect(view.getByText(third.number)).toHaveCount(0);

      // APPOINTMENT-F17: «Charge» opens the appointment's check in the till, at the price booked.
      await rowAction(page, 'appointment-list', online.id, 'charge');
      await page.waitForURL(/\/sale\/pos\?order=/);
      expect(psql(`select label from sale_order where appointment_id = '${online.id}'`)).toBe(`${who.customer.name} · ${online.number}`);
      await capture(page, 'APPOINTMENT-F17');

      // APPOINTMENT-F09: an appointment whose time is gone is marked as a no-show.
      const past = await book(context, who, `${PAST}T${String(10 + index).padStart(2, '0')}:00`);
      await page.goto(`${A}/appointment/agenda`);
      await goToDay(page, PAST);
      await rowAction(page, 'appointment-list', past.id, 'no_show');
      await expect.poll(() => statusOf(past.id)).toBe('no_show');
      await showsStatus(page, past.id, 'No-show');
      await capture(page, 'APPOINTMENT-F09');
    } finally {
      await context.close();
    }
  });

  test(`Appointments flows at ${vp.label}: the day by professional with a block, and the week`, async ({ browser }) => {
    const { context, page } = await ownerPage(browser, '/appointment/agenda', vp);
    try {
      const who = await cast(context, `${vp.label}g`, GRID_DAY);
      const booked = await book(context, who, `${GRID_DAY}T10:00`);
      await post(context, '/appointment/blocked_times', {
        title: named('Training'),
        block_type: 'other',
        start: `${GRID_DAY}T13:00`,
        end: `${GRID_DAY}T14:00`,
        staff_id: who.member.id,
      });
      await goToDay(page, GRID_DAY);
      const view = shown(page);

      // APPOINTMENT-F16: the day by professional paints her block and her appointment.
      await view.locator('[data-testid=appointment-toolbar-view-staff]').click();
      const lane = view.locator(`[data-testid=appointment-grid-lane][data-lane="${who.member.id}"]`);
      await expect(lane.locator(`[data-testid=appointment-grid-appointment][data-id="${booked.id}"]`)).toContainText(who.customer.name);
      await expect(view.locator('[data-testid=appointment-grid-block]', { hasText: 'Training' }).first()).toBeAttached();
      await capture(page, 'APPOINTMENT-F16');

      // APPOINTMENT-F27: «Week», a column per day and her appointment on its day.
      await view.locator('[data-testid=appointment-toolbar-span-week]').click();
      const cell = view.locator(`[data-testid=appointment-week-cell][data-lane="${who.member.id}"][data-day="${GRID_DAY}"]`);
      await expect(cell).toContainText(who.customer.name);
      await expect(view.locator('[data-testid=appointment-week-day]')).toHaveCount(7);
      await capture(page, 'APPOINTMENT-F27');
    } finally {
      await context.close();
    }
  });

  test(`Appointments flows at ${vp.label}: a repeating appointment and the customer's visits`, async ({ browser }) => {
    test.setTimeout(240_000);
    const { context, page } = await ownerPage(browser, '/appointment/agenda', vp);
    try {
      const who = await cast(context, `${vp.label}s`, SERIES_DAY);
      await shown(page).locator('[data-testid=appointment-toolbar-view-series]').click();
      const view = shown(page);
      await view.locator('[data-testid=appointment-series-empty], [data-testid=appointment-series-row]').first().waitFor({ state: 'visible' });

      // APPOINTMENT-F12: «New repeating appointment» books its window.
      await view.locator('[data-testid=appointment-series-add]').click();
      const form = page.locator('ion-modal[data-testid=series-form]');
      await chooseCustomer(page, 'series-form', who);
      await pick(page, 'series-form-service-add', word(who.service.name), who.service.name);
      await pick(page, 'series-form-staff', word(who.member.full_name), who.member.full_name);
      await form.locator('[data-testid=series-form-start_date] input').fill(SERIES_DAY);
      await form.locator('[data-testid=series-form-time] input').fill('16:00');
      await form.locator('[data-testid=series-form-max_occurrences] input').fill('3');
      expect(await cutLabels(form), `labels cut in the series form at ${vp.label}`).toEqual([]);
      await capture(page, 'APPOINTMENT-F12');
      await form.locator('[data-testid=series-form-submit]').click();
      await expect(form).toBeHidden();
      const outcome = view.locator('[data-testid=appointment-series-outcome]');
      await expect(outcome).toContainText('appointments booked');
      const series = psql(`select id from appointment_recurring where customer_id = '${who.customer.id}'`);
      const booked = () => Number(psql(`select count(*) from appointment_appointment where recurring_id = '${series}' and status <> 'cancelled' and deleted_at is null`));
      expect(booked()).toBeGreaterThan(0);
      // «Ends» is a column of low priority: a tablet hides it (the «Columns» menu brings it back).
      await expect(view.locator('[data-testid=appointment-series-row]', { hasText: who.customer.name })).toBeVisible();
      expect(psql(`select max_occurrences from appointment_recurring where id = '${series}'`)).toBe('3');

      // APPOINTMENT-F13: «Book appointments» books what the window still has (nothing twice).
      const before = booked();
      await rowAction(page, 'appointment-series', series, 'materialize');
      await expect(outcome).toContainText('Nothing new to book');
      await expect(outcome).not.toContainText('could not be booked');
      await capture(page, 'APPOINTMENT-F13');
      expect(booked()).toBe(before);

      // APPOINTMENT-F14: «Edit series» from its first date: the time changes for every booked appointment.
      await rowAction(page, 'appointment-series', series, 'edit');
      await expect(form).toBeVisible();
      await expect(form.locator('ion-title')).toHaveText('Edit repeating appointment');
      await form.locator('[data-testid=series-form-from_date] input').fill(SERIES_DAY);
      await form.locator('[data-testid=series-form-time] input').fill('17:00');
      await expect(form.locator('[data-testid=series-form-scope]')).toContainText('booked appointments');
      // appointments#293: only what happens; nothing is charged here, so no «0 already charged».
      await expect(form.locator('[data-testid=series-form-scope]')).not.toContainText('already charged');
      expect(await cutLabels(form), `labels cut in the series form at ${vp.label}`).toEqual([]);
      await capture(page, 'APPOINTMENT-F14');
      await form.locator('[data-testid=series-form-submit]').click();
      await expect(form).toBeHidden();
      await expect(outcome).toContainText('appointments moved');
      await expect(outcome).not.toContainText('0 cancelled');
      await expect
        .poll(() => psql(`select string_agg(distinct to_char(start at time zone 'Europe/Madrid', 'HH24:MI'), ',') from appointment_appointment where recurring_id = '${series}' and deleted_at is null and status <> 'cancelled'`))
        .toBe('17:00');

      // APPOINTMENT-F15: paused and reactivated with «Active», then deleted (asked first); what was booked stays.
      const toggle = view.locator(`[data-testid=appointment-series-toggle-${series}]`);
      await toggle.click();
      await expect.poll(() => psql(`select is_active from appointment_recurring where id = '${series}'`)).toBe('f');
      await capture(page, 'APPOINTMENT-F15');
      await toggle.click();
      await expect.poll(() => psql(`select is_active from appointment_recurring where id = '${series}'`)).toBe('t');
      await rowAction(page, 'appointment-series', series, 'delete');
      const remove = page.locator('ion-modal[data-testid=appointment-series-delete]');
      await expect(remove).toContainText(who.customer.name);
      await remove.locator('[data-testid=appointment-series-delete-submit]').click();
      await expect.poll(() => psql(`select deleted_at is not null from appointment_recurring where id = '${series}'`)).toBe('t');
      expect(booked()).toBeGreaterThan(0);

      // APPOINTMENT-F20: her card in Customers shows her visits, the newest first.
      await page.goto(`${A}/customer/customers/${who.customer.id}`);
      await expect(shown(page).locator('[data-testid=appointment-visits]')).toContainText('Visit history');
      await expect(shown(page).locator('[data-testid=appointment-visit]').first()).toBeVisible();
      // On a phone the block sits below the card's fold: bring it into view for the capture.
      await shown(page).locator('[data-testid=appointment-visits]').scrollIntoViewIfNeeded();
      await capture(page, 'APPOINTMENT-F20');
    } finally {
      await context.close();
    }
  });
});

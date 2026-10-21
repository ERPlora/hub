// flow: ONLINE_BOOKING-F01 ONLINE_BOOKING-F02 ONLINE_BOOKING-F03 ONLINE_BOOKING-F04 ONLINE_BOOKING-F05 ONLINE_BOOKING-F06 ONLINE_BOOKING-F07 ONLINE_BOOKING-F08 ONLINE_BOOKING-F10 ONLINE_BOOKING-F11
// Every flow of Online booking that has a screen, end to end in each of the three sizes (apps/online_booking/
// WORKBOOK.md), with one screenshot per flow and size (`APP-ONLINE_BOOKING-<flow>-<width>`), against the real
// Appointments, Customers, Services, Staff and Schedules apps: a service of Services that a professional of Staff
// performs and a day Schedules opens. The owner saves the page's settings and switches the service's «Online
// booking» off and on (F07); in the dev preview of the public page a customer books with no preference of
// professional (F01), sees her booking by its link (F10) and cancels it (F11). Three more customers book through
// the same public operations; the inbox searches and filters them (F08), confirms and completes the first (F02,
// F03), marks the one whose time has passed as a no-show (F04), cancels the third with a reason (F05) and deletes
// it (F06). Each size works on a day of its own and books as a visitor of its own (the page's limit counts the
// bookings of one device in an hour). Everything is named «E2E OB …» and removed before and after; the settings
// of Appointments and of this app are read first and put back by API at the end.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, psql, shot, shown } from './helpers';
import { filterBy, FLOW_VIEWPORTS, noHorizontalScroll, ownerPage, post, rowAction, settled } from './service-helpers';

const TAG = 'E2E OB';
const RUN = Date.now().toString(36);
const named = (label: string): string => `${TAG} ${label} ${RUN}`;
/** A Spanish mobile unique to the run and to `n` (`6` + eight digits). */
const STAMP = Date.now();
const mobile = (n: number): string => `6${String(STAMP + n * 7919).slice(-8)}`;
/** The visitor (its forwarded address) each size books as: one of its own per run. */
const VISITOR = `10.${Math.floor(Math.random() * 250)}.${Math.floor(Math.random() * 250)}`;

/** A Monday `weeks` + five weeks ahead (inside the 90 days of advance), as `YYYY-MM-DD` of the business. */
function aMonday(weeks: number): string {
  const day = new Date();
  day.setUTCDate(day.getUTCDate() + 35 + 7 * weeks + ((8 - day.getUTCDay()) % 7));
  return day.toISOString().slice(0, 10);
}

function cleanUp(): void {
  const customers = `select id from customer_customer where name like '${TAG}%'`;
  const appointments = `select id from appointment_appointment where customer_id in (${customers})`;
  const services = `select id from service_service where name like '${TAG}%'`;
  const members = `select id from staff_member where first_name like '${TAG}%'`;
  psql(
    [
      `delete from online_booking_booking where appointment_id in (${appointments})`,
      `delete from appointment_history where appointment_id in (${appointments})`,
      `delete from appointment_appointmentservice where appointment_id in (${appointments})`,
      `delete from appointment_appointment where id in (${appointments})`,
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

/** What the business had, put back at the end: the rules of Appointments and the page's settings. */
let savedRules: Record<string, unknown> | null = null;
let savedPage: Record<string, unknown> | null = null;
const RULES = ['min_booking_notice', 'max_advance_booking', 'slot_interval', 'auto_confirm_online', 'allow_customer_cancellation', 'cancellation_notice_hours'];

test.beforeAll(async ({ browser }) => {
  cleanUp();
  const { context } = await ownerPage(browser, '/online_booking/bookings');
  try {
    const rules = await api<Record<string, unknown>>(context, A, 'GET', '/appointment/settings');
    const page = await api<Record<string, unknown>>(context, A, 'GET', '/online_booking/settings');
    expect([rules.status, page.status]).toEqual([200, 200]);
    savedRules = Object.fromEntries(Object.entries(rules.data).filter(([key]) => key !== 'timezone'));
    savedPage = Object.fromEntries(Object.entries(page.data).filter(([key]) => key !== 'timezone' && !RULES.includes(key)));
  } finally {
    await context.close();
  }
});

test.afterAll(async ({ browser }) => {
  cleanUp();
  const { context } = await ownerPage(browser, '/online_booking/bookings');
  try {
    if (savedRules) await post(context, '/appointment/settings', savedRules, 200);
    if (savedPage) await post(context, '/online_booking/settings', savedPage, 200);
  } finally {
    await context.close();
  }
});

interface Cast {
  service: { id: string; name: string };
  member: { id: string; full_name: string };
}

/** The cast through each app's own API: a service a professional performs, `day` open, the page on. */
async function cast(context: BrowserContext, label: string, day: string): Promise<Cast> {
  const service = await post<{ id: string; name: string }>(context, '/service/services', {
    name: named(`Haircut ${label}`),
    price: 2000,
    duration_minutes: 30,
    tax_category_key: 'service.generic',
  });
  const member = await post<{ id: string; full_name: string }>(context, '/staff/members', { first_name: named(`Ana ${label}`), last_name: 'Stylist' });
  await post(context, '/service/assignments/assign', { service_id: service.id, member_id: member.id }, 200);
  await post(context, '/schedule/special_days', {
    date: day,
    name: named(`Open ${label}`),
    is_closed: false,
    intervals: [{ open_time: '09:00', close_time: '18:00' }],
  });
  await post(context, '/online_booking/settings', { is_enabled: true, auto_confirm_online: false, allow_customer_cancellation: true, cancellation_notice_hours: 24 }, 200);
  return { service, member };
}

interface Booked {
  number: string;
  status: string;
}

/** Books as the public page does (its operation), as the visitor `visitor`: the page counts each device's bookings. */
async function publicBook(context: BrowserContext, visitor: string, who: Cast, start: string, name: string, phone: string): Promise<Booked> {
  const cookies = await context.cookies(A);
  const csrf = cookies.find((c) => c.name === 'csrftoken' && c.domain === new URL(A).hostname)?.value ?? '';
  const res = await context.request.post(`${A}/api/online_booking/public/book`, {
    headers: { 'X-CSRFToken': csrf, Accept: 'application/json', 'X-Forwarded-For': visitor },
    data: { service_ids: [who.service.id], start, name, phone },
  });
  const data = (await res.json()) as Booked;
  expect(res.status(), JSON.stringify(data)).toBe(200);
  return data;
}

const idOf = (number: string): string => psql(`select id from appointment_appointment where number = '${number}'`);
const statusOf = (id: string): string => psql(`select status from appointment_appointment where id = '${id}'`);

/** Waits until the dialog `testid` has finished opening: shown, opaque and inside the viewport (a capture taken
 *  earlier catches its enter animation's first frame, an invisible box over a dimmed page). */
async function presented(page: Page, testid: string): Promise<void> {
  const modal = page.locator(`ion-modal[data-testid=${testid}]`);
  await expect(modal).toHaveClass(/show-modal/);
  await expect
    .poll(() =>
      modal.evaluate((el) => {
        const wrapper = el.shadowRoot?.querySelector('.modal-wrapper');
        if (!wrapper) return false;
        const box = wrapper.getBoundingClientRect();
        return getComputedStyle(wrapper).opacity === '1' && box.height > 0 && box.top >= 0 && box.bottom <= window.innerHeight + 1;
      }),
    )
    .toBe(true);
}

/** Each of `testids` ends inside the window: nothing pushed off its right edge (a scroll container hides it
 *  from the document's own width). */
async function inWindow(page: Page, ...testids: string[]): Promise<void> {
  for (const testid of testids) {
    const right = await shown(page).locator(`[data-testid=${testid}]`).evaluate((el) => el.getBoundingClientRect().right);
    expect(right, `${testid} inside the window`).toBeLessThanOrEqual(page.viewportSize()!.width);
  }
}

/** Every switch of the settings ends inside the window: a long label wraps instead of pushing the form past a
 *  phone's edge (ion-toggle's label is one line by default; the same defect Attendance had, hub#94). */
async function switchesFit(page: Page): Promise<void> {
  const toggles = shown(page).locator('ion-toggle[data-testid^=ob-settings-]');
  expect(await toggles.count()).toBeGreaterThan(0);
  const outside = await toggles.evaluateAll((all, width) =>
    all.filter((el) => el.getBoundingClientRect().right > width).map((el) => `${el.getAttribute('data-testid')} right=${Math.round(el.getBoundingClientRect().right)}`),
  page.viewportSize()!.width);
  expect(outside, 'settings switches pushed past the window').toEqual([]);
}

/** Every customer's name in the inbox fits its cell or ends in «…»: never cut off mid-letter. */
async function namesFit(page: Page): Promise<void> {
  const names = shown(page).locator('[data-testid=ob-bookings-customer-name]');
  expect(await names.count()).toBeGreaterThan(0);
  const cut = await names.evaluateAll((names) =>
    names.filter((el) => el.scrollWidth > el.clientWidth && getComputedStyle(el).textOverflow !== 'ellipsis').map((el) => el.textContent),
  );
  expect(cut, 'customer names cut off without «…»').toEqual([]);
}

/** The inbox row of `number`, searched by its number. */
async function inboxRow(page: Page, number: string) {
  const view = shown(page);
  await view.locator('[data-testid=ob-bookings-search] input').fill(number);
  const row = view.locator('[data-testid=ob-bookings-row]', { hasText: number });
  await expect(row).toBeVisible();
  return row;
}

FLOW_VIEWPORTS.forEach((vp, index) => {
  test(`Online booking flows at ${vp.label}: settings, book, see and cancel by link, and the inbox`, async ({ browser }) => {
    const { context, page } = await ownerPage(browser, '/online_booking/bookings', vp);
    const capture = async (flow: string): Promise<void> => {
      await settled(page);
      await page.screenshot({ path: shot(`APP-ONLINE_BOOKING-${flow}-${vp.label}`) });
    };
    const visitor = `${VISITOR}.${index + 1}`;
    await context.setExtraHTTPHeaders({ 'X-Forwarded-For': visitor });
    const day = aMonday(index);
    try {
      const who = await cast(context, vp.label, day);

      // ONLINE_BOOKING-F07: the page's title saved and said so; the service's «Online booking» off and on again.
      await page.goto('/online_booking/settings');
      let view = shown(page);
      await view.locator('[data-testid=ob-settings-page_title] input').fill(named(`Salon ${vp.label}`));
      await view.locator('[data-testid=ob-settings-save]').click();
      await expect(view.locator('[data-testid=ob-settings-saved]')).toContainText('Settings saved.');
      const saved = await api<{ page_title: string }>(context, A, 'GET', '/online_booking/settings');
      expect(saved.data.page_title).toBe(named(`Salon ${vp.label}`));
      const online = `select allow_online_booking from service_service where id = '${who.service.id}'`;
      const toggle = view.locator(`[data-testid=ob-settings-service-${who.service.id}]`);
      await toggle.scrollIntoViewIfNeeded();
      await toggle.click();
      await expect.poll(() => psql(online)).toBe('f');
      await expect(toggle).toBeEnabled();
      await toggle.click();
      await expect.poll(() => psql(online)).toBe('t');
      await expect(toggle).toBeEnabled();
      await switchesFit(page);
      await capture('ONLINE_BOOKING-F07');

      // ONLINE_BOOKING-F01: the preview of the public page — the service, no preference, the day and a free
      // time, name and mobile; pending (manual confirmation), in the diary, and her card created by her mobile.
      await page.goto('/online_booking/preview');
      view = shown(page);
      await expect(view.locator('[data-testid=ob-preview-title]')).toHaveText(named(`Salon ${vp.label}`));
      await view.locator(`[data-testid=ob-preview-service-${who.service.id}]`).click();
      const dayInput = view.locator('[data-testid=ob-preview-day] input');
      await dayInput.fill(day);
      await dayInput.press('Tab');
      const ten = view.locator('[data-testid="ob-preview-time-10:00"]');
      await expect(ten).toBeVisible();
      await ten.click();
      const marta = named(`Marta ${vp.label}`);
      await view.locator('[data-testid=ob-preview-name] input').fill(marta);
      await view.locator('[data-testid=ob-preview-phone] input').fill(mobile(10 * index));
      await view.locator('[data-testid=ob-preview-book]').click();
      const booked = view.locator('[data-testid=ob-preview-booked]');
      await expect(booked).toContainText('Booking APT-');
      await expect(booked).toContainText('We have received your booking.');
      const number = ((await booked.textContent()) ?? '').match(/APT-\d{8}-\d{4}/)![0];
      const token = ((await view.locator('[data-testid=ob-preview-token] code').textContent()) ?? '').trim();
      expect(token.length).toBeGreaterThanOrEqual(43);
      await noHorizontalScroll(page, `the booked preview at ${vp.label}`);
      await inWindow(page, 'ob-preview-booked', 'ob-preview-token');
      const appointment = JSON.parse(
        psql(`select row_to_json(a) from (select id, status, source, staff_id, customer_id from appointment_appointment where number = '${number}') a`),
      ) as { id: string; status: string; source: string; staff_id: string; customer_id: string };
      expect([appointment.status, appointment.source, appointment.staff_id]).toEqual(['pending', 'online', who.member.id]);
      expect(psql(`select phone from customer_customer where id = '${appointment.customer_id}'`)).toBe(`+34${mobile(10 * index)}`);
      const agenda = await api<{ status: string; booked_by_customer: boolean }>(context, A, 'GET', `/appointment/appointments/detail?number=${number}`);
      expect([agenda.data.status, agenda.data.booked_by_customer]).toEqual(['pending', true]);
      await capture('ONLINE_BOOKING-F01');

      // ONLINE_BOOKING-F10: her link shows the booking, still cancellable.
      await view.locator('[data-testid=ob-preview-view]').click();
      const status = view.locator('[data-testid=ob-preview-status]');
      await expect(status).toContainText('Pending');
      await expect(status).toContainText(number);
      await capture('ONLINE_BOOKING-F10');

      // ONLINE_BOOKING-F11: she cancels it with her link, within the policy: «the customer asked» in the diary.
      await view.locator('[data-testid=ob-preview-cancel]').click();
      await expect(status).toContainText('Cancelled');
      await expect(view.locator('[data-testid=ob-preview-cancel]')).toHaveClass(/button-disabled/);
      expect(psql(`select status || ' ' || cancelled_by_customer from appointment_appointment where id = '${appointment.id}'`)).toBe('cancelled true');
      await capture('ONLINE_BOOKING-F11');

      // Three more customers book through the page's operation; the third's time is then moved into the past.
      const first = await publicBook(context, visitor, who, `${day}T11:00`, named(`Lucía ${vp.label}`), mobile(10 * index + 1));
      const second = await publicBook(context, visitor, who, `${day}T12:00`, named(`Nora ${vp.label}`), mobile(10 * index + 2));
      const third = await publicBook(context, visitor, who, `${day}T13:00`, named(`Eva ${vp.label}`), mobile(10 * index + 3));
      expect([first.status, second.status, third.status]).toEqual(['pending', 'pending', 'pending']);
      const [firstId, secondId, thirdId] = [first, second, third].map((item) => idOf(item.number));
      // (`\\"end\\"`: the column is a reserved word, quoted inside the shell's double quotes of `psql()`.)
      psql(`update appointment_appointment set start = start - interval '70 days', \\"end\\" = \\"end\\" - interval '70 days' where id = '${thirdId}'`);

      // ONLINE_BOOKING-F08: the inbox, filtered by «Pending» and searched by the run's names.
      await page.goto('/online_booking/bookings');
      view = shown(page);
      await expect(view.locator('[data-testid=ob-bookings-row]').first()).toBeVisible();
      await filterBy(page, 'ob-bookings', 'status', 'Pending');
      await view.locator('[data-testid=ob-bookings-search] input').fill(`${TAG} `);
      for (const item of [first, second, third]) {
        await expect(view.locator('[data-testid=ob-bookings-row]', { hasText: item.number })).toBeVisible();
      }
      await expect(view.locator('[data-testid=ob-bookings-row]', { hasText: number })).toHaveCount(0);
      await noHorizontalScroll(page, `the inbox at ${vp.label}`);
      await namesFit(page);
      await capture('ONLINE_BOOKING-F08');
      await page.goto('/online_booking/bookings');

      // ONLINE_BOOKING-F02: the first one confirmed from its row.
      let row = await inboxRow(page, first.number);
      await expect(row).toContainText('Pending');
      await rowAction(page, 'ob-bookings', firstId, 'confirm');
      await expect(row).toContainText('Confirmed');
      await expect.poll(() => statusOf(firstId)).toBe('confirmed');
      await capture('ONLINE_BOOKING-F02');

      // ONLINE_BOOKING-F03: and completed.
      await rowAction(page, 'ob-bookings', firstId, 'complete');
      await expect(row).toContainText('Completed');
      await expect.poll(() => statusOf(firstId)).toBe('completed');
      await capture('ONLINE_BOOKING-F03');

      // ONLINE_BOOKING-F04: the one whose time has passed, marked as a no-show.
      row = await inboxRow(page, third.number);
      await rowAction(page, 'ob-bookings', thirdId, 'no_show');
      await expect(row).toContainText('No-show');
      await expect.poll(() => statusOf(thirdId)).toBe('no_show');
      await capture('ONLINE_BOOKING-F04');

      // ONLINE_BOOKING-F05: the second cancelled from its dialog, with a reason.
      row = await inboxRow(page, second.number);
      await rowAction(page, 'ob-bookings', secondId, 'cancel');
      const dialog = page.locator('[data-testid=ob-cancel]');
      await expect(dialog).toContainText(`Cancel ${named(`Nora ${vp.label}`)}'s booking`);
      await presented(page, 'ob-cancel');
      await dialog.locator('[data-testid=ob-cancel-reason] textarea').fill('Fully booked');
      await capture('ONLINE_BOOKING-F05');
      await page.locator('[data-testid=ob-cancel-submit]').click();
      await expect(dialog).toBeHidden();
      await expect(row).toContainText('Cancelled');
      expect(psql(`select status || ' ' || cancellation_reason from appointment_appointment where id = '${secondId}'`)).toBe('cancelled Fully booked');

      // ONLINE_BOOKING-F06: and deleted, after its confirmation: gone from the inbox, archived in the diary.
      await rowAction(page, 'ob-bookings', secondId, 'delete');
      const confirm = page.locator('[data-testid=ob-bookings-delete]');
      await expect(confirm).toContainText(`Delete booking ${second.number}?`);
      await presented(page, 'ob-bookings-delete');
      await capture('ONLINE_BOOKING-F06');
      await page.locator('[data-testid=ob-bookings-delete-submit]').click();
      await expect(confirm).toBeHidden();
      await expect(shown(page).locator('[data-testid=ob-bookings-row]', { hasText: second.number })).toHaveCount(0);
      expect(psql(`select deleted_at is not null from appointment_appointment where id = '${secondId}'`)).toBe('t');
    } finally {
      await context.close();
    }
  });
});

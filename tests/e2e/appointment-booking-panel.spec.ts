// flow: APPOINTMENT-F01, APPOINTMENT-F02, APPOINTMENT-F04 — «New appointment» and «Edit appointment» in Chrome at the
// three sizes: wide in two columns (the whole screen on a phone), the length of one tap, the free times in one tab per
// span of the professional's day, a booking at a time of the second tab and its edit. Each state of the free times the
// server gives is captured: something still missing, none left, a day off and the free times that cannot load.
// Everything is named «E2E Panel …» and removed before and after.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { aMonday, salonCleanUp } from './appointment-helpers';
import { cardDeletes, pickCustomer } from './customer-helpers';
import { pickDay } from './date-time-fields';
import { api, A, capture, psql, shown } from './helpers';
import { ownerPage, pick, post, rowAction, VIEWPORTS } from './service-helpers';
import { discardChanges } from './unsaved-back-helpers';

const TAG = 'E2E Panel';
const RUN = Date.now().toString(36);
const named = (label: string): string => `${TAG} ${label} ${RUN}`;
const DAY = aMonday(3);
/** The Tuesday after: the professional is away the whole day. */
const AWAY = new Date(Date.parse(`${DAY}T00:00:00Z`) + 86_400_000).toISOString().slice(0, 10);
const MEMBERS = `select id from staff_member where first_name like '${TAG}%'`;
const CUSTOMERS = `select id from customer_customer where name like '${TAG}%'`;

function cleanUp(): void {
  psql([`delete from staff_timeoff where member_id in (${MEMBERS})`, ...salonCleanUp(TAG), ...cardDeletes(CUSTOMERS)].join('; '));
}

/** The appointments booked by a test, so the next one finds the same free times. */
function dropAppointments(): void {
  const booked = `select id from appointment_appointment where customer_id in (${CUSTOMERS})`;
  psql([
    `delete from appointment_history where appointment_id in (${booked})`,
    `delete from appointment_appointmentservice where appointment_id in (${booked})`,
    `delete from appointment_appointment where id in (${booked})`,
  ].join('; '));
}

interface Cast {
  customer: { id: string; name: string };
  service: { id: string; name: string };
  member: { id: string; full_name: string };
}

const openDay = (context: BrowserContext, date: string, intervals: { open_time: string; close_time: string }[]) =>
  post(context, '/schedule/special_days', { date, name: named(`Open ${date}`), is_closed: false, intervals });

/** A cut a professional performs, a customer, `DAY` open in two spans and `AWAY` open with the professional away. */
async function cast(context: BrowserContext): Promise<Cast> {
  const service = await post<Cast['service']>(context, '/service/services', {
    name: named('Cut'),
    price: 2000,
    duration_minutes: 30,
    tax_category_key: 'service.generic',
  });
  const member = await post<Cast['member']>(context, '/staff/members', { first_name: named('Pablo'), last_name: 'Serrano' });
  await post(context, '/service/assignments/assign', { service_id: service.id, member_id: member.id }, 200);
  const customer = await post<Cast['customer']>(context, '/customer/customers', { name: named('Elena'), phone: `6${String(Date.now()).slice(-8)}` });
  await openDay(context, DAY, [
    { open_time: '09:00', close_time: '13:00' },
    { open_time: '15:00', close_time: '18:00' },
  ]);
  await openDay(context, AWAY, [{ open_time: '09:00', close_time: '18:00' }]);
  const away = await post<{ id: string }>(context, '/staff/time_off', { member_id: member.id, start_date: AWAY, end_date: AWAY });
  expect((await api(context, A, 'POST', '/staff/time_off/approve', { id: away.id })).status).toBe(200);
  return { customer, service, member };
}

let who!: Cast;

test.beforeAll(async ({ browser }) => {
  cleanUp();
  const { context } = await ownerPage(browser, '/appointment/agenda');
  try {
    who = await cast(context);
  } finally {
    await context.close();
  }
});

test.afterAll(() => cleanUp());

const form = (page: Page): Locator => page.locator('ion-modal[data-testid=appointment-form]');
const slots = (page: Page): Locator => form(page).locator('[data-testid=appointment-slots]');
const time = (page: Page, said: RegExp): Locator => form(page).locator('[data-testid=appointment-slots-time]', { hasText: said });

/** The agenda on `DAY`, where the booked appointment's row is. */
async function goToDay(page: Page): Promise<void> {
  await pickDay(page, shown(page).locator('[data-testid=appointment-toolbar-calendar]'), DAY);
  await expect(shown(page).locator('[data-testid=appointment-toolbar-date]')).not.toBeEmpty();
}

async function openNew(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=appointment-list-add]').click();
  await expect(form(page)).toBeVisible();
}

/** «Services», «Professional» and «Day» of the open panel. */
async function chooseWhatAndWhen(page: Page, day: string): Promise<void> {
  await pick(page, 'appointment-form-service-add', RUN, who.service.name);
  await pick(page, 'appointment-form-staff', RUN, who.member.full_name);
  await pickDay(page, form(page).locator('[data-testid=appointment-form-day]'), day);
}

/** Nothing in the panel scrolls sideways. */
async function fitsItsWidth(page: Page, label: string): Promise<void> {
  const body = form(page).locator('.ep-form-modal__body');
  expect(await body.evaluate((el) => el.scrollWidth - el.clientWidth), `the panel scrolls sideways at ${label}`).toBeLessThanOrEqual(0);
}

/** Each length reads on one line and, on a tablet or a desktop, the length and the free times share the right column. */
async function laidOut(page: Page, size: string): Promise<void> {
  const lines = await form(page)
    .locator('[data-testid=appointment-form-duration] [role=group] button')
    .evaluateAll((buttons) =>
      buttons.map((button) => {
        const range = document.createRange();
        range.selectNodeContents(button);
        return new Set([...range.getClientRects()].map((rect) => Math.round(rect.top))).size;
      }),
    );
  expect(lines, `a length wraps at ${size}`).toEqual(lines.map(() => 1));
  if (size === 'phone') return;
  const left = async (testid: string) => (await form(page).locator(`[data-testid=${testid}]`).boundingBox())!.x;
  expect(Math.abs((await left('appointment-form-duration')) - (await left('appointment-slots'))), `the right column at ${size}`).toBeLessThan(2);
}

for (const [size, viewport] of Object.entries(VIEWPORTS)) {
  test(`APPOINTMENT-F01, F02, F04 at ${size}: a length of one tap, a time of the second span, and its edit`, async ({ browser }) => {
    dropAppointments();
    const { context, page } = await ownerPage(browser, '/appointment/agenda', viewport);
    try {
      await openNew(page);
      await expect(form(page).locator('[data-testid=appointment-form-slots-unset]')).toBeVisible();
      await capture(page, `APPOINTMENT-F02-unset-${size}`);
      await pickCustomer(page, form(page), who.customer);
      await chooseWhatAndWhen(page, DAY);

      // The shift in two spans, each a tab with its free times; the first opens.
      await expect(slots(page).locator('[data-testid=appointment-slots-shift]')).toHaveText(
        `${who.member.full_name} works on ${await dayInWords(page)} from 9:00 AM to 1:00 PM and from 3:00 PM to 6:00 PM.`,
      );
      const tabs = slots(page).locator('[data-testid=appointment-slots-window]');
      await expect(tabs).toHaveCount(2);
      await expect(time(page, /^9:00\sAM$/)).toBeVisible();

      // One tap for an hour, a time of the afternoon, and the foot says it all.
      await form(page).locator('[data-testid=appointment-form-duration-60]').click();
      await expect(form(page).locator('[data-testid=appointment-form-duration-60]')).toHaveAttribute('aria-pressed', 'true');
      await tabs.nth(1).click();
      await time(page, /^3:00\sPM$/).click();
      await expect(time(page, /^3:00\sPM$/)).toHaveAttribute('aria-pressed', 'true');
      await expect(form(page).locator('[data-testid=appointment-form-chosen-span]')).toHaveText('3:00 PM – 4:00 PM · 60 min');
      await expect(form(page).locator('[data-testid=appointment-form-chosen-where]')).toContainText(who.member.full_name);
      await fitsItsWidth(page, size);
      await laidOut(page, size);
      await capture(page, `APPOINTMENT-F01-panel-${size}`);
      await form(page).locator('[data-testid=appointment-form-submit]').click();
      await expect(form(page)).toBeHidden();
      const booked = (): string =>
        psql(
          `select id || ' ' || to_char(start at time zone 'Europe/Madrid', 'HH24:MI') || ' ' || duration_minutes from appointment_appointment where customer_id = '${who.customer.id}'`,
        );
      await expect.poll(booked).toMatch(/ 15:00 60$/);
      const id = booked().split(' ')[0];

      // «Edit appointment» opens on the span of its time, pressed; another time of it moves the appointment.
      await goToDay(page);
      await rowAction(page, 'appointment-list', id, 'edit');
      await expect(form(page).locator('ion-title')).toHaveText('Edit appointment');
      await expect(form(page).locator('[data-testid=appointment-form-booked]')).toContainText(who.customer.name);
      await expect(time(page, /^3:00\sPM$/)).toHaveAttribute('aria-pressed', 'true');
      await expect(form(page).locator('[data-testid=appointment-form-duration-60]')).toHaveAttribute('aria-pressed', 'true');
      // Booked at an hour for a half-hour service: the way back to the sum is there from the start.
      await expect(form(page).locator('[data-testid=appointment-form-duration-use-sum]')).toBeVisible();
      await fitsItsWidth(page, `${size} edit`);
      await capture(page, `APPOINTMENT-F04-panel-${size}`);
      await time(page, /^4:30\sPM$/).click();
      await form(page).locator('[data-testid=appointment-form-submit]').click();
      await expect(form(page)).toBeHidden();
      await expect.poll(booked).toBe(`${id} 16:30 60`);
    } finally {
      await context.close();
    }
  });
}

/** The day of `DAY` as the shift's sentence writes it, in the page's language. */
function dayInWords(page: Page): Promise<string> {
  return page.evaluate(
    (day) => new Intl.DateTimeFormat('en-US', { weekday: 'long', month: 'long', day: 'numeric', timeZone: 'UTC' }).format(new Date(`${day}T00:00:00Z`)),
    DAY,
  );
}

test('APPOINTMENT-F02: none left, a day off and the free times that cannot load, each said in place', async ({ browser }) => {
  dropAppointments();
  const { context, page } = await ownerPage(browser, '/appointment/agenda', VIEWPORTS.tablet);
  try {
    await openNew(page);
    await chooseWhatAndWhen(page, DAY);
    await expect(slots(page).locator('[data-testid=appointment-slots-window]')).toHaveCount(2);

    // Five hours fit in neither span: none left, and another time can still be picked.
    await form(page).locator('[data-testid=appointment-form-duration-other]').click();
    await form(page).locator('[data-testid=appointment-form-minutes] input').fill('300');
    await expect(slots(page).locator('[data-testid=appointment-slots-empty]')).toContainText('No free times that day for this professional.');
    await expect(form(page).locator('[data-testid=appointment-form-time]')).toBeVisible();
    await capture(page, 'APPOINTMENT-F02-empty-tablet');

    // A length past a day is refused by the server: the free times say they cannot load, with Retry.
    await form(page).locator('[data-testid=appointment-form-minutes] input').fill('2000');
    const failed = slots(page).locator('[data-testid=appointment-slots-error]');
    await expect(failed).toContainText('The free times could not be loaded.');
    await expect(failed.getByRole('button', { name: 'Retry' })).toBeVisible();
    await expect(form(page).locator('[data-testid=appointment-form-time]')).toBeVisible();
    await capture(page, 'APPOINTMENT-F02-error-tablet');

    // Away the whole day: said in place, and no other time is offered, the server would refuse it.
    await form(page).locator('[data-testid=appointment-form-duration-use-sum]').click();
    await pickDay(page, form(page).locator('[data-testid=appointment-form-day]'), AWAY);
    await expect(slots(page).locator('[data-testid=appointment-slots-off]')).toContainText(`${who.member.full_name} does not work on`);
    await expect(slots(page).locator('[data-testid=appointment-slots-off]')).toContainText('Pick another day or another professional.');
    await expect(form(page).locator('[data-testid=appointment-form-other-time]')).toHaveCount(0);
    await capture(page, 'APPOINTMENT-F02-off-tablet');

    await form(page).locator('[data-testid=appointment-form-cancel]').click();
    await discardChanges(page);
    await expect(form(page)).toBeHidden();
  } finally {
    await context.close();
  }
});

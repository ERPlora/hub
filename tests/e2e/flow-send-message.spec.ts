// flow: FLOW-F31 WHATSAPP_INBOX-F23 WHATSAPP_INBOX-F26 RESERVATION-F19
// «Send a message to a customer» (apps/flow/WORKBOOK.md FLOW-F31), «The customer gets the notice when the salon
// confirms» (apps/whatsapp_inbox/WORKBOOK.md WHATSAPP_INBOX-F23) and its table companion «… when the restaurant
// confirms» (WHATSAPP_INBOX-F26, apps/reservation/WORKBOOK.md RESERVATION-F19), end to end as the owner, against the
// real apps and the run's REAL erplora.com (only Meta is played: whatsapp-helpers.ts, «The run's real erplora.com»).
// - FLOW-F31, in each of the three sizes: in a new automation «Send a message» opens its own form; to the customer's
//   exact number, the message, an approved template with a value for each blank; saved, allowed, on and run by
//   hand, the WhatsApp is in the customer's conversation and went to erplora.com (door 5), whose Meta refuses the
//   seed's made-up permission: the message says why. One screenshot per size (FIX-FLOW-SEND-MESSAGE-STEP-<width>).
// - WHATSAPP_INBOX-F23: «Comes with WhatsApp inbox» turns on «Tell the customer by WhatsApp when their appointment is
//   confirmed»; with «I review them first», Citas confirms a booking the customer made online; the worker's outbox
//   relay pass hands it over and the notice reaches her conversation through erplora.com, once (a second pass sends
//   nothing); a booking born confirmed tells its customer too. A customer whose number never wrote gets nothing,
//   and the automation's history says where it stopped. Citas' setting is put back after.
// - WHATSAPP_INBOX-F26 / RESERVATION-F19, as an owner who works in Spanish: the card «Avisar por WhatsApp al cliente
//   cuando se confirma su reserva» opened and turned on (one screenshot per size, FIX-HUB-WHATSAPP-INBOX-RESERVATION-
//   CONFIRMED-RECIPE-<width>); with «Confirmar solas las reservas nuevas» off, «Confirmar» in Reservas on a reservation
//   whose number has a conversation; the relay pass hands it over and the notice, with its day, time and guests in
//   Spanish, is in the conversation of the inbox once (a second pass, or cancelling it, sends nothing more; one
//   screenshot per size, …-chat-<width>). Reservas' settings are put back after. The reservation is always on a
//   Saturday, so the notice names «sábado», accent included, and it must name that very day, written as the Hub
//   writes any weekday and month (checked against its `day_label`).
// What it creates is «E2E Fsm …», `e2e.`/`+3469900…` (whatsapp-helpers.ts), the recipes' automations, a slot (its
// maximum is `SLOT_SENTINEL`) and a day open in Schedules («E2E Fsm …»), and goes.
import { spawnSync } from 'node:child_process';

import { type Browser, type BrowserContext, expect, type Page, test } from '@playwright/test';

import { choose, confirmDialog, signedIn } from './flow-helpers';
import { A, api, HUB_DIR, login, psql, shot, shown } from './helpers';
import { FLOW_VIEWPORTS, noHorizontalScroll, post, rowAction, settled } from './service-helpers';
import {
  cleanUp as cleanUpInbox,
  e2ePhone,
  metaGraph,
  OUTBOUND_AT_ONCE,
  pushChannel,
  receive,
  restorePhoto,
  seedErplora,
  template,
} from './whatsapp-helpers';

test.describe.configure({ mode: 'serial' });

const TASK = 'FIX-FLOW-SEND-MESSAGE-STEP';
const TAG = 'E2E Fsm';
const RUN = Date.now().toString(36);
const REF = 'whatsapp_inbox/appointment_confirmed';
const TABLE_REF = 'whatsapp_inbox/reservation_confirmed';
const TABLE_TASK = 'FIX-HUB-WHATSAPP-INBOX-RESERVATION-CONFIRMED-RECIPE';
/** The maximum of the slot this spec opens (slots have no name): how `cleanUp` knows it. */
const SLOT_SENTINEL = 76;
/** An approved Utility template of this run with two blanks. */
const CONFIRMED = template('e2e_confirmed', { variables: 2, body: 'Confirmada: {{1}} a las {{2}}.' });

function cleanUp(): void {
  const flows = `select id from flow_flow where name like '${TAG}%' or recipe in ('${REF}', '${TABLE_REF}')`;
  const customers = `select id from customer_customer where name like '${TAG}%'`;
  const appointments = `select id from appointment_appointment where customer_id in (${customers})`;
  const services = `select id from service_service where name like '${TAG}%'`;
  const members = `select id from staff_member where first_name like '${TAG}%'`;
  psql(
    [
      `delete from flow_flowrun where flow_id in (${flows})`,
      `delete from flow_flow where id in (${flows})`,
      `delete from appointment_history where appointment_id in (${appointments})`,
      `delete from appointment_appointmentservice where appointment_id in (${appointments})`,
      `delete from appointment_appointment where id in (${appointments})`,
      `delete from service_assignment where service_id in (${services}) or member_id in (${members})`,
      `delete from service_service where name like '${TAG}%'`,
      `delete from staff_member where first_name like '${TAG}%'`,
      `delete from schedule_specialdayinterval where special_day_id in (select id from schedule_specialday where name like '${TAG}%')`,
      `delete from schedule_specialday where name like '${TAG}%'`,
      `delete from reservation_reservation where guest_name like '${TAG}%' or customer_id in (${customers})`,
      `delete from reservation_timeslot where max_reservations = ${SLOT_SENTINEL}`,
      `delete from schedule_overrideinterval where override_id in (select id from schedule_override where reason like '${TAG}%')`,
      `delete from schedule_override where reason like '${TAG}%'`,
    ].join('; '),
  );
  cleanUpInbox();
  psql(
    [
      `delete from customer_activity where customer_id in (${customers})`,
      `delete from customer_consent where customer_id in (${customers})`,
      `delete from customer_customer where name like '${TAG}%'`,
    ].join('; '),
  );
}

test.beforeAll(async () => {
  cleanUp();
  // erplora.com takes `a`'s number (connected); this Hub knows it, with this run's approved template.
  expect(seedErplora()).toEqual({ delivered: true, hub_error: '' });
  // erplora.com reaches Meta only through the run's Graph, or the run stops here (whatsapp-helpers.ts).
  await metaGraph();
  pushChannel({ status: 'connected', templates: [CONFIRMED] });
});
test.afterAll(() => {
  cleanUp();
  restorePhoto();
});

/** The outbox relay as the worker runs it on every tick, pass after pass until one finds nothing to do; what the
 *  automation hands erplora.com (door 5) is called before this process ends (`OUTBOUND_AT_ONCE`). */
function relayPass(): void {
  const code = [
    OUTBOUND_AT_ONCE,
    'from django.utils import timezone',
    'from base import relay',
    'for _ in range(200):',
    '    done = relay.run(timezone.now())',
    '    if not (done.taken or done.delivered): break',
  ].join('\n');
  const out = spawnSync('uv', ['run', 'python', 'manage.py', 'shell', '-c', code], { cwd: HUB_DIR, env: process.env, encoding: 'utf8' });
  expect(out.status, `relay pass: ${out.stderr}`).toBe(0);
}

/** The Hub's messages to `phone`: `kind|status|body|error`, oldest first. */
const sentTo = (phone: string): string[] =>
  psql(
    `select m.kind || '|' || m.status || '|' || m.body || '|' || m.error_message from whatsapp_inbox_message m join whatsapp_inbox_conversation c on c.id = m.conversation_id where c.phone = '${phone}' and m.direction = 'outbound' order by m.created_at`,
  )
    .split('\n')
    .filter(Boolean);

/** Gone to erplora.com: no longer queued nor on its way (Meta's answer, through erplora.com, is in it). */
const handedOver = (row: string): boolean => !/^[a-z]+\|(queued|sending)\|/.test(row);

async function openRun(page: Page, status: string) {
  const run = shown(page).locator('[data-testid^=flow-run-]').filter({ hasText: status }).first();
  await expect(run).toBeVisible();
  await run.locator('[data-testid^=flow-run-toggle-]').click();
  return run;
}

for (const viewport of FLOW_VIEWPORTS) {
  test(`FLOW-F31: «Send a message» writes to the customer's exact number at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(150_000);
    const phone = e2ePhone();
    receive(phone, 'Hola, ¿me confirmáis?', `e2e.Ana ${RUN}`);
    const text = `${TAG} hello ${viewport.label} ${RUN}`;
    const { context, page } = await signedIn(browser, '/flow/automations/new', viewport);
    try {
      const editor = shown(page);
      await editor.locator('[data-testid=flow-editor-name] input').fill(`${TAG} ${viewport.label} ${RUN}`);
      await expect(editor.locator('[data-testid=flow-editor-add-message]')).toHaveText('Send a message');
      await editor.locator('[data-testid=flow-editor-add-message]').click();
      await expect(editor.locator('[data-testid=flow-step-open-s1]')).toHaveText('Send a WhatsApp to a customer');
      await expect(editor.locator('[data-testid=flow-message-phonehint-s1]')).toContainText('exactly that international number');
      await editor.locator('[data-testid=flow-message-phone-s1-text-0]').fill(phone);
      await editor.locator('[data-testid=flow-message-text-s1-text-0]').fill(text);
      await choose(page, 'flow-message-template-s1', 'e2e_confirmed');
      await expect(editor.locator('[data-testid=flow-message-preview-s1]')).toHaveText('Confirmada: {{1}} a las {{2}}.');
      await editor.locator('[data-testid=flow-message-var-s1-0-text-0]').fill('el lunes');
      await editor.locator('[data-testid=flow-message-var-s1-1-text-0]').fill('10:00');
      await settled(page);
      await noHorizontalScroll(page, `FLOW-F31 ${viewport.label}`);
      await page.screenshot({ path: shot(`${TASK}-${viewport.label}`) });

      await editor.locator('[data-testid=flow-editor-save]').click();
      await page.waitForURL(/\/flow\/automations\/[0-9a-f-]+$/);
      await expect(shown(page).locator('[data-testid=flow-editor-notice]')).toHaveText('Saved.');
      await shown(page).locator('[data-testid=flow-editor-tab-permissions]').click();
      await shown(page).locator('[data-testid=flow-perm-grantall]').click();
      await expect(shown(page).locator('[data-testid="flow-perm-granted-whatsapp_inbox.message.notify"]')).toContainText(
        'Send a WhatsApp to a customer',
      );
      await shown(page).locator('[data-testid=flow-editor-enabled]').click();
      await shown(page).locator('[data-testid=flow-editor-save]').click();
      await expect(shown(page).locator('[data-testid=flow-editor-notice]')).toHaveText('Saved.');
      await shown(page).locator('[data-testid=flow-editor-run]').click();
      await confirmDialog(page, 'Run it now?');
      await shown(page).locator('[data-testid=flow-editor-tab-history]').click();
      await openRun(page, 'Finished well');

      // Within her 24 hours the message goes as it is, in her conversation, and erplora.com was called.
      await expect.poll(() => sentTo(phone).length).toBe(1);
      const [message] = sentTo(phone);
      expect(message.startsWith(`text|`)).toBe(true);
      expect(message).toContain(`|${text}|`);
      await expect.poll(() => handedOver(sentTo(phone)[0])).toBe(true);
    } finally {
      await context.close();
    }
  });
}

/** A Monday five weeks ahead (inside the 90 days of advance), as `YYYY-MM-DD`. */
function aMonday(): string {
  const day = new Date();
  day.setUTCDate(day.getUTCDate() + 35 + ((8 - day.getUTCDay()) % 7));
  return day.toISOString().slice(0, 10);
}

/** Whether the day of the bookings is open already (one special day per run). */
let opened = false;

/** Through each app's own API: a customer's card with `phone`, a service her own professional performs and the day
 *  open; then a booking she made online at 10:00 (pending until the business confirms it, unless they confirm
 *  themselves). */
async function onlineBooking(context: BrowserContext, label: string, phone: string): Promise<{ id: string; status: string }> {
  const day = aMonday();
  const customer = await post<{ id: string }>(context, '/customer/customers', { name: `${TAG} Lucía ${label} ${RUN}`, phone });
  const service = await post<{ id: string }>(context, '/service/services', {
    name: `${TAG} Haircut ${label} ${RUN}`,
    price: 2000,
    duration_minutes: 30,
    tax_category_key: 'service.generic',
  });
  const member = await post<{ id: string }>(context, '/staff/members', { first_name: `${TAG} Ana ${label}`, last_name: RUN });
  await post(context, '/service/assignments/assign', { service_id: service.id, member_id: member.id }, 200);
  if (!opened) {
    await post(context, '/schedule/special_days', {
      date: day,
      name: `${TAG} open ${RUN}`,
      is_closed: false,
      intervals: [{ open_time: '09:00', close_time: '18:00' }],
    });
    opened = true;
  }
  return post(context, '/appointment/appointments', {
    customer_id: customer.id,
    services: [{ service_id: service.id }],
    staff_id: member.id,
    start: `${day}T10:00`,
    source: 'online',
  });
}

/** Citas' «Online bookings confirm themselves» (APPOINTMENT-F19), set through its API; what was there before. */
async function autoConfirm(context: BrowserContext, on: boolean): Promise<Record<string, unknown>> {
  const current = await api<Record<string, unknown>>(context, A, 'GET', '/appointment/settings');
  expect(current.status).toBe(200);
  const before = Object.fromEntries(Object.entries(current.data).filter(([key]) => key !== 'timezone'));
  await post(context, '/appointment/settings', { ...before, auto_confirm_online: on }, 200);
  return before;
}

test('WHATSAPP_INBOX-F23: confirming a booking tells the customer by WhatsApp through erplora.com, once', async ({ browser }) => {
  test.setTimeout(180_000);
  const { context, page } = await signedIn(browser, '/flow/automations', FLOW_VIEWPORTS[2]);
  const settings = await autoConfirm(context, false);
  try {
    // FLOW-F33: the inbox's automation, turned on from its card under the gallery.
    const card = shown(page).locator(`[data-testid="flow-recipe-${REF}"]`);
    await card.locator(`[data-testid="flow-recipe-open-${REF}"]`).click();
    await expect(shown(page).locator(`[data-testid="flow-recipe-panel-${REF}"]`)).toContainText('only to exactly the number on their card');
    await shown(page).locator(`[data-testid="flow-recipe-enable-${REF}"]`).click();
    await expect.poll(() => psql(`select enabled from flow_flow where recipe = '${REF}' and deleted_at is null`)).toBe('t');

    // Step 2: «I review them first»: the salon confirms a booking she made online.
    const phone = e2ePhone();
    receive(phone, 'Quiero cita el lunes', `e2e.Lucía ${RUN}`);
    relayPass(); // what other specs left in the outbox is delivered first
    const booking = await onlineBooking(context, 'yes', phone);
    expect(booking.status).toBe('pending');
    await post(context, '/appointment/appointments/confirm', { id: booking.id }, 200);
    expect(sentTo(phone)).toEqual([]); // nothing leaves inside the request that confirmed

    relayPass();
    await expect.poll(() => sentTo(phone).length).toBe(1);
    const [notice] = sentTo(phone);
    expect(notice).toMatch(/^text\|[a-z]+\|Confirmed! We are expecting you on Monday, .+ at 10:00 for your E2E Fsm Haircut yes .+ with E2E Fsm Ana yes .+\.\|/);
    await expect.poll(() => handedOver(sentTo(phone)[0])).toBe(true);
    relayPass();
    expect(sentTo(phone)).toHaveLength(1);

    // Step 6: a booking born confirmed («Online bookings confirm themselves») tells her too.
    await autoConfirm(context, true);
    const other = e2ePhone();
    receive(other, 'Otra cita, por favor', `e2e.Marta ${RUN}`);
    const born = await onlineBooking(context, 'born', other);
    expect(born.status).toBe('confirmed');
    relayPass();
    await expect.poll(() => sentTo(other).length).toBe(1);
    expect(sentTo(other)[0]).toContain('for your E2E Fsm Haircut born');

    // A customer whose number never wrote gets nothing: the run stops at its own step, without an error.
    const stranger = e2ePhone();
    await onlineBooking(context, 'no', stranger);
    relayPass();
    expect(sentTo(stranger)).toEqual([]);
    const flowId = psql(`select id from flow_flow where recipe = '${REF}' and deleted_at is null`);
    const runs = await api<{ rows: { status: string }[] }>(context, A, 'GET', `/flow/runs?flow_id=${flowId}`);
    expect(runs.data.rows.map((row) => row.status).sort()).toEqual(['stopped', 'succeeded', 'succeeded']);
  } finally {
    await post(context, '/appointment/settings', settings, 200);
    await context.close();
  }
});

/** The business's day `days` from today on its wall clock (Madrid in phase 1): `YYYY-MM-DD` and its weekday
 *  (0 = Monday), inside Reservas' 30 days ahead. */
function madridDay(days: number): { date: string; weekday: number } {
  const date = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Madrid', year: 'numeric', month: '2-digit', day: '2-digit' }).format(
    new Date(Date.now() + days * 86_400_000),
  );
  return { date, weekday: (new Date(`${date}T00:00:00Z`).getUTCDay() + 6) % 7 };
}

/** The first Saturday at least `days` from today on the business's wall clock: the reservation's day is a Saturday
 *  on purpose, so its notice always says «sábado», accent included (it failed only on the runs that fell on one). */
function madridSaturday(days: number): { date: string; weekday: number } {
  const soon = madridDay(days);
  const saturday = new Date(`${soon.date}T00:00:00Z`);
  saturday.setUTCDate(saturday.getUTCDate() + ((5 - soon.weekday + 7) % 7));
  return { date: saturday.toISOString().slice(0, 10), weekday: 5 };
}

/** `date` (`YYYY-MM-DD`) as the Hub says a day in Spanish, weekday first («sábado, 7 de noviembre de 2026»: `day_label`
 *  of apps/schedule): what a notice must name, not just any word with a shape of day. */
const spanishDay = (date: string): string =>
  new Intl.DateTimeFormat('es-ES', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' }).format(
    new Date(`${date}T00:00:00Z`),
  );

// flow: flow-send-message
test('flow-send-message: the day a notice is expected to name reads as the Hub writes it, any weekday and month', () => {
  // Seven days in a row (`miércoles` and `sábado` carry an accent) and the twelve months, against `day_label` itself.
  const week = Array.from({ length: 7 }, (_, n) => `2026-11-${String(2 + n).padStart(2, '0')}`);
  const months = Array.from({ length: 12 }, (_, n) => `2027-${String(n + 1).padStart(2, '0')}-15`);
  const dates = [...week, ...months];
  const code = [
    'import datetime as dt, json',
    'from apps.schedule.queries import day_label',
    `print(json.dumps([day_label(dt.date.fromisoformat(d), "es") for d in ${JSON.stringify(dates)}]))`,
  ].join('\n');
  const out = spawnSync('uv', ['run', 'python', 'manage.py', 'shell', '-c', code], { cwd: HUB_DIR, env: process.env, encoding: 'utf8' });
  expect(out.status, `day_label: ${out.stderr}`).toBe(0);
  const hub = JSON.parse(out.stdout.trim().split('\n').at(-1) ?? '[]') as string[];
  expect(dates.map(spanishDay)).toEqual(hub);
  expect(new Set(hub.slice(0, 7).map((label) => label.split(',')[0])).size).toBe(7);
});

/** The owner on `a` in Spanish (the Hub's language cookie, as the sign-in sets it), at `next`. */
async function spanishOwner(browser: Browser, next: string, viewport: { width: number; height: number }) {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'es-ES' });
  const page = await context.newPage();
  await login(page, A, next);
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}${next}`);
  await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
  return { context, page };
}

// flow: WHATSAPP_INBOX-F26 RESERVATION-F19
test('WHATSAPP_INBOX-F26 (y RESERVATION-F19): confirming a reservation in Reservas tells the guest by WhatsApp through erplora.com, once', async ({
  browser,
}) => {
  test.setTimeout(240_000);
  const { context, page } = await spanishOwner(browser, '/flow/automations', FLOW_VIEWPORTS[2]);
  const day = madridSaturday(3);
  const current = await api<Record<string, unknown>>(context, A, 'GET', '/reservation/settings');
  expect(current.status).toBe(200);
  try {
    // The book open on the reservation's day: a slot all day and Schedules open 24 hours, whatever the dev
    // database's hours; «Confirmar solas las reservas nuevas» off («I review them first»).
    await post(context, '/reservation/time_slots', { day_of_week: day.weekday, start_time: '00:00', end_time: '23:59', max_reservations: SLOT_SENTINEL });
    await post(context, '/schedule/overrides', {
      start_date: day.date,
      end_date: day.date,
      reason: `${TAG} open ${RUN}`,
      is_closed: false,
      intervals: [{ open_time: '00:00', close_time: '00:00' }],
    });
    await post(context, '/reservation/settings', { auto_confirm: false }, 200);

    // FLOW-F33: the inbox's table notice, opened and turned on from its card under the gallery, in Spanish.
    const card = shown(page).locator(`[data-testid="flow-recipe-${TABLE_REF}"]`);
    await expect(card).toContainText('Avisar por WhatsApp al cliente cuando se confirma su reserva');
    await card.locator(`[data-testid="flow-recipe-open-${TABLE_REF}"]`).click();
    const recipePanel = shown(page).locator(`[data-testid="flow-recipe-panel-${TABLE_REF}"]`);
    await expect(recipePanel).toContainText('solo al número exacto de la reserva');
    await expect(recipePanel).toContainText('«reservation_confirmed»');
    for (const viewport of FLOW_VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await card.scrollIntoViewIfNeeded();
      await expect(recipePanel).toBeVisible();
      await settled(page);
      await noHorizontalScroll(page, `WHATSAPP_INBOX-F26 card ${viewport.label}`);
      await page.screenshot({ path: shot(`${TABLE_TASK}-${viewport.label}`) });
    }
    await page.setViewportSize(FLOW_VIEWPORTS[2]);
    await shown(page).locator(`[data-testid="flow-recipe-enable-${TABLE_REF}"]`).click();
    await expect.poll(() => psql(`select enabled from flow_flow where recipe = '${TABLE_REF}' and deleted_at is null`)).toBe('t');

    // The guest wrote from her number; Reservas takes her table for four (her card is made in Customers).
    const phone = e2ePhone();
    receive(phone, 'Mesa para 4, por favor', `e2e.Lucía mesa ${RUN}`);
    relayPass(); // what other specs left in the outbox is delivered first
    const guest = `${TAG} Lucía mesa ${RUN}`;
    const reservation = await post<{ id: string; status: string }>(context, '/reservation/reservations', {
      guest_name: guest,
      guest_phone: phone,
      date: day.date,
      time: '21:00',
      party_size: 4,
    });
    expect(reservation.status).toBe('pending');
    relayPass();
    expect(sentTo(phone)).toEqual([]); // a pending reservation tells nobody

    // RESERVATION-F07: «Confirmar» in Reservas, found by searching the whole book for the guest.
    await page.goto(`${A}/reservation/reservations`);
    await shown(page).locator('[data-testid=reservation-list-search] input').fill(guest);
    await rowAction(page, 'reservation-list', reservation.id, 'confirm');
    await expect.poll(() => psql(`select status from reservation_reservation where id = '${reservation.id}'`)).toBe('confirmed');
    expect(sentTo(phone)).toEqual([]); // nothing leaves inside the request that confirmed

    relayPass();
    await expect.poll(() => sentTo(phone).length).toBe(1);
    const [notice] = sentTo(phone);
    expect(spanishDay(day.date)).toMatch(/^sábado, /);
    expect(notice.split('|').slice(0, 3)).toEqual([
      'text',
      expect.stringMatching(/^[a-z]+$/),
      `¡Confirmada! Te esperamos el ${spanishDay(day.date)} a las 21:00, mesa para 4.`,
    ]);
    await expect.poll(() => handedOver(sentTo(phone)[0])).toBe(true);
    relayPass();
    expect(sentTo(phone)).toHaveLength(1);

    // Any other change of status tells nobody: cancelling it sends nothing more.
    await post(context, '/reservation/reservations/cancel', { id: reservation.id }, 200);
    relayPass();
    expect(sentTo(phone)).toHaveLength(1);
    const flowId = psql(`select id from flow_flow where recipe = '${TABLE_REF}' and deleted_at is null`);
    const runs = await api<{ rows: { status: string }[] }>(context, A, 'GET', `/flow/runs?flow_id=${flowId}`);
    expect(runs.data.rows.map((row) => row.status)).toEqual(['succeeded']);

    // The notice in her conversation of the inbox, in every size.
    await page.goto(`${A}/whatsapp_inbox/inbox`);
    await shown(page).locator('[data-testid=whatsapp-inbox-search] input').fill(phone.slice(3));
    await shown(page).locator('[data-testid=whatsapp-inbox-row]', { hasText: phone.slice(3) }).click();
    const bubble = shown(page)
      .locator('[data-testid=whatsapp-inbox-detail] [data-testid=whatsapp-inbox-message][data-side=outbound]')
      .filter({ hasText: '¡Confirmada! Te esperamos el' });
    await expect(bubble).toHaveCount(1);
    for (const viewport of FLOW_VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await expect(bubble).toBeVisible();
      await expect(bubble).toContainText(`Te esperamos el ${spanishDay(day.date)} a las 21:00, mesa para 4.`);
      await settled(page);
      await noHorizontalScroll(page, `WHATSAPP_INBOX-F26 chat ${viewport.label}`);
      await page.screenshot({ path: shot(`${TABLE_TASK}-chat-${viewport.label}`) });
    }
    // The owner's Spanish session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
    if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  } finally {
    await post(context, '/reservation/settings', { auto_confirm: current.data.auto_confirm }, 200);
    await context.close();
  }
});

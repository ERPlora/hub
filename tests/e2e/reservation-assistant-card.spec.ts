// hub#549: the dangerous card titles the reservation, slot, blocked date or waitlist entry it acts on,
// in Spanish and English, never «Registro»/«Record». hub#550: booking or changing a reservation names its table with
// its zone («7 (Terraza)»), as Tables does, since table 7 repeats across zones. Every confirmation is cancelled: nothing
// changes.
// flow: RESERVATION-F01 RESERVATION-F02 RESERVATION-F06 RESERVATION-F08 RESERVATION-F09 RESERVATION-F10 RESERVATION-F15 RESERVATION-F20 RESERVATION-F23 BASE-F97
import { type BrowserContext, expect, test } from '@playwright/test';

import { cancel, cardSpec, datumOf, ownerIn, VIEWPORTS } from './assistant-card-helpers';
import { card, openPanel } from './assistant-real';
import { cleanUp as customersCleanUp } from './customer-helpers';
import { A, api, capture, psql } from './helpers';
import { post } from './service-helpers';

const NEEDED = ['customer', 'tax', 'sale', 'table', 'schedule', 'reservation'];
const TAG = 'e2e.Tarjeta reservas';
const SENTINEL = 78;
const WORDS = {
  es: { reservation: 'Reserva', slot: 'Franja', blocked: 'Fecha bloqueada', entry: 'Entrada de la lista de espera' },
  en: { reservation: 'Reservation', slot: 'Time slot', blocked: 'Blocked date', entry: 'Waitlist entry' },
};
const GENERIC = { es: 'Registro:', en: 'Record:' };
const TABLE = { es: 'Mesa', en: 'Table' };
const ROOM = `${TAG} Sala`;
const TERRACE = `${TAG} Terraza`;

function dayAfter(days: number): { date: string; weekday: number } {
  const at = new Date(Date.now() + days * 86_400_000);
  const date = at.toISOString().slice(0, 10);
  return { date, weekday: (at.getUTCDay() + 6) % 7 };
}

const TOMORROW = dayAfter(1);
const LATER = dayAfter(2);

function cleanUp(): void {
  const reservations = `select id from reservation_reservation where guest_name like '${TAG}%'`;
  const tables = `select id from table_table where zone_id in (select id from table_zone where name like '${TAG}%')`;
  psql(
    [
      `delete from table_hold where source_ref in (select id::text from reservation_reservation where guest_name like '${TAG}%')`,
      `delete from table_hold where table_id in (${tables})`,
      `update reservation_waitlistentry set reservation_id = null where guest_name like '${TAG}%'`,
      `delete from reservation_waitlistentry where guest_name like '${TAG}%'`,
      `delete from reservation_reservation where id in (${reservations})`,
      `delete from reservation_blockeddate where reason like '${TAG}%'`,
      `delete from reservation_timeslot where max_reservations = ${SENTINEL}`,
      `delete from schedule_overrideinterval where override_id in (select id from schedule_override where reason like '${TAG}%')`,
      `delete from schedule_override where reason like '${TAG}%'`,
      `delete from table_table where id in (${tables})`,
      `delete from table_zone where name like '${TAG}%'`,
    ].join('; '),
  );
  customersCleanUp();
}

cardSpec(NEEDED, cleanUp);

interface RecordOut {
  id: string;
  label: string;
  status?: string;
}

interface Books {
  reservation: RecordOut;
  slot: RecordOut;
  blocked: RecordOut;
  entry: RecordOut;
}

async function detail(context: BrowserContext, path: string, id: string): Promise<RecordOut> {
  const read = await api<RecordOut>(context, A, 'GET', `${path}?id=${id}`);
  expect(read.status, JSON.stringify(read.data)).toBe(200);
  return read.data;
}

async function makeBooks(context: BrowserContext): Promise<Books> {
  await post(context, '/schedule/overrides', {
    start_date: TOMORROW.date,
    end_date: TOMORROW.date,
    reason: `${TAG} abierto`,
    is_closed: false,
    intervals: [{ open_time: '00:00', close_time: '00:00' }],
  });
  const slot = await post<RecordOut>(context, '/reservation/time_slots', {
    day_of_week: TOMORROW.weekday,
    start_time: '00:00',
    end_time: '23:59',
    max_reservations: SENTINEL,
  });
  const reservation = await post<RecordOut>(context, '/reservation/reservations', {
    guest_name: `${TAG} Ana`,
    guest_phone: `6${String(Date.now()).slice(-8)}`,
    date: TOMORROW.date,
    time: '21:00',
    party_size: 2,
  });
  const blocked = await post<RecordOut>(context, '/reservation/blocked_dates', {
    date: LATER.date,
    reason: `${TAG} cierre`,
    is_full_day: true,
  });
  const entry = await post<RecordOut>(context, '/reservation/waitlist', {
    guest_name: `${TAG} Luis`,
    date: LATER.date,
    preferred_time: '21:00',
    party_size: 2,
  });
  return {
    reservation: await detail(context, '/reservation/reservations/detail', reservation.id),
    slot: await detail(context, '/reservation/time_slots/detail', slot.id),
    blocked: await detail(context, '/reservation/blocked_dates/detail', blocked.id),
    entry: await detail(context, '/reservation/waitlist/detail', entry.id),
  };
}

/** Table 7 of the room and table 7 of the terrace: the same number in two zones, as Tables reads them. */
async function makeSevens(context: BrowserContext): Promise<[RecordOut, RecordOut]> {
  const sevens: RecordOut[] = [];
  for (const name of [ROOM, TERRACE]) {
    const zone = await post<RecordOut>(context, '/table/zones', { name });
    const table = await post<RecordOut>(context, '/table/tables', { zone_id: zone.id, number: '7', capacity: 4 });
    sevens.push(await detail(context, '/table/tables/detail', table.id));
  }
  return [sevens[0], sevens[1]];
}

for (const language of ['es', 'en'] as const) {
  const words = WORDS[language];

  test(`reservation-assistant-card — in ${language}, booking and changing a reservation name its table with its zone`, async ({
    browser,
  }) => {
    const [context, page] = await ownerIn(browser, language);
    const books = await makeBooks(context);
    const [room, terrace] = await makeSevens(context);
    expect([room.label, terrace.label]).toEqual([`7 (${ROOM})`, `7 (${TERRACE})`]);
    await page.setViewportSize({ width: 1440, height: 900 });
    await openPanel(page);

    // A normal write paints its first three data in one line (BASE-F97): booking carries its table as its fifth datum,
    // a change says its reservation and, right after it, the new table.
    const booking = await datumOf(
      page,
      'reservation__reservation__create',
      { guest_name: `${TAG} Marta`, date: TOMORROW.date, time: '21:30', party_size: 2, table_id: terrace.id },
      'table_id',
    );
    expect([booking.label, booking.value]).toEqual([TABLE[language], terrace.label]);
    await cancel(page);

    const change = await datumOf(
      page,
      'reservation__reservation__update',
      { id: books.reservation.id, table_id: terrace.id },
      'table_id',
    );
    expect([change.label, change.value]).toEqual([TABLE[language], terrace.label]);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(`${books.reservation.label} · ${terrace.label}`);
      await expect(card(page)).not.toContainText(room.label);
      await capture(page, `hub-550-update-table-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    const left = await api<{ table_id: string | null }>(context, A, 'GET', `/reservation/reservations/detail?id=${books.reservation.id}`);
    expect(left.data.table_id).toBeNull();
    expect(psql(`select count(*) from reservation_reservation where guest_name = '${TAG} Marta'`)).toBe('0');
    await context.close();
  });

  test(`reservation-assistant-card — in ${language}, every dangerous write titles its record`, async ({ browser }) => {
    const [context, page] = await ownerIn(browser, language);
    const books = await makeBooks(context);
    await page.setViewportSize({ width: 1440, height: 900 });
    await openPanel(page);

    const cases = [
      { action: 'delete', tool: 'reservation__reservation__delete', record: books.reservation, title: words.reservation, data: {} },
      { action: 'no-show', tool: 'reservation__reservation__no_show', record: books.reservation, title: words.reservation, data: {} },
      { action: 'cancel', tool: 'reservation__reservation__cancel', record: books.reservation, title: words.reservation, data: { reason: `${TAG} llamó` } },
      { action: 'slot-delete', tool: 'reservation__time_slot__delete', record: books.slot, title: words.slot, data: {} },
      { action: 'blocked-delete', tool: 'reservation__blocked_date__delete', record: books.blocked, title: words.blocked, data: {} },
      { action: 'waitlist-delete', tool: 'reservation__waitlist__delete', record: books.entry, title: words.entry, data: {} },
    ];

    for (const one of cases) {
      const field = await datumOf(page, one.tool, { id: one.record.id, ...one.data });
      expect([field.label, field.value]).toEqual([one.title, one.record.label]);
      for (const vp of VIEWPORTS) {
        await page.setViewportSize({ width: vp.width, height: vp.height });
        await expect(card(page)).toContainText(`${one.title}: ${one.record.label}`);
        await expect(card(page)).not.toContainText(GENERIC[language]);
        await capture(page, `hub-549-${one.action}-${language}-${vp.label}`);
      }
      await page.setViewportSize({ width: 1440, height: 900 });
      await cancel(page);
    }

    for (const [path, record] of [
      ['/reservation/reservations/detail', books.reservation],
      ['/reservation/time_slots/detail', books.slot],
      ['/reservation/blocked_dates/detail', books.blocked],
      ['/reservation/waitlist/detail', books.entry],
    ] as const) {
      expect((await detail(context, path, record.id)).label).toBe(record.label);
    }
    await context.close();
  });
}

// hub#635: since hub#416 the assistant's card left out every id its schema does not mark, so «delete these two
// appointments», «delete Lucía's repeating appointment», «remove Ana's training» or «block Ana's afternoon» said no
// appointment, no series, no block and no professional — and a bulk delete said «Ids» with nothing in it. Now each
// appointment goes by its customer, day, hour and professional, a series as the series list titles one (customer ·
// repetition · weekday · hour), a block by its title, day, hour and professional and a professional by their name,
// read as the person, in their language, never by an id. End to end with the stack's SaaS gateway and the e2e's provider
// (assistant-provider.ts, `E2E-ASK <tool> <JSON>`): the SaaS must be seeded with it (README of this folder, «El
// asistente»). Cancelled, nothing changes. What this file creates is named «E2E Tarjeta cita …» and goes away before and
// after; the apps it turns on are turned off again.
// flow: APPOINTMENT-F11 APPOINTMENT-F15 APPOINTMENT-F16 APPOINTMENT-F21 BASE-F97
import { type BrowserContext, expect, test } from '@playwright/test';

import { aMonday, salonCleanUp } from './appointment-helpers';
import { AN_ID, cancel, cardSpec, datumOf, ownerIn, VIEWPORTS } from './assistant-card-helpers';
import { card, openPanel } from './assistant-real';
import { A, api, capture, psql } from './helpers';
import { post } from './service-helpers';

const TAG = 'E2E Tarjeta cita';
const DAY = aMonday();

/** What the card calls each record, and how a weekly series repeats, by the language of the card. */
const WORDS = {
  es: { appointments: 'Citas', series: 'Cita periódica', block: 'Bloqueo', professional: 'Profesional', weekly: 'Cada semana · Lunes' },
  en: { appointments: 'Appointments', series: 'Repeating appointment', block: 'Blocked period', professional: 'Professional', weekly: 'Every week · Monday' },
};
/** The words the card would call them by if nothing titled them, in each language. */
const UNTITLED = { es: ['Registro', 'Ids', 'Staff Id'], en: ['Record', 'Ids', 'Staff Id'] };

function cleanUp(): void {
  const customers = `select id from customer_customer where name like '${TAG}%'`;
  const series = `select id from appointment_recurring where customer_id in (${customers})`;
  psql(
    [
      ...salonCleanUp(TAG),
      `delete from appointment_recurringservice where recurring_id in (${series})`,
      `delete from appointment_recurring where id in (${series})`,
      `delete from appointment_blockedtime where title like '${TAG}%'`,
      `delete from customer_activity where customer_id in (${customers})`,
      `delete from customer_consent where customer_id in (${customers})`,
      `delete from customer_customer where name like '${TAG}%'`,
    ].join('; '),
  );
}

cardSpec(['customer', 'service', 'staff', 'schedule', 'appointment'], cleanUp);

interface Diary {
  customer: { id: string; name: string };
  member: { id: string; full_name: string };
  other: { id: string; full_name: string };
  appointment: { id: string; number: string };
  series: { id: string };
  block: { id: string; title: string };
}

/** A customer, a professional who performs a cut on an open Monday, an appointment, a weekly series and a block of that
 *  professional, through each app's own API. */
async function aDiary(context: BrowserContext, language: string): Promise<Diary> {
  const customer = await post<Diary['customer']>(context, '/customer/customers', {
    name: `${TAG} Lucía ${language}`,
    phone: `6${String(Date.now()).slice(-8)}`,
  });
  const service = await post<{ id: string }>(context, '/service/services', {
    name: `${TAG} Corte`,
    price: 2000,
    duration_minutes: 30,
    tax_category_key: 'service.generic',
  });
  const member = await post<Diary['member']>(context, '/staff/members', { first_name: `${TAG} Ana`, last_name: language });
  const other = await post<Diary['other']>(context, '/staff/members', { first_name: `${TAG} Bea`, last_name: language });
  await post(context, '/service/assignments/assign', { service_id: service.id, member_id: member.id }, 200);
  await post(context, '/schedule/special_days', {
    date: DAY,
    name: `${TAG} Abierto`,
    is_closed: false,
    intervals: [{ open_time: '09:00', close_time: '18:00' }],
  });
  const appointment = await post<Diary['appointment']>(context, '/appointment/appointments', {
    customer_id: customer.id,
    services: [{ service_id: service.id }],
    staff_id: member.id,
    start: `${DAY} 10:00`,
  });
  const created = await post<{ recurring: Diary['series'] }>(context, '/appointment/recurring', {
    customer_id: customer.id,
    services: [{ service_id: service.id }],
    staff_id: member.id,
    frequency: 'weekly',
    start_date: DAY,
    time: '16:00',
    max_occurrences: 2,
  });
  const series = created.recurring;
  const block = await post<Diary['block']>(context, '/appointment/blocked_times', {
    title: `${TAG} Formación`,
    start: `${DAY} 14:00`,
    end: `${DAY} 15:00`,
    staff_id: member.id,
  });
  return { customer, member, other, appointment, series, block };
}

/** How many of the diary's records are still there: the appointment, the series alive and the block. */
function stillThere(diary: Diary): string {
  return psql(
    `select (select count(*) from appointment_appointment where id = '${diary.appointment.id}') || '/' ||` +
      ` (select count(*) from appointment_recurring where id = '${diary.series.id}' and deleted_at is null) || '/' ||` +
      ` (select count(*) from appointment_blockedtime where id = '${diary.block.id}')`,
  );
}

for (const language of ['es', 'en'] as const) {
  const words = WORDS[language];

  test(`appointment-assistant-card — in ${language}, a write of Appointments says which appointment, series, block and professional, never by an id`, async ({ browser }) => {
    test.slow();
    const [context, page] = await ownerIn(browser, language);
    const diary = await aDiary(context, language);
    expect(stillThere(diary)).toBe('1/1/1');
    const detail = await api<{ label: string }>(context, A, 'GET', `/appointment/appointments/detail?id=${diary.appointment.id}`);
    expect(detail.status).toBe(200);
    await page.setViewportSize({ width: 1440, height: 900 });
    await openPanel(page);

    // «Borra estas citas», dangerous: each appointment as the Agenda tells it, under «Citas», in every size.
    const deleted = await datumOf(page, 'appointment__appointment__bulk_delete', { ids: [diary.appointment.id] }, 'ids');
    expect([deleted.label, deleted.value]).toEqual([words.appointments, [detail.data.label]]);
    expect(detail.data.label).toContain(diary.member.full_name);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(diary.customer.name);
      await expect(card(page)).not.toContainText(AN_ID);
      for (const untitled of UNTITLED[language]) await expect(card(page)).not.toContainText(`${untitled}:`);
      await capture(page, `hub-635-bulk-delete-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // «Borra la cita periódica de Lucía»: the series as its list titles one.
    const series = await datumOf(page, 'appointment__recurring__delete', { id: diary.series.id });
    expect([series.label, series.value]).toEqual([words.series, `${diary.customer.name} · ${words.weekly} · 16:00`]);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(words.weekly);
      await expect(card(page)).not.toContainText(AN_ID);
      await capture(page, `hub-635-series-delete-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // «Quita la formación de Ana»: the block by its title, its day, its hour and its professional.
    const block = await datumOf(page, 'appointment__blocked_time__delete', { id: diary.block.id });
    expect(block.label).toBe(words.block);
    expect(String(block.value).startsWith(`${diary.block.title} · `)).toBe(true);
    expect(String(block.value).endsWith(` · 14:00 · ${diary.member.full_name}`)).toBe(true);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(diary.block.title);
      await expect(card(page)).not.toContainText(AN_ID);
      await capture(page, `hub-635-block-delete-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // «Bloquea la tarde de Ana»: the professional by their name. A write that is not dangerous goes in one line, its
    // first three data (@erplora/ui ``cardLine``), and the professional is a block's sixth: the card sends it named.
    const blocking = await datumOf(
      page,
      'appointment__blocked_time__create',
      { title: `${TAG} Descanso`, start: `${DAY} 17:00`, end: `${DAY} 18:00`, staff_id: diary.member.id },
      'staff_id',
    );
    expect([blocking.label, blocking.value]).toEqual([words.professional, diary.member.full_name]);
    await cancel(page);

    // «Pasa la cita de Lucía a Bea»: in that one line, the appointment as the Agenda tells it and Bea by her name.
    const handedOver = await datumOf(
      page,
      'appointment__appointment__update',
      { id: diary.appointment.id, staff_id: diary.other.id },
      'staff_id',
    );
    expect([handedOver.label, handedOver.value]).toEqual([words.professional, diary.other.full_name]);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(`${detail.data.label} · ${diary.other.full_name}`);
      await expect(card(page)).not.toContainText(AN_ID);
      await capture(page, `hub-635-update-staff-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // Cancelled, nothing changed: the appointment (still Ana's), the series and the block there, and no other block.
    expect(stillThere(diary)).toBe('1/1/1');
    expect(psql(`select staff_id from appointment_appointment where id = '${diary.appointment.id}'`)).toBe(diary.member.id);
    expect(psql(`select count(*) from appointment_blockedtime where title = '${TAG} Descanso'`)).toBe('0');
    await context.close();
  });
}

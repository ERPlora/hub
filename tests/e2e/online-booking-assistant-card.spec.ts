// hub#673: since hub#416 the assistant's card left out every id its schema does not mark, so «cancel Lucía's booking»,
// «confirm the booking APT-…» or a booking of the page said no booking, no service and no professional. Now a booking is
// named as the diary names it — its customer, its day, its time and its professional, as the inbox's «Cancel …'s
// booking?» dialog does —, and a service and a professional of the page's booking by their names, read as the person,
// in their language, never by an id. End to end with the stack's SaaS gateway and the e2e's provider
// (assistant-provider.ts, `E2E-ASK <tool> <JSON>`): the SaaS must be seeded with it (README of this folder, «El
// asistente»). Cancelled, nothing changes. What this file creates is named «E2E Tarjeta reserva …» and goes away
// before and after; the apps it turns on are turned off again.
// flow: ONLINE_BOOKING-F01 ONLINE_BOOKING-F02 ONLINE_BOOKING-F05 BASE-F97
import { type BrowserContext, expect, test } from '@playwright/test';

import { cancel, cardSpec, datumOf, fieldsOf, ownerIn, VIEWPORTS } from './assistant-card-helpers';
import { card, openPanel } from './assistant-real';
import { aMonday, openForACut, salonCleanUp } from './appointment-helpers';
import { A, api, capture, psql } from './helpers';
import { post } from './service-helpers';

/** A business is born with every app off; Online booking requires the diary and what the diary requires. */
const NEEDED = ['tax', 'staff', 'customer', 'schedule', 'service', 'appointment', 'online_booking'];
const TAG = 'E2E Tarjeta reserva';
const DAY = aMonday();

/** What the screens call each record, by the language of the card: the bookings list and the booking page. */
const WORDS = {
  es: { booking: 'Reserva', services: 'Servicios', professional: 'Profesional' },
  en: { booking: 'Booking', services: 'Services', professional: 'Professional' },
};
/** The word the card calls a record by when nothing titles it, in each language. */
const GENERIC = { es: 'Registro', en: 'Record' };

/** Every appointment, open day, service and professional this file made, then its customers. */
function cleanUp(): void {
  const customers = `select id from customer_customer where name like '${TAG}%'`;
  psql(
    [
      ...salonCleanUp(TAG),
      `delete from customer_activity where customer_id in (${customers})`,
      `delete from customer_consent where customer_id in (${customers})`,
      `delete from customer_customer where name like '${TAG}%'`,
    ].join('; '),
  );
}

cardSpec(NEEDED, cleanUp);

interface Salon {
  service: { id: string; name: string };
  member: { id: string; full_name: string };
  booking: { id: string; number: string; status: string };
}

/** A service a professional performs, the day open and Lucía's online booking at 10:00, through each app's own API. */
async function aSalon(context: BrowserContext): Promise<Salon> {
  const customer = await post<{ id: string }>(context, '/customer/customers', {
    name: `${TAG} Lucía`,
    phone: `6${String(Date.now()).slice(-8)}`,
  });
  const { service, member } = await openForACut(context, TAG, DAY);
  const booking = await post<Salon['booking']>(context, '/appointment/appointments', {
    customer_id: customer.id,
    services: [{ service_id: service.id }],
    staff_id: member.id,
    start: `${DAY}T10:00`,
    source: 'online',
  });
  return { service, member, booking };
}

/** How the diary says the booking to the person, in their language (Citas' own read). */
async function diarySays(context: BrowserContext, id: string): Promise<{ label: string; status: string }> {
  const read = await api<{ label: string; status: string }>(context, A, 'GET', `/appointment/appointments/detail?id=${id}`);
  expect(read.status, JSON.stringify(read.data)).toBe(200);
  return read.data;
}

for (const language of ['es', 'en'] as const) {
  const words = WORDS[language];

  test(`online-booking-assistant-card — in ${language}, a write of Online booking says which booking, services and professional, never by an id`, async ({ browser }) => {
    const [context, page] = await ownerIn(browser, language);
    const { service, member, booking } = await aSalon(context);
    const { label, status } = await diarySays(context, booking.id);
    expect(label).toContain(`${TAG} Lucía`);
    expect(label).toContain('10:00');
    expect(label).toContain(member.full_name);
    await page.setViewportSize({ width: 1440, height: 900 });
    await openPanel(page);

    // «Cancela la reserva de Lucía», a dangerous write: the booking as the diary says it, titled as the list calls one,
    // in every size.
    const cancelled = await datumOf(page, 'online_booking__booking__cancel', { id: booking.id, reason: `${TAG} llamó` });
    expect([cancelled.label, cancelled.value]).toEqual([words.booking, label]);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(`${words.booking}: ${label}`);
      await expect(card(page)).not.toContainText(GENERIC[language]);
      await capture(page, `hub-673-cancel-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // «Confirma la reserva APT-…»: a write that is not dangerous is said in one line, the booking by its name.
    const confirmed = await datumOf(page, 'online_booking__booking__confirm', { id: booking.id });
    expect([confirmed.label, confirmed.value]).toEqual([words.booking, label]);
    await expect(card(page)).toContainText(label);
    await cancel(page);

    // A booking of the page: each service and the professional by their names, under the words of the booking page.
    const booked = await fieldsOf(page, 'online_booking__public__book', {
      service_ids: [service.id],
      staff_id: member.id,
      start: `${DAY}T12:00`,
      name: `${TAG} Marta`,
      phone: '612345678',
    });
    const said = Object.fromEntries(booked.map((field) => [field.name, [field.label, field.value]]));
    expect([said.service_ids, said.staff_id]).toEqual([
      [words.services, [service.name]],
      [words.professional, member.full_name],
    ]);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(service.name);
      await expect(card(page)).toContainText(member.full_name);
      await capture(page, `hub-673-public-book-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // Cancelled, nothing changed: the booking as it was, and nobody booked for Marta.
    expect((await diarySays(context, booking.id)).status).toBe(status);
    expect(psql(`select count(*) from customer_customer where name = '${TAG} Marta'`)).toBe('0');
    await context.close();
  });
}

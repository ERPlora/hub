// Online booking → the preview of the public booking page (WORKBOOK «Vista previa de la reserva», development
// only): the customer's flow with the same public operations the page of base will call — pick services, a
// professional or «No preference», a day and a free time, leave name and mobile, book; then see the booking
// and cancel it with the personal link. Refusals are said where they happen, under their field.
import { describe, expect, it } from 'vitest';

import type { BookedOut, PageOut, PublicBookingOut, PublicServiceOut, PublicSlotsOut } from '../operations';
import { click, ionChecked, ionValue, type MountOptions, mountOnlineBooking, page, settle } from '../__tests__/mount-online-booking';
import PreviewPage from './PreviewPage.vue';

const PAGE: PageOut = {
  title: 'Salón Lucía',
  welcome_message: 'Book your next visit',
  primary_color: '#6366f1',
  logo_url: '',
  require_email: false,
  allow_staff_selection: true,
  allow_notes: true,
  cancellation_policy: 'Cancel 24 h ahead.',
  min_booking_notice: 60,
  max_advance_booking: 90,
  allow_customer_cancellation: true,
  cancellation_notice_hours: 24,
  timezone: 'Europe/Madrid',
};
const ANA = { id: 'm1', name: 'Ana López' };
const BEA = { id: 'm2', name: 'Bea Ruiz' };
const SERVICES: PublicServiceOut[] = [
  { id: 'v1', name: 'Haircut', description: '', category: 'Hair', price: 2000, duration_minutes: 30, professionals: [ANA, BEA] },
  { id: 'v2', name: 'Colour', description: '', category: 'Hair', price: null, duration_minutes: null, professionals: [BEA] },
];
const SLOTS: PublicSlotsOut = {
  date: '2030-03-05',
  timezone: 'Europe/Madrid',
  duration_minutes: 30,
  slots: [
    { start: '2030-03-05T10:00:00+01:00', end: '2030-03-05T10:30:00+01:00', professionals: [ANA, BEA] },
    { start: '2030-03-05T10:30:00+01:00', end: '2030-03-05T11:00:00+01:00', professionals: [BEA] },
  ],
};
const BOOKED: BookedOut = {
  number: 'APT-20300304-0001',
  status: 'confirmed',
  start: '2030-03-05T10:00:00+01:00',
  end: '2030-03-05T10:30:00+01:00',
  timezone: 'Europe/Madrid',
  service_names: 'Haircut',
  staff_name: 'Ana López',
  message: 'Your booking is confirmed. See you soon!',
  token: 't'.repeat(43),
};
const SEEN: PublicBookingOut = {
  number: BOOKED.number,
  status: 'confirmed',
  start: BOOKED.start,
  end: BOOKED.end,
  timezone: 'Europe/Madrid',
  service_names: 'Haircut',
  staff_name: 'Ana López',
  can_cancel: true,
  cancel_until: '2030-03-04T10:00:00+01:00',
  cancellation_policy: 'Cancel 24 h ahead.',
};

const ROUTES = {
  '/api/online_booking/public/page': [200, PAGE],
  '/api/online_booking/public/services': [200, page(SERVICES, 2, 100)],
  '/api/online_booking/public/slots': [200, SLOTS],
  '/api/online_booking/public/book': [200, BOOKED],
  '/api/online_booking/public/booking': [200, SEEN],
  '/api/online_booking/public/cancel': [200, { ...SEEN, status: 'cancelled', can_cancel: false, cancel_until: null }],
} as Record<string, [number, unknown]>;

async function setup(options: MountOptions = {}, routes = ROUTES) {
  const m = await mountOnlineBooking(PreviewPage, { path: '/online_booking/preview', answers: routes, ...options });
  await settle();
  const el = (testid: string) => m.inDoc(`ob-preview-${testid}`) as HTMLElement & { value?: unknown; errorText?: string };
  return { ...m, el };
}

async function chooseUpToATime(s: Awaited<ReturnType<typeof setup>>) {
  await ionChecked(s.el('service-v1'), true);
  await ionValue(s.el('day'), '2030-03-05', 'ionChange');
  await settle();
  await click(s.el('time-10:00'));
}

describe('PreviewPage', () => {
  it('opens with the page’s texts and the services booked online', async () => {
    const s = await setup();
    expect(s.el('title')?.textContent).toContain('Salón Lucía');
    expect(s.find('ob-preview').text()).toContain('Book your next visit');
    expect(s.el('service-v1')?.textContent).toContain('Haircut');
    expect(s.el('service-v1')?.textContent).toContain('€20.00 · 30 min');
    expect(s.el('service-v2')?.textContent).not.toContain('€');
    expect(s.sent().map((call) => call.path)).toEqual(['/api/online_booking/public/page', '/api/online_booking/public/services']);
  });

  it('with no service booked online, says so and where to switch them on, in English and in Spanish', async () => {
    const empty = { ...ROUTES, '/api/online_booking/public/services': [200, page([], 0, 100)] } as Record<string, [number, unknown]>;
    const s = await setup({}, empty);
    expect(s.el('no-services')?.textContent).toContain('No service is booked online yet: switch them on in Settings.');
    const es = await setup({ locale: 'es' }, empty);
    expect(es.el('no-services')?.textContent).toContain('Aún no hay servicios que se reserven online: actívalos en Ajustes.');
  });

  it('asks the free times of the services, the day and the professional, and offers who does them all', async () => {
    const s = await setup();
    await ionChecked(s.el('service-v1'), true);
    await ionChecked(s.el('service-v2'), true);
    expect([...(s.el('staff')?.querySelectorAll('ion-select-option') ?? [])].map((o) => o.textContent?.trim())).toEqual([
      'No preference',
      'Bea Ruiz',
    ]);
    await ionValue(s.el('staff'), 'm2', 'ionChange');
    await ionValue(s.el('day'), '2030-03-05', 'ionChange');
    await settle();
    const asked = new URL(s.net.api.at(-1)!.url, 'http://a.localhost');
    expect(asked.pathname).toBe('/api/online_booking/public/slots');
    expect([asked.searchParams.getAll('service_ids'), asked.searchParams.get('date'), asked.searchParams.get('staff_id')]).toEqual([
      ['v1', 'v2'],
      '2030-03-05',
      'm2',
    ]);
    expect(s.el('time-10:00')?.textContent).toContain('10:00 AM');
    expect(s.el('time-10:30')).not.toBeNull();
  });

  it('books with the time, the name and the mobile, and shows the number, the message and the link', async () => {
    const s = await setup();
    await chooseUpToATime(s);
    await ionValue(s.el('name'), 'Marta Gil', 'ionInput');
    await ionValue(s.el('phone'), '612 345 678', 'ionInput');
    await click(s.el('book'));
    await settle();
    expect(s.sent().at(-1)).toEqual({
      method: 'POST',
      path: '/api/online_booking/public/book',
      query: {},
      body: { service_ids: ['v1'], start: '2030-03-05T10:00', name: 'Marta Gil', phone: '612 345 678', email: '', notes: '' },
    });
    expect(s.el('booked')?.textContent).toContain('Booking APT-20300304-0001');
    expect(s.el('booked')?.textContent).toContain('Your booking is confirmed. See you soon!');
    expect(s.el('token')?.textContent).toContain('t'.repeat(43));
  });

  it('sees the booking with the link and cancels it within the policy', async () => {
    const s = await setup();
    await chooseUpToATime(s);
    await ionValue(s.el('name'), 'Marta Gil', 'ionInput');
    await ionValue(s.el('phone'), '612345678', 'ionInput');
    await click(s.el('book'));
    await settle();
    await click(s.el('view'));
    await settle();
    expect(s.el('status')?.textContent).toContain('Confirmed');
    expect(s.el('status')?.textContent).toContain('You may cancel it until Monday, March 4, 2030 · 10:00 AM.');
    expect(s.el('status')?.textContent).toContain('Cancel 24 h ahead.');
    await click(s.el('cancel'));
    await settle();
    expect(s.sent().at(-1)).toMatchObject({ method: 'POST', path: '/api/online_booking/public/cancel', body: { token: 't'.repeat(43) } });
    expect(s.el('status')?.textContent).toContain('Cancelled');
    expect(s.el('status')?.textContent).toContain('It can no longer be cancelled online.');
  });

  it('puts a refusal under its field, and a refused time above the button', async () => {
    const routes = {
      ...ROUTES,
      '/api/online_booking/public/book': [
        422,
        { error: { code: 'invalid_payload', message: 'Invalid payload', fields: { phone: 'That mobile is not a valid number.' } } },
      ],
    } as Record<string, [number, unknown]>;
    const s = await setup({}, routes);
    await chooseUpToATime(s);
    await ionValue(s.el('name'), 'Marta', 'ionInput');
    await ionValue(s.el('phone'), '12', 'ionInput');
    await click(s.el('book'));
    await settle();
    expect(s.el('phone')?.errorText).toBe('That mobile is not a valid number.');
    expect(s.el('form-error')?.textContent).toContain('Invalid payload');
  });

  it('says the page is off when the business takes no online bookings', async () => {
    const s = await setup({}, {
      '/api/online_booking/public/page': [
        404,
        { error: { code: 'online_booking.page_disabled', message: 'This business does not take online bookings right now.' } },
      ],
    });
    expect(s.el('error')?.textContent).toContain('This business does not take online bookings right now.');
    expect(s.el('service-v1')).toBeNull();
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    expect(s.find('ob-preview').text()).toContain('Vista previa de la página de reservas');
    expect(s.el('book')?.textContent).toContain('Reservar');
  });
});

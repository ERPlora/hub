// Online booking → the booking page a customer opens without a session (`/p/<slug>/book`, ONLINE_BOOKING-F01): the
// preview's booking flow, but every call goes through base's public door (`/p/<slug>/api/<operation>`, the input as the
// JSON body) instead of the team's API, the prices are in the money the page's HTML carries (no session to read the
// business with), and the words are the customer's, not the team's.
import type { SessionMe } from '@erplora/ui/shell';
import { createMemoryHistory, createRouter } from 'vue-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import appointmentEn from '../../../appointment/frontend/locale/en.json';
import appointmentEs from '../../../appointment/frontend/locale/es.json';
import { click, ionChecked, ionValue, mountInShell, page, settle } from '../__tests__/mount-online-booking';
import en from '../locale/en.json';
import es from '../locale/es.json';
import type { BookedOut, PageOut, PublicBookingOut, PublicServiceOut, PublicSlotsOut } from '../operations';
import PublicBookingPage from './PublicBookingPage.vue';

const VISITOR: SessionMe = { user: null, permissions: [], menu: [], apps: [], language: 'en' };
const PAGE: PageOut = {
  business_name: 'Salón Lucía',
  privacy_policy_url: 'https://erplora.com/legal/privacy/',
  title: 'Salón Lucía',
  welcome_message: 'Book your next visit',
  primary_color: '#6366f1',
  logo_url: '/media/salon-lucia.png',
  require_email: false,
  allow_staff_selection: true,
  allow_notes: false,
  cancellation_policy: '',
  min_booking_notice: 60,
  max_advance_booking: 90,
  allow_customer_cancellation: true,
  cancellation_notice_hours: 24,
  timezone: 'Europe/Madrid',
};
const ANA = { id: 'm1', name: 'Ana López' };
const SERVICES: PublicServiceOut[] = [
  { id: 'v1', name: 'Haircut', description: '', category: 'Hair', price: 2000, duration_minutes: 30, professionals: [ANA] },
];
const SLOTS: PublicSlotsOut = {
  date: '2030-03-05',
  timezone: 'Europe/Madrid',
  duration_minutes: 30,
  slots: [{ start: '2030-03-05T10:00:00+01:00', end: '2030-03-05T10:30:00+01:00', professionals: [ANA] }],
};
const BOOKED: BookedOut = {
  number: 'APT-20300304-0001',
  status: 'pending',
  start: '2030-03-05T10:00:00+01:00',
  end: '2030-03-05T10:30:00+01:00',
  timezone: 'Europe/Madrid',
  service_names: 'Haircut',
  staff_name: 'Ana López',
  message: 'We have received your booking.',
  token: 't'.repeat(43),
};
const SEEN: PublicBookingOut = {
  business_name: PAGE.business_name,
  logo_url: PAGE.logo_url,
  number: BOOKED.number,
  status: 'pending',
  start: BOOKED.start,
  end: BOOKED.end,
  timezone: 'Europe/Madrid',
  service_names: 'Haircut',
  staff_name: 'Ana López',
  can_cancel: true,
  cancel_until: '2030-03-04T10:00:00+01:00',
  cancellation_policy: '',
};
const ANSWERS: Record<string, [number, unknown]> = {
  'online_booking.public.page': [200, PAGE],
  'online_booking.public.services': [200, page(SERVICES, 1, 100)],
  'online_booking.public.slots': [200, SLOTS],
  'online_booking.public.book': [200, BOOKED],
  'online_booking.public.booking': [200, SEEN],
  'online_booking.public.cancel': [200, { ...SEEN, status: 'cancelled', can_cancel: false, cancel_until: null }],
};
const DOOR = '/p/salon-lucia/api/';

/** What the page posted through the door: the operation and its body. */
let posted: { op: string; method: string; body: unknown }[] = [];

/** The door answers by operation; one it is not given hangs, as a page still loading. */
function door(answers: Record<string, [number, unknown] | 'hang'> = ANSWERS): void {
  posted = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit) => {
      const op = url.startsWith(DOOR) ? url.slice(DOOR.length) : url;
      posted.push({ op, method: String(init.method), body: JSON.parse(String(init.body ?? 'null')) });
      const answer = answers[op];
      if (answer === 'hang') return new Promise<Response>(() => {});
      const [status, body] = answer ?? [404, { error: { code: 'not_found', message: 'Not found' } }];
      return Response.json(body, { status });
    }),
  );
}

function moneyBlock(currency: string): void {
  const script = document.createElement('script');
  script.id = 'public-door';
  script.type = 'application/json';
  script.textContent = JSON.stringify({ currency, currency_decimals: 2 });
  document.body.append(script);
}

async function open(locale: 'en' | 'es' = 'en') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/p/:slug/book', component: { template: '<div />' }, meta: { auth: false, chrome: false } }],
  });
  const m = await mountInShell(
    PublicBookingPage,
    { locale, session: VISITOR },
    {
      path: '/p/salon-lucia/book',
      session: VISITOR,
      router,
      messages: { en: { ...appointmentEn, ...en }, es: { ...appointmentEs, ...es } },
    },
  );
  await settle();
  await settle();
  const el = (testid: string) => m.inDoc(`ob-preview-${testid}`) as HTMLElement | null;
  return { ...m, el, text: () => m.find('ob-preview').text() };
}

beforeEach(() => {
  document.cookie = 'hub_csrftoken=tok';
  moneyBlock('EUR');
});

afterEach(() => {
  document.getElementById('public-door')?.remove();
  vi.unstubAllGlobals();
});

describe('PublicBookingPage', () => {
  it('opens the business’s page through the public door, never the team’s API nor its live stream', async () => {
    door();
    const s = await open();
    expect(s.el('title')?.textContent).toContain('Salón Lucía');
    expect(s.text()).toContain('Book your next visit');
    expect(posted.map(({ op, method }) => [op, method])).toEqual([
      ['online_booking.public.page', 'POST'],
      ['online_booking.public.services', 'POST'],
    ]);
    expect(posted[1].body).toEqual({ limit: 100 });
    expect(s.sent()).toEqual([]);
    expect(s.client.stream.subscriptions('base.business.get')).toEqual([]);
  });

  it('identifies the business with its name, logo and page colour', async () => {
    door();
    const s = await open();
    expect(s.el('business-name')?.textContent).toContain('Salón Lucía');
    expect(s.el('business-logo')?.getAttribute('src')).toBe('/media/salon-lucia.png');
    expect(s.el('business-logo')?.getAttribute('alt')).toBe('Salón Lucía logo');
    expect(s.el('page')?.getAttribute('style')).toContain('--ob-accent: #6366f1');
  });

  it('shows the business name without an img when the configured logo is external', async () => {
    door({ ...ANSWERS, 'online_booking.public.page': [200, { ...PAGE, logo_url: 'https://example.com/salon-lucia.png' }] });
    const s = await open();
    expect(s.el('business-logo')).toBeNull();
    expect(s.el('business-name')?.textContent).toBe('Salón Lucía');
    expect(s.el('title')?.textContent).toBe('Salón Lucía');
  });

  it('writes the prices in the money the page’s HTML carries: złoty in a business in Poland', async () => {
    document.getElementById('public-door')?.remove();
    moneyBlock('PLN');
    door();
    const s = await open('es');
    expect(s.el('service-v1')?.textContent).toContain('20,00 zł · 30 min');
    expect(s.text()).not.toContain('€');
  });

  it('speaks to the customer, not to the team: its own heading and words, nothing of a preview', async () => {
    door();
    const s = await open('es');
    expect(s.text()).toContain('Reserva online');
    expect(s.text()).toContain('Elige tus servicios, un día y una hora libre, y deja tu nombre y tu móvil.');
    expect(s.text()).not.toMatch(/vista previa|desarrollo/i);
  });

  it('puts the privacy notice and its link beside Book, and keeps the trap out of reach', async () => {
    door();
    const s = await open();
    expect(s.el('privacy')?.textContent).toContain('Your details will be used by Salón Lucía to manage this booking');
    const link = s.el('privacy')?.querySelector('a');
    expect(link?.getAttribute('href')).toBe('https://erplora.com/legal/privacy/');
    expect(link?.getAttribute('target')).toBe('_blank');
    expect(link?.getAttribute('rel')).toContain('noopener');
    expect(s.el('trap')?.getAttribute('aria-hidden')).toBe('true');
    const trap = s.el('trap-input') as HTMLInputElement;
    expect(trap.tabIndex).toBe(-1);
    expect(trap.getAttribute('autocomplete')).toBe('off');
    expect(trap.value).toBe('');
    expect(s.el('trap')?.hidden).toBe(true);
    expect(s.el('trap')?.classList.contains('ob-public-submit__trap')).toBe(true);
  });

  it('says it is loading while the business has not answered', async () => {
    door({ 'online_booking.public.page': 'hang' });
    const s = await open();
    expect(s.text()).toContain('Loading the page…');
  });

  it('says when the business has nothing to book online, without sending the customer to its settings', async () => {
    door({ ...ANSWERS, 'online_booking.public.services': [200, page([], 0, 100)] });
    const s = await open();
    expect(s.el('no-services')?.textContent).toContain('This business has nothing to book online right now.');
    expect(s.el('no-services')?.classList.contains('empty-state')).toBe(true);
    expect(s.el('intro')).toBeNull();
    expect(s.text()).not.toContain('Settings');
    for (const field of ['staff', 'day', 'name', 'phone', 'email', 'book']) expect(s.el(field)).toBeNull();
  });

  it('says why the page does not open: a business that does not take online bookings', async () => {
    const message = 'This business does not take online bookings right now.';
    door({ 'online_booking.public.page': [404, { error: { code: 'online_booking.page_disabled', message } }] });
    const s = await open();
    expect(s.el('error')?.textContent).toContain(message);
  });

  async function fillBooking(s: Awaited<ReturnType<typeof open>>): Promise<void> {
    await ionChecked(s.el('service-v1'), true);
    await ionValue(s.el('day'), '2030-03-05', 'ionChange');
    await settle();
    await click(s.el('time-10:00'));
    await ionValue(s.el('name'), 'Marta Gil', 'ionInput');
    await ionValue(s.el('phone'), '612 345 678', 'ionInput');
  }

  async function booked(s: Awaited<ReturnType<typeof open>>): Promise<void> {
    await fillBooking(s);
    const clock = vi.spyOn(Date, 'now');
    clock.mockReturnValue(Date.now() + 4000);
    try {
      await click(s.el('book'));
    } finally {
      clock.mockRestore();
    }
    await settle();
  }

  it('books through the door and shows the booking’s number and the business’s message', async () => {
    door();
    const s = await open();
    await booked(s);
    expect(s.el('booked')?.textContent).toContain('We have received your booking.');
    const book = posted.find(({ op }) => op === 'online_booking.public.book');
    expect(book?.body).toMatchObject({ service_ids: ['v1'], start: '2030-03-05T10:00', name: 'Marta Gil', phone: '612 345 678', website: '' });
  });

  it('waits three seconds from opening the page before sending a booking', async () => {
    door();
    const s = await open();
    await fillBooking(s);
    vi.useFakeTimers();
    try {
      s.el('book')!.dispatchEvent(new MouseEvent('click', { bubbles: true, composed: true }));
      await Promise.resolve();
      await Promise.resolve();
      expect(posted.filter(({ op }) => op === 'online_booking.public.book')).toHaveLength(0);
      await vi.advanceTimersByTimeAsync(3000);
      vi.useRealTimers();
      await settle();
      expect(posted.filter(({ op }) => op === 'online_booking.public.book')).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('right after booking she sees it and cancels it through the door, its link in the body', async () => {
    door();
    const s = await open();
    await booked(s);
    await click(s.el('view'));
    await settle();
    expect(s.el('status')?.textContent).toContain('Pending');
    await click(s.el('cancel'));
    await settle();
    expect(s.el('status')?.textContent).toContain('Cancelled');
    const byLink = posted.filter(({ op }) => op === 'online_booking.public.booking' || op === 'online_booking.public.cancel');
    expect(byLink.map(({ op, body }) => [op, body])).toEqual([
      ['online_booking.public.booking', { token: BOOKED.token }],
      ['online_booking.public.cancel', { token: BOOKED.token }],
    ]);
  });
});

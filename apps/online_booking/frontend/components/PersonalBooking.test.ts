import type { SessionMe } from '@erplora/ui/shell';
import { ApiError, type ApiClient } from '@erplora/ui/sdk';
import { computed } from 'vue';
import { describe, expect, it, vi } from 'vitest';

import appointmentEn from '../../../appointment/frontend/locale/en.json';
import appointmentEs from '../../../appointment/frontend/locale/es.json';
import { click, ionValue, mountInShell, settle } from '../__tests__/mount-online-booking';
import en from '../locale/en.json';
import es from '../locale/es.json';
import { PUBLIC_DOOR } from '../lib/door';
import type { PublicBookingOut } from '../operations';
import PersonalBooking from './PersonalBooking.vue';

vi.mock('@ionic/vue', async (importOriginal) => (await import('../../../../base/frontend/__tests__/modal')).mockIonicModal(importOriginal));

const TOKEN = 't'.repeat(43);
const VISITOR: SessionMe = { user: null, permissions: [], menu: [], apps: [], language: 'en' };
const SEEN: PublicBookingOut = {
  business_name: 'Salón Lucía',
  logo_url: '',
  number: 'APT-20300304-0001',
  status: 'confirmed',
  start: '2030-03-05T10:00:00+01:00',
  end: '2030-03-05T10:30:00+01:00',
  timezone: 'Europe/Madrid',
  service_names: 'Haircut',
  staff_name: 'Ana López',
  can_cancel: true,
  cancel_until: '2030-03-04T10:00:00+01:00',
  cancellation_policy: 'Please give us 24 hours notice.',
};

async function setup(answer: PublicBookingOut | ApiError | 'hang' = SEEN, locale: 'en' | 'es' = 'en') {
  const call = vi.fn(async (op: string) => {
    if (op === 'online_booking.public.booking') {
      if (answer === 'hang') return new Promise<never>(() => {});
      if (answer instanceof ApiError) throw answer;
      return answer;
    }
    if (op === 'online_booking.public.cancel') return { ...SEEN, status: 'cancelled', can_cancel: false, cancel_until: null };
    throw new Error(`Unexpected operation: ${op}`);
  });
  const door = { api: { call } as unknown as ApiClient, money: computed(() => undefined), slug: 'salon-lucia' };
  const mounted = await mountInShell(
    PersonalBooking,
    { props: { token: TOKEN }, locale, session: VISITOR },
    {
      path: `/p/salon-lucia/book/${TOKEN}`,
      session: VISITOR,
      provide: { [PUBLIC_DOOR]: door },
      messages: { en: { ...appointmentEn, ...en }, es: { ...appointmentEs, ...es } },
    },
  );
  await settle();
  return { ...mounted, call };
}

function expectCancelled(s: Awaited<ReturnType<typeof setup>>): void {
  expect(s.inDoc('ob-preview-business-name')?.textContent).toBe('Salón Lucía');
  expect(s.inDoc('ob-preview-status')?.textContent).toContain('Cancelled');
  expect(s.inDoc('ob-preview-status')?.textContent).not.toContain('It can no longer be cancelled online.');
  expect(s.inDoc('ob-personal-cancelled')?.textContent).toContain('This booking is cancelled.');
  expect(s.inDoc('ob-preview-cancel')).toBeNull();
}

describe('PersonalBooking', () => {
  it('shows the business name without a logo when the booking response has none', async () => {
    const s = await setup();
    expect(s.inDoc('ob-preview-business-name')?.textContent).toBe('Salón Lucía');
    expect(s.inDoc('ob-preview-business-logo')).toBeNull();
    expect(s.call).not.toHaveBeenCalledWith('online_booking.public.page', expect.anything());
  });

  it('shows the business logo with its accessible alternative text', async () => {
    const logoUrl = '/p/media/online_booking/logo/salon.png';
    const s = await setup({ ...SEEN, logo_url: logoUrl });
    const logo = s.inDoc('ob-preview-business-logo');
    expect(s.inDoc('ob-preview-business-name')?.textContent).toBe('Salón Lucía');
    expect(logo?.getAttribute('src')).toBe(logoUrl);
    expect(logo?.getAttribute('alt')).toBe('Salón Lucía logo');
  });

  it.each([
    ['en', 'the business logo'],
    ['es', 'Logo de este negocio'],
  ] as const)('names the logo in %s when a demo has no business name', async (locale, alt) => {
    const s = await setup({ ...SEEN, business_name: '', logo_url: '/p/media/online_booking/logo/salon.png' }, locale);
    expect(s.inDoc('ob-preview-business-logo')?.getAttribute('alt')).toBe(alt);
  });

  it('leaves out an empty header when a demo has neither a business name nor a logo', async () => {
    const s = await setup({ ...SEEN, business_name: '' });
    expect(s.inDoc('ob-preview-status')).not.toBeNull();
    expect(s.wrapper.find('.ob-business').exists()).toBe(false);
  });

  it('loads only the booking behind the link and shows its service, time, professional and status', async () => {
    const s = await setup();
    expect(s.call).toHaveBeenCalledExactlyOnceWith('online_booking.public.booking', { token: TOKEN });
    expect(s.inDoc('ob-preview-status')?.textContent).toContain('APT-20300304-0001');
    expect(s.inDoc('ob-preview-status')?.textContent).toContain('Haircut');
    expect(s.inDoc('ob-preview-status')?.textContent).toContain('Ana López');
    expect(s.inDoc('ob-preview-status')?.textContent).toContain('Tuesday, March 5, 2030');
    expect(s.inDoc('ob-preview-status')?.textContent).toContain('10:00 AM');
    expect(s.inDoc('ob-preview-status')?.textContent).toContain('Confirmed');
    expect(s.inDoc('ob-preview-cancel')).not.toBeNull();
    expect(s.inDoc('ob-preview')).toBeNull();
  });

  it('places the booking and its status before the cancel action', async () => {
    const s = await setup();
    const status = s.inDoc('ob-preview-status');
    const cancel = s.inDoc('ob-preview-cancel');
    expect(status).not.toBeNull();
    expect(cancel).not.toBeNull();
    expect(status!.compareDocumentPosition(cancel!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('asks for confirmation and only then cancels through the link, with its optional reason', async () => {
    const s = await setup();
    await click(s.inDoc('ob-preview-cancel'));
    expect(s.call).not.toHaveBeenCalledWith('online_booking.public.cancel', expect.anything());
    expect(s.inDoc('ob-cancel')?.textContent).toContain('APT-20300304-0001');
    await ionValue(s.inDoc('ob-cancel-reason'), 'I cannot make it', 'ionInput');
    await click(s.inDoc('ob-cancel-submit'));
    await settle();
    expect(s.call).toHaveBeenLastCalledWith('online_booking.public.cancel', { token: TOKEN, reason: 'I cannot make it' });
    expectCancelled(s);
  });

  it('shows an already cancelled booking without offering to cancel it again', async () => {
    const s = await setup({ ...SEEN, status: 'cancelled', can_cancel: false, cancel_until: null });
    expectCancelled(s);
  });

  it('uses the app’s cancelled word in Spanish and shows only that message', async () => {
    const s = await setup({ ...SEEN, status: 'cancelled', can_cancel: false, cancel_until: null }, 'es');
    expect(s.inDoc('ob-preview-status')?.textContent).toContain('Cancelada');
    expect(s.inDoc('ob-preview-status')?.textContent).not.toContain('Ya no se puede cancelar online.');
    expect(s.inDoc('ob-personal-cancelled')?.textContent).toContain('Esta reserva está cancelada.');
    expect(s.wrapper.text()).not.toContain('anulada');
  });

  it('shows a booking whose cancellation window has passed without the cancel action', async () => {
    const s = await setup({ ...SEEN, can_cancel: false, cancel_until: null });
    expect(s.inDoc('ob-preview-status')?.textContent).toContain('It can no longer be cancelled online.');
    expect(s.inDoc('ob-preview-cancel')).toBeNull();
  });

  it('says while the booking is loading', async () => {
    const s = await setup('hang');
    expect(s.inDoc('ob-personal-loading')?.textContent).toContain('Loading your booking…');
    expect(s.inDoc('ob-preview-status')).toBeNull();
  });

  it('shows a loading failure and retries it without losing the link', async () => {
    const s = await setup(new ApiError(500, 'internal_error', 'The booking could not be loaded.'));
    expect(s.inDoc('ob-personal-error')?.textContent).toContain('The booking could not be loaded.');
    s.call.mockResolvedValueOnce(SEEN);
    await click(s.inDoc('ob-personal-error')?.querySelector('ion-button') ?? null);
    await settle();
    expect(s.call).toHaveBeenLastCalledWith('online_booking.public.booking', { token: TOKEN });
    expect(s.inDoc('ob-preview-status')?.textContent).toContain('Haircut');
  });

  it('shows a clear not-found notice without booking data or the general booking form', async () => {
    const s = await setup(new ApiError(404, 'online_booking.booking_not_found', 'This booking does not exist or its link is no longer valid.'));
    expect(s.inDoc('ob-personal-error')?.textContent).toContain('This booking does not exist or its link is no longer valid.');
    expect(s.wrapper.text()).not.toContain('Haircut');
    expect(s.wrapper.text()).not.toContain('APT-20300304-0001');
    expect(s.inDoc('ob-preview-status')).toBeNull();
    expect(s.inDoc('ob-preview-cancel')).toBeNull();
    expect(s.inDoc('ob-preview-business-name')).toBeNull();
    expect(s.inDoc('ob-preview-business-logo')).toBeNull();
    expect(s.inDoc('ob-preview')).toBeNull();
  });

  it('keeps a cancellation refusal in the dialog and speaks Spanish', async () => {
    const s = await setup(SEEN, 'es');
    s.call.mockRejectedValueOnce(new ApiError(409, 'appointment.cannot_cancel', 'Esta cita ya no se puede cancelar.'));
    await click(s.inDoc('ob-preview-cancel'));
    expect(s.inDoc('ob-cancel')?.textContent).toContain('¿Cancelar la reserva APT-20300304-0001');
    await click(s.inDoc('ob-cancel-submit'));
    await settle();
    expect(s.inDoc('ob-cancel-error')?.textContent).toContain('Esta cita ya no se puede cancelar.');
    expect(s.inDoc('ob-preview-status')?.textContent).toContain('Confirmada');
  });
});

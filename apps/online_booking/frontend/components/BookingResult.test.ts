import { ApiError } from '@erplora/ui/sdk';
import { describe, expect, it } from 'vitest';

import type { BookedOut, PublicBookingOut } from '../operations';
import { click, ionValue, mountOnlineBooking, settle } from '../__tests__/mount-online-booking';
import BookingResult from './BookingResult.vue';
import CancelDialog from './CancelDialog.vue';

const BOOKED = {
  number: 'APT-1',
  status: 'confirmed',
  start: '2030-03-05T10:00:00+01:00',
  end: '2030-03-05T10:30:00+01:00',
  timezone: 'Europe/Madrid',
  service_names: 'Haircut',
  staff_name: 'Ana',
  message: 'Your booking is confirmed.',
  token: 't'.repeat(43),
} as BookedOut;
const CANCELLED = { ...BOOKED, status: 'cancelled', can_cancel: false, cancel_until: null } as unknown as PublicBookingOut;

async function setup(locale: 'en' | 'es' = 'en') {
  return mountOnlineBooking(BookingResult, {
    props: { booked: BOOKED, seen: null, pending: false, error: '', token: BOOKED.token },
    locale,
  });
}

describe('BookingResult', () => {
  it('shows the confirmation and emits seeing the booking and booking another', async () => {
    const s = await setup();
    expect(s.inDoc('ob-preview-booked')?.textContent).toContain('Your booking is confirmed.');
    await click(s.inDoc('ob-preview-view'));
    await click(s.inDoc('ob-preview-again'));
    expect(s.wrapper.emitted('view')).toEqual([[]]);
    expect(s.wrapper.emitted('again')).toEqual([[]]);
  });

  it('a tap on Cancel only asks, naming the booking and when; confirming asks to cancel it with the reason', async () => {
    const s = await setup();
    await click(s.inDoc('ob-preview-cancel'));
    await settle();
    expect(s.wrapper.emitted('cancel')).toBeUndefined();
    expect(s.inDoc('ob-cancel')?.textContent).toContain('Cancel booking APT-1 (Tuesday, March 5, 2030 · 10:00 AM)?');
    await ionValue(s.inDoc('ob-cancel-reason'), 'Running late', 'ionInput');
    await click(s.inDoc('ob-cancel-submit'));
    expect(s.wrapper.emitted('cancel')).toEqual([['Running late']]);
  });

  it('keeping the booking closes the confirmation without cancelling it', async () => {
    const s = await setup();
    await click(s.inDoc('ob-preview-cancel'));
    await click(s.inDoc('ob-cancel-cancel'));
    await settle();
    expect(s.wrapper.findComponent(CancelDialog).props('open')).toBe(false);
    expect(s.wrapper.emitted('cancel')).toBeUndefined();
  });

  it('closes the confirmation once the booking shows as cancelled', async () => {
    const s = await setup();
    await click(s.inDoc('ob-preview-cancel'));
    await click(s.inDoc('ob-cancel-submit'));
    await s.wrapper.setProps({ seen: CANCELLED });
    await settle();
    expect(s.wrapper.findComponent(CancelDialog).props('open')).toBe(false);
    expect(s.inDoc('ob-personal-cancelled')?.textContent).toContain('This booking is cancelled.');
  });

  it('keeps a refusal and the wait inside the confirmation, in Spanish', async () => {
    const s = await setup('es');
    await click(s.inDoc('ob-preview-cancel'));
    await s.wrapper.setProps({ pending: true });
    expect(s.inDoc('ob-cancel')?.querySelector('form')?.getAttribute('aria-busy')).toBe('true');
    const refusal = new ApiError(409, 'appointment.cannot_cancel', 'Esta cita ya no se puede cancelar.');
    await s.wrapper.setProps({ pending: false, cancelError: refusal });
    await settle();
    expect(s.inDoc('ob-cancel')?.textContent).toContain('¿Cancelar la reserva APT-1');
    expect(s.inDoc('ob-cancel-error')?.textContent).toContain('Esta cita ya no se puede cancelar.');
    expect(s.wrapper.findComponent(CancelDialog).props('open')).toBe(true);
  });

  it('asking again starts without the last refusal', async () => {
    const s = await setup();
    await click(s.inDoc('ob-preview-cancel'));
    await s.wrapper.setProps({ cancelError: new ApiError(500, 'internal_error', 'The booking could not be cancelled.') });
    await settle();
    expect(s.inDoc('ob-cancel-error')?.textContent).toContain('The booking could not be cancelled.');
    await click(s.inDoc('ob-cancel-cancel'));
    await click(s.inDoc('ob-preview-cancel'));
    await settle();
    expect(s.inDoc('ob-cancel-error')).toBeNull();
  });
});

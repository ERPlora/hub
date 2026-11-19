import { describe, expect, it } from 'vitest';

import type { BookedOut } from '../operations';
import { click, mountOnlineBooking } from '../__tests__/mount-online-booking';
import BookingResult from './BookingResult.vue';

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

describe('BookingResult', () => {
  it('shows the confirmation and emits its actions', async () => {
    const s = await mountOnlineBooking(BookingResult, {
      props: { booked: BOOKED, seen: null, pending: false, error: '' },
    });
    expect(s.inDoc('ob-preview-booked')?.textContent).toContain('Your booking is confirmed.');
    await click(s.inDoc('ob-preview-view'));
    await click(s.inDoc('ob-preview-cancel'));
    await click(s.inDoc('ob-preview-again'));
    expect(s.wrapper.emitted('action')).toEqual([
      ['online_booking.public.booking'],
      ['online_booking.public.cancel'],
    ]);
    expect(s.wrapper.emitted('again')).toEqual([[]]);
  });
});

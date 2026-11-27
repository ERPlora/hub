// What the booking panel has chosen, at the foot beside its buttons: «12:00 PM – 12:30 PM · 30 min» and, under it, the
// day and the professional; nothing while the time is missing.
import { describe, expect, it } from 'vitest';

import { mountAppointment } from '../__tests__/mount-appointment';
import BookingSummary from './BookingSummary.vue';

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountAppointment(BookingSummary, {
    props: { day: '2026-11-25', time: '12:00', minutes: 30, staffName: 'Pablo Serrano', ...props },
    locale,
  });
  const lines = () => m.wrapper.findAll('[data-testid^=appointment-form-chosen]').map((line) => line.text());
  return { ...m, lines };
}

describe('BookingSummary', () => {
  it('says the time it takes, its length, the day and the professional', async () => {
    expect((await setup()).lines()).toEqual(['12:00 PM – 12:30 PM · 30 min', 'Wed, Nov 25 · Pablo Serrano']);
  });

  it('speaks Spanish', async () => {
    expect((await setup({ time: '09:45', minutes: 90 }, 'es')).lines()).toEqual(['9:45 – 11:15 · 90 min', 'mié, 25 nov · Pablo Serrano']);
  });

  it('without a length, only the time; without a professional, what is missing', async () => {
    expect((await setup({ minutes: null, staffName: '' })).lines()).toEqual(['12:00 PM', 'Wed, Nov 25 · Pick a professional']);
  });

  it('says nothing while the time is missing', async () => {
    expect((await setup({ time: '' })).lines()).toEqual([]);
  });
});

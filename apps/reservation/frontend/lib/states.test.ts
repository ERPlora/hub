// What a reservation row offers by its status (the server's steps, services.py STEPS), the colour of its
// status, the next slot of the day the bar shows, and the opening hours as one line.
import { describe, expect, it } from 'vitest';

import type { DayOut, SlotLoadOut } from '../operations';
import { allows, nextSlot, spansLine, statusTone } from './states';

const slot = (start: string, end: string, available: number, extra: Partial<SlotLoadOut> = {}): SlotLoadOut => ({
  id: start,
  start_time: `${start}:00`,
  end_time: `${end}:00`,
  max_reservations: 10,
  max_covers: null,
  reserved: 10 - available,
  covers: 0,
  available,
  full: available === 0,
  in_hours: true,
  ...extra,
});

const day = (extra: Partial<DayOut> = {}): DayOut => ({
  date: '2026-10-15',
  today: '2026-10-15',
  timezone: 'Europe/Madrid',
  closed: false,
  blocks: [],
  hours_restricted: false,
  spans: [],
  slots: [slot('13:00', '16:00', 4), slot('20:00', '23:30', 0)],
  reservations: 0,
  covers: 0,
  ...extra,
});

describe('reservation states', () => {
  it('offers each step only from the statuses the server accepts', () => {
    expect(['pending', 'confirmed', 'seated', 'completed', 'cancelled', 'no_show'].filter((s) => allows('confirm', s))).toEqual(['pending']);
    expect(['pending', 'confirmed', 'seated', 'completed'].filter((s) => allows('seat', s))).toEqual(['pending', 'confirmed']);
    expect(['pending', 'confirmed', 'seated'].filter((s) => allows('complete', s))).toEqual(['seated']);
    expect(['pending', 'confirmed', 'seated'].filter((s) => allows('cancel', s))).toEqual(['pending', 'confirmed']);
    expect(['pending', 'confirmed', 'seated'].filter((s) => allows('no_show', s))).toEqual(['pending', 'confirmed']);
    expect(allows('edit', 'completed')).toBe(true);
    expect(allows('delete', 'cancelled')).toBe(true);
  });

  it('paints each status in its colour', () => {
    expect(['pending', 'confirmed', 'seated', 'completed', 'cancelled', 'no_show'].map(statusTone)).toEqual([
      'warning',
      'info',
      'success',
      'neutral',
      'danger',
      'danger',
    ]);
  });
});

describe('the next slot of the day', () => {
  it('on today is the first one that has not ended; on another day, its first one', () => {
    expect(nextSlot(day(), true, '14:00')).toMatchObject({ state: 'open', slot: { start_time: '13:00:00' } });
    expect(nextSlot(day(), true, '17:00')).toMatchObject({ state: 'full', slot: { start_time: '20:00:00' } });
    expect(nextSlot(day(), true, '23:45')).toEqual({ state: 'over' });
    expect(nextSlot(day({ today: '2026-10-14' }), false, '23:45')).toMatchObject({ state: 'open' });
  });

  it('says when the day is closed or has no service', () => {
    expect(nextSlot(day({ closed: true }), true, '10:00')).toEqual({ state: 'closed' });
    expect(nextSlot(day({ hours_restricted: true, spans: [] }), true, '10:00')).toEqual({ state: 'closed' });
    expect(nextSlot(day({ slots: [] }), true, '10:00')).toEqual({ state: 'no-service' });
  });
});

describe('the opening hours as one line', () => {
  it('joins the spans of the day by start, past midnight included', () => {
    const spans = [
      { start: '2026-10-15T20:00:00', end: '2026-10-16T02:00:00' },
      { start: '2026-10-15T13:00:00', end: '2026-10-15T16:00:00' },
    ];
    expect(spansLine(spans, (time) => time)).toBe('13:00–16:00 · 20:00–02:00');
  });
});

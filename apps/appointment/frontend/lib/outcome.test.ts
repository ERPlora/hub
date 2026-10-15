// What booking a series' dates tells the person (APPOINTMENT-F12, F13): «{booked} appointments booked ·
// {skipped} could not be booked», each skipped date with its reason, the dates still to book from
// `next_from`, or the series' next date beyond the window when there is nothing to book yet.
import { describe, expect, it } from 'vitest';

import type { MaterializeOut } from '../operations';
import { describeOutcome } from './outcome';

const t = (key: string, named: Record<string, unknown> = {}) => `${key}${JSON.stringify(named)}`;
const outcome = (over: Partial<MaterializeOut>): MaterializeOut => ({
  recurring: {} as MaterializeOut['recurring'],
  booked: 3,
  already_booked: 0,
  skipped: [],
  next_from: null,
  to: '2026-12-31',
  upcoming_date: null,
  ...over,
});

describe('describeOutcome', () => {
  it('counts what was booked and lists what was skipped with its reason', () => {
    const said = describeOutcome(
      outcome({ skipped: [{ occurrence_date: '2026-10-26', code: 'outside_schedule', message: 'Closed.' }] }),
      t,
      'en',
    );
    expect(said.summary).toBe('appointment.series.outcome.booked{"booked":3,"skipped":1}');
    expect(said.skipped).toEqual(['Monday, October 26, 2026: Closed.']);
    expect(said.more).toBe('');
  });

  it('says what is left to book, or when the next date comes', () => {
    expect(describeOutcome(outcome({ next_from: '2027-01-04' }), t, 'en').more).toBe(
      'appointment.series.outcome.pendingFrom{"date":"Monday, January 4, 2027"}',
    );
    expect(describeOutcome(outcome({ booked: 0, upcoming_date: '2027-03-01' }), t, 'en').more).toBe(
      'appointment.series.outcome.upcoming{"date":"Monday, March 1, 2027"}',
    );
  });
});

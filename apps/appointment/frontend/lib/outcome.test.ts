// What booking a series' dates tells the person (APPOINTMENT-F12, F13): only what happened — how many were
// booked and how many could not be (never «· 0 could not be booked»), or that there was nothing new because
// the window was already booked (never «0 appointments booked · 0 could not be booked») —, each skipped date
// with its reason, the dates still to book from `next_from`, or the series' next date beyond the window when
// there is nothing to book yet.
import { describe, expect, it } from 'vitest';

import type { MaterializeOut, RecurringUpdatedOut } from '../operations';
import { describeOutcome, describeUpdate } from './outcome';

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
    expect(said.summary).toBe('appointment.series.outcome.booked{"booked":3} · appointment.series.outcome.notBooked{"skipped":1}');
    expect(said.skipped).toEqual(['Monday, October 26, 2026: Closed.']);
    expect(said.more).toBe('');
  });

  it('says only what happened: no «0 could not be booked», and nothing new when the window was booked', () => {
    expect(describeOutcome(outcome({}), t, 'en').summary).toBe('appointment.series.outcome.booked{"booked":3}');
    expect(
      describeOutcome(
        outcome({ booked: 0, skipped: [{ occurrence_date: '2026-10-26', code: 'outside_schedule', message: 'Closed.' }] }),
        t,
        'en',
      ).summary,
    ).toBe('appointment.series.outcome.notBooked{"skipped":1}');
    expect(describeOutcome(outcome({ booked: 0, already_booked: 3 }), t, 'en').summary).toBe(
      'appointment.series.outcome.alreadyBooked{"already":3}',
    );
    expect(describeOutcome(outcome({ booked: 0, upcoming_date: '2027-03-01' }), t, 'en').summary).toBe(
      'appointment.series.outcome.none{}',
    );
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

// What editing a series «from this occurrence on» tells the person (APPOINTMENT-F14): only what happened
// (appointments#293: never «0 cancelled · 0 left alone»), to whom the appointments now go (#256) and for which
// services (#294), and each appointment that kept its time with its date in the reader's language.
describe('describeUpdate', () => {
  const series = { staff_name: 'Bea Ruiz', service_names: 'Haircut, Colour' } as RecurringUpdatedOut['recurring'];
  const updated = (over: Partial<RecurringUpdatedOut>): RecurringUpdatedOut => ({
    recurring: series,
    moved: 0,
    cancelled: 0,
    locked: 0,
    skipped: [],
    booked: 0,
    ...over,
  });

  it('says only what happened', () => {
    expect(describeUpdate(updated({ moved: 3 }), {}, t, 'en').summary).toBe('appointment.series.outcome.moved{"moved":3}');
    expect(describeUpdate(updated({ moved: 2, cancelled: 1, locked: 1, booked: 4 }), {}, t, 'en').summary).toBe(
      [
        'appointment.series.outcome.moved{"moved":2}',
        'appointment.series.outcome.newDates{"booked":4}',
        'appointment.series.outcome.cancelled{"cancelled":1}',
        'appointment.series.outcome.locked{"locked":1}',
      ].join(' · '),
    );
    expect(describeUpdate(updated({}), {}, t, 'en').summary).toBe('appointment.series.outcome.unchanged{}');
  });

  it('names who the appointments go to and for which services', () => {
    expect(describeUpdate(updated({ moved: 3 }), { staff_id: 'm2' }, t, 'en').summary).toBe(
      'appointment.series.outcome.handed{"moved":3,"staff":"Bea Ruiz"}',
    );
    expect(describeUpdate(updated({ moved: 3 }), { services: [{ service_id: 's2' }] }, t, 'en').summary).toBe(
      'appointment.series.outcome.servicesChanged{"moved":3,"services":"Haircut, Colour"}',
    );
    expect(
      describeUpdate(updated({ moved: 1 }), { staff_id: 'm2', services: [{ service_id: 's2' }] }, t, 'en').summary,
    ).toBe('appointment.series.outcome.handedWithServices{"moved":1,"staff":"Bea Ruiz","services":"Haircut, Colour"}');
  });

  it('lists what kept its time, with its date in the reader’s language', () => {
    const said = describeUpdate(
      updated({ moved: 1, skipped: [{ occurrence_date: '2026-09-26', code: 'blocked', message: 'Blocked.' }] }),
      {},
      t,
      'es',
    );
    expect(said.summary).toBe(
      'appointment.series.outcome.moved{"moved":1} · appointment.series.outcome.notMoved{"skipped":1}',
    );
    expect(said.skipped).toEqual(['sábado, 26 de septiembre de 2026: Blocked.']);
  });
});

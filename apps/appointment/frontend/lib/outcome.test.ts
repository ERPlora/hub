// What booking a series' dates tells the person (APPOINTMENT-F12, F13): only what happened — how many were
// booked and how many could not be (never «· 0 could not be booked»), or that there was nothing new because
// the window was already booked (never «0 appointments booked · 0 could not be booked») —, each skipped date
// with its reason, the dates still to book from `next_from`, or the series' next date beyond the window when
// there is nothing to book yet. Each count goes to the catalogue as `count`, so vue-i18n picks its singular or plural.
import { createShellI18n } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import en from '../locale/en.json';
import es from '../locale/es.json';
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
    expect(said.summary).toBe('appointment.series.outcome.booked{"count":3} · appointment.series.outcome.notBooked{"count":1}');
    expect(said.skipped).toEqual(['Monday, October 26, 2026: Closed.']);
    expect(said.more).toBe('');
  });

  it('says only what happened: no «0 could not be booked», and nothing new when the window was booked', () => {
    expect(describeOutcome(outcome({}), t, 'en').summary).toBe('appointment.series.outcome.booked{"count":3}');
    expect(
      describeOutcome(
        outcome({ booked: 0, skipped: [{ occurrence_date: '2026-10-26', code: 'outside_schedule', message: 'Closed.' }] }),
        t,
        'en',
      ).summary,
    ).toBe('appointment.series.outcome.notBooked{"count":1}');
    expect(describeOutcome(outcome({ booked: 0, already_booked: 3 }), t, 'en').summary).toBe(
      'appointment.series.outcome.alreadyBooked{"count":3}',
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
// (never «0 cancelled · 0 left alone»), to whom the appointments now go and for which
// services, and each appointment that kept its time with its date in the reader's language.
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
    expect(describeUpdate(updated({ moved: 3 }), {}, t, 'en').summary).toBe('appointment.series.outcome.moved{"count":3}');
    expect(describeUpdate(updated({ moved: 2, cancelled: 1, locked: 1, booked: 4 }), {}, t, 'en').summary).toBe(
      [
        'appointment.series.outcome.moved{"count":2}',
        'appointment.series.outcome.newDates{"count":4}',
        'appointment.series.outcome.cancelled{"count":1}',
        'appointment.series.outcome.locked{"count":1}',
      ].join(' · '),
    );
    expect(describeUpdate(updated({}), {}, t, 'en').summary).toBe('appointment.series.outcome.unchanged{}');
  });

  it('names who the appointments go to and for which services', () => {
    expect(describeUpdate(updated({ moved: 3 }), { staff_id: 'm2' }, t, 'en').summary).toBe(
      'appointment.series.outcome.handed{"count":3,"staff":"Bea Ruiz"}',
    );
    expect(describeUpdate(updated({ moved: 3 }), { services: [{ service_id: 's2' }] }, t, 'en').summary).toBe(
      'appointment.series.outcome.servicesChanged{"count":3,"services":"Haircut, Colour"}',
    );
    expect(
      describeUpdate(updated({ moved: 1 }), { staff_id: 'm2', services: [{ service_id: 's2' }] }, t, 'en').summary,
    ).toBe('appointment.series.outcome.handedWithServices{"count":1,"staff":"Bea Ruiz","services":"Haircut, Colour"}');
  });

  it('lists what kept its time, with its date in the reader’s language', () => {
    const said = describeUpdate(
      updated({ moved: 1, skipped: [{ occurrence_date: '2026-09-26', code: 'blocked', message: 'Blocked.' }] }),
      {},
      t,
      'es',
    );
    expect(said.summary).toBe(
      'appointment.series.outcome.moved{"count":1} · appointment.series.outcome.notMoved{"count":1}',
    );
    expect(said.skipped).toEqual(['sábado, 26 de septiembre de 2026: Blocked.']);
  });
});

// hub#2063: «1 cita reservada», never «1 citas reservadas»; the plural only from two (and for none).
describe('with the app catalogues, one appointment reads in the singular', () => {
  const translator = (locale: 'en' | 'es') => {
    const { t: translate } = createShellI18n({ locale, messages: { en, es } }).global;
    return (key: string, named?: Record<string, unknown>) => (named ? translate(key, named) : translate(key));
  };
  const closed = (day: string) => ({ occurrence_date: day, code: 'outside_schedule', message: 'Closed.' });
  const series = { staff_name: 'Bea Ruiz', service_names: 'Colour' } as RecurringUpdatedOut['recurring'];
  const edited = (count: number): RecurringUpdatedOut => ({
    recurring: series,
    moved: count,
    cancelled: count,
    locked: count,
    skipped: Array.from({ length: count }, (_, day) => closed(`2026-10-2${day}`)),
    booked: count,
  });

  it('booking a series', () => {
    const es1 = describeOutcome(outcome({ booked: 1, skipped: [closed('2027-02-07')] }), translator('es'), 'es');
    expect(es1.summary).toBe('1 cita reservada · 1 no se ha podido reservar');
    const en1 = describeOutcome(outcome({ booked: 1, skipped: [closed('2027-02-07')] }), translator('en'), 'en');
    expect(en1.summary).toBe('1 appointment booked · 1 could not be booked');
    expect(describeOutcome(outcome({ booked: 3 }), translator('es'), 'es').summary).toBe('3 citas reservadas');
    expect(describeOutcome(outcome({ booked: 3 }), translator('en'), 'en').summary).toBe('3 appointments booked');
    expect(describeOutcome(outcome({ booked: 0, skipped: [closed('2027-02-07'), closed('2027-03-07')] }), translator('es'), 'es').summary).toBe(
      '2 no se han podido reservar',
    );
  });

  it('a series whose window was already booked', () => {
    expect(describeOutcome(outcome({ booked: 0, already_booked: 1 }), translator('es'), 'es').summary).toBe(
      'Nada nuevo que reservar: su cita ya estaba reservada',
    );
    expect(describeOutcome(outcome({ booked: 0, already_booked: 1 }), translator('en'), 'en').summary).toBe(
      'Nothing new to book: its appointment was already booked',
    );
    expect(describeOutcome(outcome({ booked: 0, already_booked: 8 }), translator('es'), 'es').summary).toBe(
      'Nada nuevo que reservar: sus 8 citas ya estaban reservadas',
    );
  });

  it('editing a series from this occurrence on', () => {
    expect(describeUpdate(edited(1), {}, translator('es'), 'es').summary).toBe(
      '1 cita movida · 1 fecha nueva reservada · 1 cancelada porque ya no cae en la repetición · ' +
        '1 sin tocar porque ya está cobrada · 1 no se ha podido mover y se queda a su hora:',
    );
    expect(describeUpdate(edited(1), {}, translator('en'), 'en').summary).toBe(
      '1 appointment moved · 1 new date booked · 1 cancelled because it no longer fits the pattern · ' +
        '1 left alone because it is already charged · 1 could not be moved and keeps its time:',
    );
    expect(describeUpdate(edited(2), {}, translator('es'), 'es').summary).toBe(
      '2 citas movidas · 2 fechas nuevas reservadas · 2 canceladas porque ya no caen en la repetición · ' +
        '2 sin tocar porque ya están cobradas · 2 no se han podido mover y se quedan a su hora:',
    );
    expect(describeUpdate(edited(2), {}, translator('en'), 'en').summary).toBe(
      '2 appointments moved · 2 new dates booked · 2 cancelled because they no longer fit the pattern · ' +
        '2 left alone because they are already charged · 2 could not be moved and keep their time:',
    );
  });

  it('handing a series to someone else or changing its services', () => {
    const moved = (count: number): RecurringUpdatedOut => ({ ...edited(0), moved: count });
    const [staff, services] = [{ staff_id: 'm2' }, { services: [{ service_id: 's2' }] }];
    type Change = Parameters<typeof describeUpdate>[1];
    const said = (count: number, change: Change, locale: 'en' | 'es') =>
      describeUpdate(moved(count), change, translator(locale), locale).summary;
    const cases: [Change, 'en' | 'es', string, string][] = [
      [staff, 'es', '1 cita pasa a Bea Ruiz', '4 citas pasan a Bea Ruiz'],
      [staff, 'en', '1 appointment now with Bea Ruiz', '4 appointments now with Bea Ruiz'],
      [services, 'es', '1 cita cambia a Colour', '4 citas cambian a Colour'],
      [services, 'en', '1 appointment now for Colour', '4 appointments now for Colour'],
      [{ ...staff, ...services }, 'es', '1 cita pasa a Bea Ruiz con Colour', '4 citas pasan a Bea Ruiz con Colour'],
      [{ ...staff, ...services }, 'en', '1 appointment now with Bea Ruiz for Colour', '4 appointments now with Bea Ruiz for Colour'],
    ];
    for (const [change, locale, one, four] of cases) expect([said(1, change, locale), said(4, change, locale)]).toEqual([one, four]);
  });
});

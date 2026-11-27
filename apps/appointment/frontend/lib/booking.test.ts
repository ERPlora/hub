// What the booking panel sends (APPOINTMENT-F01, F04, F14): a new appointment whole; an edit only what changed, the
// series from its date when «This and all following»; and the server's refusal under the panel's own fields.
import { describe, expect, it } from 'vitest';

import { BOOKED } from '../__tests__/appointment-form';
import { type Chosen, newBooking, noteChanges, refusedFields, seriesChange, slotChanges } from './booking';

const AS_BOOKED: Chosen = {
  day: '2026-10-19',
  time: '10:00',
  minutes: null,
  staffId: 's1',
  serviceIds: ['cut'],
  notes: '',
  internalNotes: '',
};

describe('newBooking', () => {
  it('sends the services in order, the professional and the wall-clock time; the minutes only when typed', () => {
    const chosen = { ...AS_BOOKED, serviceIds: ['cut', 'colour'], time: '9:05', notes: 'Hi' };
    expect(newBooking(chosen, 'c1', false)).toEqual({
      customer_id: 'c1',
      services: [{ service_id: 'cut' }, { service_id: 'colour' }],
      staff_id: 's1',
      start: '2026-10-19T09:05',
      notes: 'Hi',
      internal_notes: '',
      confirm_overlap: false,
    });
    expect(newBooking({ ...chosen, minutes: 75 }, null, true)).toMatchObject({ customer_id: null, duration_minutes: 75, confirm_overlap: true });
  });
});

describe('slotChanges and noteChanges', () => {
  it('nothing changed, nothing sent', () => {
    expect([slotChanges(BOOKED, AS_BOOKED), noteChanges(BOOKED, AS_BOOKED)]).toEqual([{}, {}]);
  });

  it('sends the time, the length, the professional, the services and the notes that changed', () => {
    const chosen = { ...AS_BOOKED, time: '11:00', minutes: 45, staffId: 's2', serviceIds: ['colour'], internalNotes: 'Warm' };
    expect(slotChanges(BOOKED, chosen)).toEqual({ start: '2026-10-19T11:00', duration_minutes: 45, staff_id: 's2', services: [{ service_id: 'colour' }] });
    expect(noteChanges(BOOKED, chosen)).toEqual({ internal_notes: 'Warm' });
    expect(slotChanges(BOOKED, { ...AS_BOOKED, minutes: 30, staffId: null })).toEqual({});
  });
});

describe('seriesChange', () => {
  const OCCURRENCE = { ...BOOKED, recurring_id: 'r1', occurrence_date: '2026-10-19' };

  it('moves the series from the occurrence’s date: the time, and the weekday when the day changed', () => {
    expect(seriesChange(OCCURRENCE, { ...AS_BOOKED, time: '9:30' })).toEqual({ id: 'r1', from_date: '2026-10-19', time: '09:30' });
    expect(seriesChange(OCCURRENCE, { ...AS_BOOKED, day: '2026-10-21', minutes: 45, staffId: 's2' })).toEqual({
      id: 'r1',
      from_date: '2026-10-19',
      time: '10:00',
      day_of_week: 2,
      duration_minutes: 45,
      staff_id: 's2',
    });
  });
});

describe('refusedFields', () => {
  it('puts each reason under the panel’s field: length, professional, customer and a service of the list', () => {
    const error = { code: 'invalid_payload', message: 'x', status: 422, fields: { duration_minutes: 'a', staff_id: 'b', customer_id: 'c', 'services.0': 'd', notes: 'e' } };
    expect(refusedFields(error as never)?.fields).toEqual({ minutes: 'a', staff: 'b', customer: 'c', services: 'd', notes: 'e' });
    expect(refusedFields(null)).toBeNull();
  });
});

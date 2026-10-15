// What each appointment allows in its state (WORKBOOK APPOINTMENT-F03 to F11, F17 and the market's
// decisions): an action that does not apply is greyed out, never hidden; a charged appointment is final.
import { describe, expect, it } from 'vitest';

import type { AppointmentRow, AppointmentStatus } from '../operations';
import { ACTIONS, allows, customerLabel, hasOpenCheck, STATUS_TONE } from './states';

const NOW = new Date('2026-10-19T12:00:00+02:00');
const row = (status: AppointmentStatus, over: Partial<AppointmentRow> = {}): AppointmentRow => ({
  id: 'a1',
  number: 'APT-20261019-0001',
  customer_id: 'c1',
  customer_name: 'Lucía Pérez',
  staff_id: 's1',
  staff_name: 'Ana López',
  start: '2026-10-19T10:00:00+02:00',
  end: '2026-10-19T10:30:00+02:00',
  duration_minutes: 30,
  status,
  source: 'counter',
  services: [],
  service_names: 'Haircut',
  total: 2000,
  booked_by_customer: false,
  sale_id: null,
  order_id: null,
  recurring_id: null,
  occurrence_date: null,
  ...over,
});
const allowed = (item: AppointmentRow) => ACTIONS.filter((action) => allows(action, item, NOW));

describe('what an appointment allows', () => {
  it('in each state', () => {
    expect(allowed(row('pending'))).toEqual(['charge', 'edit', 'confirm', 'start', 'no_show', 'cancel', 'history', 'delete']);
    expect(allowed(row('confirmed'))).toEqual(['charge', 'edit', 'start', 'complete', 'no_show', 'cancel', 'history', 'delete']);
    expect(allowed(row('in_progress'))).toEqual(['charge', 'complete', 'history']);
    expect(allowed(row('completed'))).toEqual(['charge', 'history']);
    expect(allowed(row('cancelled'))).toEqual(['history', 'delete']);
    expect(allowed(row('no_show'))).toEqual(['cancel', 'history', 'delete']);
  });

  it('a no-show only once its time has passed', () => {
    expect(allows('no_show', row('confirmed', { start: '2026-10-19T13:00:00+02:00' }), NOW)).toBe(false);
  });

  it('charged is final: only its history', () => {
    expect(allowed(row('completed', { sale_id: 's9' }))).toEqual(['history']);
    expect(allowed(row('confirmed', { sale_id: 's9' }))).toEqual(['complete', 'history']);
  });

  it('a check open in the till holds it: no no-show, cancel nor delete until it is charged or voided', () => {
    expect(allowed(row('confirmed', { order_id: 'o1' }))).toEqual(['charge', 'edit', 'start', 'complete', 'history']);
    expect(hasOpenCheck(row('confirmed', { order_id: 'o1' }))).toBe(true);
    expect(hasOpenCheck(row('completed', { order_id: 'o1', sale_id: 's9' }))).toBe(false);
    expect(hasOpenCheck(row('confirmed'))).toBe(false);
  });

  it('names an erased customer and paints every status with a tone', () => {
    const t = (key: string) => (key === 'appointment.list.erasedCustomer' ? 'Deleted customer' : key);
    expect(customerLabel(row('pending', { customer_name: '' }), t)).toBe('Deleted customer');
    expect(customerLabel(row('pending'), t)).toBe('Lucía Pérez');
    expect(Object.keys(STATUS_TONE).sort()).toEqual(['cancelled', 'completed', 'confirmed', 'in_progress', 'no_show', 'pending']);
  });
});

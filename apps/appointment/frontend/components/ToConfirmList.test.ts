// The bookings still waiting for confirmation, of every day and soonest first (APPOINTMENT-F03): the same query that
// counts them, each row with its day, its row actions handed to the page, «Back to the agenda», and the list's
// empty, loading and error states.
import { describe, expect, it } from 'vitest';

import type { AppointmentRow } from '../operations';

import { errorFrame, mountAppointment, page, settle } from '../__tests__/mount-appointment';
import AppointmentList from './AppointmentList.vue';
import ToConfirmList from './ToConfirmList.vue';

const OP = 'appointment.appointment.list_to_confirm';
const booking: AppointmentRow = {
  id: 'p1',
  number: 'APT-0013',
  customer_id: 'c1',
  customer_name: 'Lucía Pérez',
  staff_id: 's1',
  staff_name: 'Ana López',
  start: '2026-11-27T12:00:00+01:00',
  end: '2026-11-27T12:30:00+01:00',
  duration_minutes: 30,
  status: 'pending',
  source: 'online',
  services: [],
  service_names: 'Styling',
  total: 2000,
  booked_by_customer: true,
  sale_id: null,
  order_id: null,
  recurring_id: null,
  occurrence_date: null,
};

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountAppointment(ToConfirmList, { props: { now: new Date('2026-11-26T10:00:00Z'), canDelete: true }, locale });
  await m.live();
  const list = () => m.wrapper.findComponent(AppointmentList);
  return { ...m, list };
}

describe('ToConfirmList', () => {
  it('lists the bookings to confirm with their day, and hands their actions and «Back to the agenda» to the page', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ limit: 100, offset: 0 }]);
    expect(s.list().props('loading')).toBe(true);
    await s.result(OP, { ...page([booking], 1, 100), timezone: 'Europe/Madrid' });
    expect(s.list().props()).toMatchObject({ rows: [booking], withDate: true, canAdd: false, canDelete: true, loading: false });

    s.list().vm.$emit('action', { actionId: 'confirm', row: booking });
    await s.find('appointment-to-confirm-back').trigger('click');
    expect(s.wrapper.emitted('action')).toEqual([[{ actionId: 'confirm', row: booking }]]);
    expect(s.wrapper.emitted('back')).toHaveLength(1);
  });

  it('says when none is left, and when they cannot load', async () => {
    const s = await setup();
    await s.result(OP, { ...page([], 0, 100), timezone: 'Europe/Madrid' });
    expect(s.list().props('emptyMessage')).toBe('No appointments left to confirm.');
    s.net.lastStream().push(errorFrame(s.subId(OP), 'internal_error'));
    await settle();
    expect(s.list().props('error')).toBe('Error loading appointments');
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    await s.result(OP, { ...page([], 0, 100), timezone: 'Europe/Madrid' });
    expect(s.find('appointment-to-confirm-notice').text()).toContain('Estas son las citas que esperan tu confirmación, sean del día que sean.');
    expect(s.find('appointment-to-confirm-back').text()).toBe('Volver a la agenda');
    expect(s.list().props('emptyMessage')).toBe('No quedan citas por confirmar.');
  });
});

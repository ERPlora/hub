// APPOINTMENT-F10 «Ver el historial de una cita»: every change with its time on the business's clock, who
// did it («Requested by the customer» when she asked) and what changed — from which professional or
// service to which, the new time and the reason. Loading, empty and error (with Retry) states.
import { describe, expect, it } from 'vitest';

import type { HistoryOut } from '../operations';
import { errorFrame, mountAppointment, page, settle } from '../__tests__/mount-appointment';
import AppointmentHistory from './AppointmentHistory.vue';

const OP = 'appointment.appointment.history';
const line = (over: Partial<HistoryOut>): HistoryOut => ({
  id: 'h1',
  action: 'created',
  at: '2026-10-19T09:00:00+02:00',
  actor: 'Ana López',
  by_customer: false,
  reason: '',
  old_value: {},
  new_value: {},
  ...over,
});

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountAppointment(AppointmentHistory, { props: { appointmentId: 'a1' }, locale });
  await m.live();
  const entries = () => m.wrapper.findAll('[data-testid="appointment-history-entry"]').map((e) => e.text().replace(/\s+/g, ' ').trim());
  return { ...m, entries };
}

describe('AppointmentHistory', () => {
  it('follows the history of its appointment, a hundred lines at most', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ id: 'a1', limit: 100 }]);
    expect(s.find('appointment-history-loading').exists()).toBe(true);
  });

  it('says what changed, when and who did it', async () => {
    const s = await setup();
    await s.result(
      OP,
      page([
        line({}),
        line({ id: 'h2', action: 'rescheduled', new_value: { start: '2026-10-19T11:15:00+02:00' } }),
        line({ id: 'h3', action: 'staff_changed', old_value: { staff: 'Ana López' }, new_value: { staff: 'Bea Ruiz' } }),
        line({ id: 'h4', action: 'cancelled', actor: '', by_customer: true, reason: 'Ill' }),
      ]),
    );
    expect(s.entries()).toEqual([
      expect.stringMatching(/Booked.*9:00 AM.*Ana López/),
      expect.stringMatching(/Time changed.*New time.*11:15 AM/),
      expect.stringMatching(/Professional changed.*Ana López → Bea Ruiz/),
      expect.stringMatching(/Cancelled.*Requested by the customer.*Reason.*Ill/),
    ]);
  });

  it('in Spanish, empty, and failing with Retry', async () => {
    const s = await setup('es');
    await s.result(OP, page([]));
    expect(s.find('appointment-history-empty').text()).toBe('Esta cita aún no tiene cambios registrados.');
    s.net.lastStream().push(errorFrame(s.subId(OP), 'appointment.boom'));
    await settle();
    expect(s.find('appointment-history-error').text()).toContain('No se pudo cargar el historial de la cita.');
  });
});

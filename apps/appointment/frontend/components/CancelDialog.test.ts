// APPOINTMENT-F05 «Cancelar una cita»: a confirmation (the market: Fresha, Timely, Phorest, Mangomint)
// naming whose appointment and when, with an optional reason that stays in its history; «Cancel the
// appointment» cancels it, «Keep it» leaves it. A refusal stays in the dialog.
import { describe, expect, it, vi } from 'vitest';

import type { AppointmentRow } from '../operations';
import { click, ionValue, mountAppointment, settle } from '../__tests__/mount-appointment';
import CancelDialog from './CancelDialog.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const ROW = {
  id: 'a1',
  number: 'APT-1',
  customer_name: 'Lucía Pérez',
  start: '2026-10-19T10:00:00+02:00',
} as AppointmentRow;

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountAppointment(CancelDialog, { props: { open: false, appointment: ROW }, locale });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  return m;
}

describe('CancelDialog', () => {
  it('names whose appointment and when, and cancels it with the reason', async () => {
    const s = await setup();
    expect(s.inDoc('appointment-cancel')?.textContent).toContain("Cancel Lucía Pérez's appointment (Monday, October 19, 2026 · 10:00 AM)?");
    await ionValue(s.inDoc('appointment-cancel-reason'), 'Ill', 'ionInput');
    s.answer(200, { ...ROW, status: 'cancelled' });
    await click(s.inDoc('appointment-cancel-submit'));
    expect(s.sent()).toEqual([
      { method: 'POST', path: '/api/appointment/appointments/cancel', query: {}, body: { id: 'a1', reason: 'Ill' } },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('keeps a refusal in the dialog, and speaks Spanish', async () => {
    const s = await setup('es');
    expect(s.inDoc('appointment-cancel-cancel')?.textContent).toContain('No cancelar');
    s.answer(409, { error: { code: 'appointment.cannot_cancel', message: 'Esta cita ya no se puede cancelar en su estado actual.' } });
    await click(s.inDoc('appointment-cancel-submit'));
    expect(s.inDoc('appointment-cancel-error')?.textContent).toContain('ya no se puede cancelar');
  });
});

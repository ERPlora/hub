// APPOINTMENT-F10: «History» of a row opens «Appointment history» with its number and its lines.
import { describe, expect, it, vi } from 'vitest';

import type { AppointmentRow } from '../operations';
import { click, mountAppointment, settle } from '../__tests__/mount-appointment';
import AppointmentHistory from './AppointmentHistory.vue';
import HistoryModal from './HistoryModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

describe('HistoryModal', () => {
  it('shows the history of the appointment and closes', async () => {
    const m = await mountAppointment(HistoryModal, { props: { open: false, appointment: { id: 'a1', number: 'APT-7' } as AppointmentRow } });
    await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
    await m.wrapper.setProps({ open: true });
    await settle();
    expect(m.inDoc('appointment-history-modal')?.getAttribute('aria-label')).toBe('Appointment history');
    expect(m.inDoc('appointment-history-modal')?.textContent).toContain('APT-7');
    expect(m.wrapper.findComponent(AppointmentHistory).props('appointmentId')).toBe('a1');
    await click(m.inDoc('appointment-history-modal-submit'));
    expect(m.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });
});

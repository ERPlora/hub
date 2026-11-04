// APPOINTMENT-F10: «History» of a row opens «Appointment history» with its number and its lines.
import { FormModal } from '@erplora/ui/components';
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
    // Read only: one «Close», no «Cancel» beside it.
    expect(m.inDoc('appointment-history-modal-cancel')).toBeNull();
    expect(m.inDoc('appointment-history-modal-submit')).toBeNull();
    expect(m.inDoc('appointment-history-modal')?.querySelectorAll('.ep-form-modal__footer ion-button')).toHaveLength(1);
    expect(m.inDoc('appointment-history-modal-done')?.textContent?.trim()).toBe('Close');
    // The common read-only window, not a footer of its own (hub#711).
    expect(m.wrapper.findComponent(FormModal).props('readonly')).toBe(true);
    await click(m.inDoc('appointment-history-modal-done'));
    expect(m.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('speaks Spanish: «Cerrar»', async () => {
    const m = await mountAppointment(HistoryModal, { props: { open: true, appointment: { id: 'a1', number: 'APT-7' } as AppointmentRow }, locale: 'es' });
    await settle();
    expect(m.inDoc('appointment-history-modal-done')?.textContent?.trim()).toBe('Cerrar');
  });
});

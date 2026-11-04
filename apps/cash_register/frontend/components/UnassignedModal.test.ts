// «Sale lines in no shift» (CASH_REGISTER-F17): the window with the sale lines that
// fell in no session; it only reads them while open. «Close» closes it.
import { FormModal } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import { click, mountCash } from '../__tests__/mount-cash-register';
import SessionLines from './SessionLines.vue';
import UnassignedModal from './UnassignedModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

describe('UnassignedModal', () => {
  it('lists the unassigned lines while open, and «Close» closes it', async () => {
    const m = await mountCash(UnassignedModal, { props: { open: true } });
    expect(m.inDoc('cash-register-unassigned')?.getAttribute('aria-label')).toBe('Sale lines in no shift');
    expect(m.wrapper.findComponent(SessionLines).props('query')).toEqual({ unassigned: true });
    await click(m.inDoc('cash-register-unassigned-done'));
    expect(m.wrapper.emitted('update:open')).toEqual([[false]]);
    expect(m.wrapper.findComponent(SessionLines).exists()).toBe(false);
  });

  it('is read only: its footer is one «Close», with no «Cancel» beside it (hub#711)', async () => {
    const m = await mountCash(UnassignedModal, { props: { open: true } });
    expect(m.inDoc('cash-register-unassigned')?.querySelectorAll('.ep-form-modal__footer ion-button')).toHaveLength(1);
    expect(m.inDoc('cash-register-unassigned-cancel')).toBeNull();
    expect(m.inDoc('cash-register-unassigned-submit')).toBeNull();
    expect(m.inDoc('cash-register-unassigned-done')?.textContent?.trim()).toBe('Close');
    expect(m.wrapper.findComponent(FormModal).props('readonly')).toBe(true);
  });

  it('speaks Spanish: «Cerrar»', async () => {
    const m = await mountCash(UnassignedModal, { props: { open: true }, locale: 'es' });
    expect(m.inDoc('cash-register-unassigned-done')?.textContent?.trim()).toBe('Cerrar');
  });
});

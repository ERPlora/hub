// «Sale lines in no shift» (CASH_REGISTER-F17): the window with the sale lines that
// fell in no session; it only reads them while open. «Close» closes it.
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
    await click(m.inDoc('cash-register-unassigned-submit'));
    expect(m.wrapper.emitted('update:open')).toEqual([[false]]);
    expect(m.wrapper.findComponent(SessionLines).exists()).toBe(false);
  });
});

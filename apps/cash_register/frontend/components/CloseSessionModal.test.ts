// The «Close session · S-…» window around its body (CloseSessionForm), which only exists — and only reads —
// while the window is open. A closed session closes the window; «Cancel» too.
import { describe, expect, it, vi } from 'vitest';

import { flush, mountCash } from '../__tests__/mount-cash-register';
import CloseSessionForm from './CloseSessionForm.vue';
import CloseSessionModal from './CloseSessionModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const SESSION = { id: 's1', number: 'S-261014-0001' };

describe('CloseSessionModal', () => {
  it('is «Close session · <number>» with its body only while open', async () => {
    const m = await mountCash(CloseSessionModal, { props: { open: true, session: SESSION } });
    expect(m.inDoc('cash-register-close')?.getAttribute('aria-label')).toBe('Close session · S-261014-0001');
    expect(m.wrapper.findComponent(CloseSessionForm).exists()).toBe(true);
    await m.wrapper.setProps({ open: false });
    expect(m.wrapper.findComponent(CloseSessionForm).exists()).toBe(false);
  });

  it('closes when the session closed or the person cancels', async () => {
    const m = await mountCash(CloseSessionModal, { props: { open: true, session: SESSION } });
    m.wrapper.findComponent(CloseSessionForm).vm.$emit('closed');
    await flush();
    expect(m.wrapper.emitted('update:open')).toEqual([[false]]);
    expect(m.wrapper.emitted('closed')).toHaveLength(1);
    await m.wrapper.setProps({ open: false });
    await m.wrapper.setProps({ open: true });
    m.wrapper.findComponent(CloseSessionForm).vm.$emit('cancel');
    await flush();
    expect(m.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });
});

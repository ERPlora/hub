// The «Close session · S-…» window around its body (CloseSessionForm), which only exists — and only reads —
// while the window is open. A closed session closes the window; «Cancel» too. «Close session» waits in grey until the
// business has answered its money (hub#921).
import { describe, expect, it, vi } from 'vitest';

import { expectWaitsForTheYen, flush, ionValue, mountCash } from '../__tests__/mount-cash-register';
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

describe('CloseSessionModal: before the business answers its money (hub#921)', () => {
  // What is closed once the yen arrives (1500, never 150000) is CloseSessionForm's test.
  it('«Close session» waits in grey and reads no count until the business answers', async () => {
    const m = await mountCash(CloseSessionModal, { props: { open: true, session: SESSION }, business: null });
    await m.live();
    const page = (rows: unknown[]) => ({ rows, total: rows.length, limit: 20, offset: 0 });
    await m.result('cash_register.session.get', { id: 's1', number: 'S-261014-0001', status: 'open', summary: { expected_cash: 1500 } });
    await m.result('cash_register.count.list', page([]));
    await m.result('sale.order.list', page([]));
    await m.result('kitchen.ticket.board', { cooking: [], ready: [], cooking_count: 0, ready_count: 0, stations: [], truncated: false });
    await m.result('printing.job.summary', { usages: [], pending: 0, sent: 0, failed: 0 });
    await ionValue(m.inDoc('cash-register-close-counted'), '1500', 'ionInput');
    await expectWaitsForTheYen(m, 'cash-register-close-submit', 'cash-register-close-counted');
  });
});

describe('CloseSessionModal: Android Back with unsaved changes (hub#1031, BASE-F05)', () => {
  it('as opened closes, also once the last closing count fills the cash; a change asks; restored closes again', async () => {
    const m = await mountCash(CloseSessionModal, { props: { open: true, session: SESSION } });
    await m.live();
    const page = (rows: unknown[]) => ({ rows, total: rows.length, limit: 20, offset: 0 });
    await m.result('cash_register.session.get', { id: 's1', number: 'S-261014-0001', status: 'open', summary: { expected_cash: 1500 } });
    await m.result('cash_register.count.list', page([{ id: 'c1', type: 'closing', total: 1500 }]));
    await m.result('sale.order.list', page([]));
    await m.result('kitchen.ticket.board', { cooking: [], ready: [], cooking_count: 0, ready_count: 0, stations: [], truncated: false });
    await m.result('printing.job.summary', { usages: [], pending: 0, sent: 0, failed: 0 });
    const counted = () => m.inDoc('cash-register-close-counted');
    const seeded = (counted() as unknown as { value?: unknown }).value;
    expect(seeded).toBeTruthy();
    const { expectUnsavedFormOnAndroidBack } = await import('../../../../base/frontend/__tests__/unsaved-form');
    await expectUnsavedFormOnAndroidBack({
      overlay: () => m.inDoc('cash-register-close'),
      change: () => ionValue(counted(), '14,00', 'ionInput'),
      restore: () => ionValue(counted(), seeded, 'ionInput'),
    });
    await ionValue(m.inDoc('cash-register-close-notes'), 'Short by one', 'ionInput');
    const { unsavedChangesIn } = await import('../../../../base/frontend/lib/system-back');
    expect(unsavedChangesIn(m.inDoc('cash-register-close')!)).toBeDefined();
  });
});

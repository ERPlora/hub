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

describe('CloseSessionModal: unsaved changes ask before closing (hub#1031, hub#1234, BASE-F05)', () => {
  /** The window with the session read and its last closing count (15,00) in the counted cash. */
  async function opened() {
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
    return { ...m, counted, seeded };
  }

  it('a changed count: Back, its «Cancel», the «×», Escape and a tap outside ask «Discard changes?»; restored, Back closes', async () => {
    const m = await opened();
    const { expectUnsavedFormAsksBeforeClosing } = await import('../../../../base/frontend/__tests__/unsaved-form');
    await expectUnsavedFormAsksBeforeClosing({
      overlay: () => m.inDoc('cash-register-close'),
      change: () => ionValue(m.counted(), '14,00', 'ionInput'),
      restore: () => ionValue(m.counted(), m.seeded, 'ionInput'),
    });
    await ionValue(m.inDoc('cash-register-close-notes'), 'Short by one', 'ionInput');
    const { unsavedChangesIn } = await import('../../../../base/frontend/lib/system-back');
    expect(unsavedChangesIn(m.inDoc('cash-register-close')!)).toBeDefined();
  });

  it('«Discard changes» after its «Cancel» closes the window and closes no session', async () => {
    const m = await opened();
    const { answerUnsavedQuestion } = await import('../../../../base/frontend/__tests__/unsaved-form');
    await ionValue(m.inDoc('cash-register-close-notes'), 'Short by one', 'ionInput');
    m.inDoc('cash-register-close-cancel')!.click();
    await flush();
    await answerUnsavedQuestion('discard');
    expect(m.inDoc('cash-register-close-notes')).toBeNull();
    expect(m.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
    expect(m.wrapper.emitted('closed')).toBeUndefined();
  });

  it('as opened, with the last closing count in the cash, its «Cancel», the «×», Escape and a tap outside close it without asking', async () => {
    const m = await opened();
    const { expectUntouchedWindowClosesAtOnce } = await import('../../../../base/frontend/__tests__/unsaved-form');
    await expectUntouchedWindowClosesAtOnce(m, 'cash-register-close');
  });
});

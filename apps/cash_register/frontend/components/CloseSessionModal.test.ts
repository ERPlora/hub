// The «Close session · S-…» window around its body (CloseSessionForm), which only exists — and only reads —
// while the window is open. A closed session closes the window; «Cancel» too. «Close session» waits in grey until the
// business has answered its money (hub#921).
import { toastSuccess } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';

import { expectSaveWaitsForMoney } from '../../../../base/frontend/__tests__/save-waits-for-money';
import { business, click, flush, ionValue, JAPANESE, mountCash, settle } from '../__tests__/mount-cash-register';
import { plain } from '../lib/money';
import CloseSessionForm from './CloseSessionForm.vue';
import CloseSessionModal from './CloseSessionModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));

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
  it('«Close session» waits in grey and reads no count; once the yen arrives «1500» is 1500', async () => {
    const m = await mountCash(CloseSessionModal, { props: { open: true, session: SESSION }, business: null });
    await m.live();
    const page = (rows: unknown[]) => ({ rows, total: rows.length, limit: 20, offset: 0 });
    await m.result('cash_register.session.get', { id: 's1', number: 'S-261014-0001', status: 'open', summary: { expected_cash: 1500 } });
    await m.result('cash_register.count.list', page([]));
    await m.result('sale.order.list', page([]));
    await m.result('kitchen.ticket.board', { cooking: [], ready: [], cooking_count: 0, ready_count: 0, stations: [], truncated: false });
    await m.result('printing.job.summary', { usages: [], pending: 0, sent: 0, failed: 0 });
    await ionValue(m.inDoc('cash-register-close-counted'), '1500', 'ionInput');
    m.answer(200, { id: 's1', number: 'S-261014-0001', status: 'closed', expected_balance: 1500, closing_balance: 1500, difference: 0 });
    const window = {
      wrapper: m.wrapper,
      save: () => m.inDoc('cash-register-close-submit'),
      amount: () => m.inDoc('cash-register-close-counted'),
      sent: m.sent,
      settle,
    };
    await expectSaveWaitsForMoney(window, () => m.result('base.business.get', business(JAPANESE)));
    await click(m.inDoc('cash-register-close-submit'));
    expect(m.sent().map((call) => call.body)).toEqual([{ session_id: 's1', closing_balance: 1500, closing_notes: '' }]);
    expect(plain(vi.mocked(toastSuccess).mock.calls[0][0])).toBe('Session S-261014-0001 closed · expected ¥1,500 · counted ¥1,500 · difference ¥0');
  });
});

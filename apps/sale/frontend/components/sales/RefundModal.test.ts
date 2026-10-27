// The Refund window (SALE-F31): «Refund sale <number>» around the refund body, which only exists (and
// only reads what can go back) while the window is open. A refund recorded closes it.
import { FormModal } from '@erplora/ui/components';
import { toastError } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';

import { flush, mountSale } from '../../__tests__/mount-sale';
import type { SaleRow } from '../../operations';
import RefundForm from './RefundForm.vue';
import RefundModal from './RefundModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
  toastError: vi.fn(() => Promise.resolve()),
}));

const SALE = { id: 's1', number: '20261014-0007' } as SaleRow;

async function setup(open = true, locale: 'en' | 'es' = 'en') {
  const m = await mountSale(RefundModal, { props: { open, sale: SALE }, locale });
  await m.clock.advance(150);
  return m;
}

describe('RefundModal', () => {
  it('is «Refund sale <number>» and reads what can go back only while open', async () => {
    const closed = await setup(false);
    expect(closed.params('sale.refund.options')).toEqual([]);
    const s = await setup();
    expect(s.inDoc('sale-refund')?.getAttribute('aria-label')).toBe('Refund sale 20261014-0007');
    expect(s.wrapper.findComponent(RefundForm).props('saleId')).toBe('s1');
    expect(s.params('sale.refund.options')).toEqual([{ sale_id: 's1' }]);
    // Its own button is the body's «Refund <amount>»: no generic Save / Cancel.
    expect(s.inDoc('sale-refund-submit')).toBeNull();
  });

  it('a refund recorded closes it', async () => {
    const s = await setup();
    s.wrapper.findComponent(RefundForm).vm.$emit('refunded');
    await flush();
    expect(s.wrapper.emitted('update:open')).toEqual([[false]]);
    expect(s.wrapper.emitted('refunded')).toHaveLength(1);
  });

  it('Enter in a field asks the body to refund (it answers with what is missing)', async () => {
    const s = await setup();
    await s.result('sale.refund.options', {
      sale_id: 's1',
      number: '20261014-0007',
      status: 'completed',
      currency: 'EUR',
      currency_decimals: 2,
      total: 100,
      refunded_total: 0,
      refundable_total: 100,
      tenders: [{ payment_id: 'p1', position: 1, method_id: 'm1', method_name: 'Cash', method_type: 'cash', charged: 100, refunded: 0, remaining: 100, refundable: true, reason: '' }],
      lines: [],
    });
    s.wrapper.findComponent(FormModal).vm.$emit('submit');
    await flush();
    expect(toastError).toHaveBeenCalledWith('A refund needs a reason.');
  });

  it('speaks Spanish', async () => {
    const s = await setup(true, 'es');
    expect(s.inDoc('sale-refund')?.getAttribute('aria-label')).toBe('Devolver la venta 20261014-0007');
  });
});

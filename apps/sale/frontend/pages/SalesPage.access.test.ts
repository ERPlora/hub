// Sales & POS → Sales, what is said before «Void» and «Refund» begin (SALE-F30, SALE-F31, BASE-F84): whoever does them
// hears nothing, whoever needs a manager's approval hears so as the window opens, and whoever their role says no to is
// told and no window opens. The actions look the same to everybody.
import { toastError, toastInfo } from '@erplora/ui/shell';
import { offeredRowActions, pressRowAction } from '@erplora/ui/testing/data-table';
import { describe, expect, it } from 'vitest';
import { ref } from 'vue';

import { EMPLOYEE, flush, MANAGER, mountSale, type MountOptions, type SaleSession } from '../__tests__/mount-sale';
import RefundModal from '../components/sales/RefundModal.vue';
import VoidSaleModal from '../components/sales/VoidSaleModal.vue';
import type { SaleRow } from '../operations';
import SalesPage from './SalesPage.vue';

const SALE: SaleRow = {
  id: 's1',
  number: '20261014-0001',
  business_day: '2026-10-14',
  currency: 'EUR',
  currency_decimals: 2,
  created_at: '2026-10-14T10:05:00Z',
  status: 'completed',
  document_type: 'ticket',
  customer_id: null,
  customer_name: '',
  payment_method_name: 'Cash',
  staff_id: null,
  total: 1250,
  tax_total: 114,
  refunded_total: 0,
  refundable_total: 1250,
  sessions_to_return: 0,
  has_refunds: false,
  invoice_status: 'issued',
  documents_pending: false,
};

const WITHOUT_VOIDS: SaleSession = { ...EMPLOYEE, approvable: ['sale.refund_sale'] };
const WITHOUT_REFUNDS: SaleSession = { ...EMPLOYEE, approvable: ['sale.void_sale'] };

async function setup(options: MountOptions) {
  const m = await mountSale(SalesPage, { path: '/sale/sales', ...options });
  await m.live();
  await m.result('sale.sale.list', { rows: [SALE], total: 1, limit: 50, offset: 0 }, { offset: 0 });
  const press = async (action: string) => {
    await pressRowAction(m.wrapper, 's1', action);
    await flush();
  };
  const opened = () => [VoidSaleModal, RefundModal].map((modal) => m.wrapper.findComponent(modal).props('open'));
  return { ...m, press, opened };
}

describe('SalesPage: before a void or a refund begins', () => {
  it('whoever does them hears nothing', async () => {
    const s = await setup({ session: MANAGER });
    await s.press('void');
    await s.press('refund');
    expect(s.opened()).toEqual([true, true]);
    expect(toastInfo).not.toHaveBeenCalled();
    expect(toastError).not.toHaveBeenCalled();
  });

  it.each([
    ['void', [true, false], 'A manager will have to approve this void.'],
    ['refund', [false, true], 'A manager will have to approve this refund.'],
  ])('«%s» with approval opens its window, saying a manager will have to approve it', async (action, opened, said) => {
    const s = await setup({ session: EMPLOYEE });
    await s.press(action);
    expect(s.opened()).toEqual(opened);
    expect(toastInfo).toHaveBeenCalledExactlyOnceWith(said);
    expect(toastError).not.toHaveBeenCalled();
  });

  it.each([
    ['void', WITHOUT_VOIDS, 'Your role does not let you void a sale. Ask a manager to do it.'],
    ['refund', WITHOUT_REFUNDS, 'Your role does not let you refund a sale. Ask a manager to do it.'],
  ])('«%s» the role says no to opens nothing, sends nothing and says why', async (action, session, said) => {
    const s = await setup({ session });
    await s.press(action);
    expect(s.opened()).toEqual([false, false]);
    expect(toastError).toHaveBeenCalledExactlyOnceWith(said);
    expect(toastInfo).not.toHaveBeenCalled();
    expect(s.sent().filter((call) => call.method === 'POST')).toEqual([]);
  });

  it('a no to one leaves the other as the role says', async () => {
    const s = await setup({ session: WITHOUT_VOIDS });
    await s.press('refund');
    expect(s.opened()).toEqual([false, true]);
  });

  it.each([
    ['void', WITHOUT_VOIDS, 'Tu rol no permite anular una venta. Pídeselo a un encargado.'],
    ['refund', WITHOUT_REFUNDS, 'Tu rol no permite devolver una venta. Pídeselo a un encargado.'],
  ])('«%s» is refused in the person’s language', async (action, session, said) => {
    const s = await setup({ session, locale: 'es' });
    await s.press(action);
    expect(toastError).toHaveBeenCalledExactlyOnceWith(said);
  });

  it.each([
    ['void', 'Un encargado tendrá que aprobar esta anulación.'],
    ['refund', 'Un encargado tendrá que aprobar esta devolución.'],
  ])('«%s» with approval is said in the person’s language', async (action, said) => {
    const s = await setup({ session: EMPLOYEE, locale: 'es' });
    await s.press(action);
    expect(toastInfo).toHaveBeenCalledExactlyOnceWith(said);
  });

  it('the actions are the same for everybody', async () => {
    for (const session of [MANAGER, EMPLOYEE, WITHOUT_VOIDS, WITHOUT_REFUNDS]) {
      const s = await setup({ session });
      expect(offeredRowActions(s.wrapper, 's1')).toEqual(['document', 'reprint', 'void', 'refund']);
      s.wrapper.unmount();
    }
  });

  it('follows the role as it changes with the screen open', async () => {
    const session = ref<SaleSession>(EMPLOYEE);
    const s = await setup({ session });
    session.value = WITHOUT_VOIDS;
    await flush();
    await s.press('void');
    expect(s.opened()).toEqual([false, false]);
    session.value = { ...EMPLOYEE, permissions: [...EMPLOYEE.permissions, 'sale.void_sale'] };
    await flush();
    await s.press('void');
    expect(s.opened()).toEqual([true, false]);
    expect(toastInfo).not.toHaveBeenCalled();
  });
});

// Sales & POS → Sell: the table of the check, with Tables on.
// The shell is loaded first, as in the till's other tests: it hooks Ionic's form controls before `@ionic/vue` defines them.
import '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';

import { click, MANAGER, settle } from '../__tests__/mount-sale';
import { freshEachTest, LUCIA, setup } from '../__tests__/pos-page';
import CartHeading from '../components/pos/CartHeading.vue';
import TableButton from '../components/pos/TableButton.vue';
import TablePicker from '../components/pos/TablePicker.vue';
import { CURRENT_CHECK_KEY } from '../composables/pos/useCurrentCheck';

// The checkout sheet, the document window and Customers' search, by their contracts.
vi.mock('../components/checkout/CheckoutSheet.vue', async () => (await import('../__tests__/pos-page-stubs')).CHECKOUT_SHEET);
vi.mock('../components/document/DocumentModal.vue', async () => (await import('../__tests__/pos-page-stubs')).DOCUMENT_MODAL);
vi.mock('../../../customer/frontend/components/CustomerSearch.vue', async () => (await import('../__tests__/pos-page-stubs')).CUSTOMER_SEARCH);

freshEachTest();

describe('PosPage: the table of the check (SALE-F19)', () => {
  const TABLE_PERMISSIONS = ['table.view_table', 'table.add_session', 'table.view_session', 'table.change_session'];
  /** Tables is on in this business and the person sees the tables, seats and follows the table checks. */
  const WITH_TABLES = { ...MANAGER, permissions: [...MANAGER.permissions, ...TABLE_PERMISSIONS], apps: [{ label: 'table', state: 'on' as const }] };
  const without = (permission: string) => ({ ...WITH_TABLES, permissions: WITH_TABLES.permissions.filter((p) => p !== permission) });
  const TABLE_OPS = ['table.session.by_order', 'table.table.list', 'table.floor.status'] as const;
  const seatOf = (over: Record<string, unknown> = {}) => ({
    id: 's1',
    table_id: 't4',
    table_number: '4',
    zone_id: 'z1',
    zone_name: 'Terrace',
    order_id: 'o1',
    guests_count: 4,
    status: 'open',
    waiter_id: 'u1',
    waiter_name: 'Ana',
    opened_at: '2026-10-15T12:00:00+02:00',
    closed_at: null,
    notes: '',
    split_from_id: null,
    transferred_from_id: null,
    merged_into_id: null,
    paid_total: null,
    customer_id: null,
    customer_name: null,
    ...over,
  });

  it('without Tables on, or without the right to see the tables or seat, nothing about tables shows nor is followed', async () => {
    const sessions = [
      { ...WITH_TABLES, apps: [] },
      { ...WITH_TABLES, apps: [{ label: 'table', state: 'activating' as const }] },
      without('table.view_table'),
      without('table.add_session'),
    ];
    for (const session of sessions) {
      const s = await setup({ session });
      await s.addProduct();
      expect(s.find('pos-table-trigger').exists()).toBe(false);
      expect(s.find('pos-table-chip').exists()).toBe(false);
      for (const op of TABLE_OPS) expect(s.params(op), op).toEqual([]);
    }
  });

  it('with Tables on, the button is in the check’s bar; the check’s table is followed once there is a check', async () => {
    const s = await setup({ session: WITH_TABLES, locale: 'es' });
    expect(s.find('pos-table-trigger').attributes('aria-label')).toBe('Asignar mesa');
    for (const op of TABLE_OPS) expect(s.params(op), op).toEqual([]);
    await s.addProduct();
    expect(s.params('table.session.by_order')).toEqual([{ order_id: 'o1' }]);
    await s.result('table.session.by_order', { rows: [seatOf()] });
    expect(s.wrapper.findComponent(TableButton).props('tableNumber')).toBe('4');
    expect(s.find('pos-table-chip').text()).toBe('Mesa 4');
    expect(s.find('pos-check-context-empty').exists()).toBe(false);
  });

  it('the check’s follower and the table’s never share a key: the duplicate broke the till once a check opened', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    try {
      const s = await setup({ session: WITH_TABLES });
      await s.addProduct();
      expect(s.params('table.session.by_order')).toEqual([{ order_id: 'o1' }]);
      const duplicates = warn.mock.calls.filter((call) => String(call[0]).includes('Duplicate keys'));
      expect(duplicates).toEqual([]);
    } finally {
      warn.mockRestore();
    }
  });

  it('without the right to see the table checks, the button stays but no table is followed', async () => {
    const s = await setup({ session: without('table.view_session') });
    await s.addProduct();
    expect(s.find('pos-table-trigger').exists()).toBe(true);
    expect(s.params('table.session.by_order')).toEqual([]);
  });

  it('the button opens «Choose table» with the check, its seat and its parked table check', async () => {
    const s = await setup({ session: WITH_TABLES });
    await s.addProduct();
    const seat = seatOf();
    await s.result('table.session.by_order', { rows: [seat] });
    expect(s.wrapper.findComponent(TablePicker).exists()).toBe(false);
    await click(s.find('pos-table-trigger').element);
    expect(s.wrapper.findComponent(TablePicker).props()).toMatchObject({ open: true, orderId: 'o1', seat, parked: null });
    await s.reopen();
    expect(s.params('table.table.list')).toHaveLength(1);
  });

  it('seated with no check yet: the check Tables opened goes on the till, with the customer already chosen', async () => {
    const s = await setup({ session: WITH_TABLES });
    s.wrapper.findComponent({ name: 'CustomerSearch' }).vm.$emit('update:modelValue', LUCIA);
    await settle();
    await click(s.find('pos-table-trigger').element);
    expect(s.wrapper.findComponent(TablePicker).props('orderId')).toBeNull();
    s.reply({ order_id: 'o9', customer_id: 'c1' });
    s.wrapper.findComponent(TablePicker).vm.$emit('seated', seatOf({ order_id: 'o9' }));
    await settle();
    await s.reopen();
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBe('o9');
    expect(s.params('sale.order.get')).toEqual([{ order_id: 'o9' }]);
    expect(s.params('table.session.by_order')).toEqual([{ order_id: 'o9' }]);
    expect(s.writes()).toEqual([['/api/customer/orders/link', { order_id: 'o9', customer_id: 'c1' }]]);
    expect(s.wrapper.findComponent(CartHeading).props('customerName')).toBe('Lucía');
  });

  it('seated with the check on screen: the till keeps it', async () => {
    const s = await setup({ session: WITH_TABLES });
    await s.addProduct();
    await click(s.find('pos-table-trigger').element);
    s.wrapper.findComponent(TablePicker).vm.$emit('seated', seatOf());
    await settle();
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBe('o1');
    expect(s.writes()).toEqual([['/api/sale/orders', { lines: [{ product_id: 'p1' }] }]]);
  });

  it('a charged check takes its table off the screen', async () => {
    const s = await setup({ session: WITH_TABLES });
    await s.addProduct();
    await s.result('table.session.by_order', { rows: [seatOf()] });
    expect(s.find('pos-table-chip').exists()).toBe(true);
    await click(s.find('pos-charge').element);
    s.wrapper.findComponent({ name: 'CheckoutSheet' }).vm.$emit('charged', { id: 'sale-1' }, []);
    await settle();
    expect(s.find('pos-table-chip').exists()).toBe(false);
    expect(s.wrapper.findComponent(TableButton).props('tableNumber')).toBeNull();
  });
});

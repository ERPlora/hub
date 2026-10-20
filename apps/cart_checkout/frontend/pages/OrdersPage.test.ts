// Cart & Checkout → Orders (WORKBOOK «Pantallas · Pedidos»; CART_CHECKOUT-F09 to F12): the live
// `cart_checkout.order.list` with the old table's Order, Email, Status, Payment and Total, «Search order or
// email…», filters per column (the total from / to in the unit the column shows, cart_checkout#26),
// newest first, 50 a page, list or cards. Each row offers the step it can take — «Mark paid» (Initiated),
// «Complete» (Paid), «Fail» (Initiated or Paid, with its reason in a form) —, only to whoever may; a
// failed order shows its reason. No «add»: orders are born from a cart (CART_CHECKOUT-F08). The total
// paints in the order's own currency (the old screen used the business's), in minor units (the old #9).
import { DataTable, type DataTableAction, EmptyState, InlineFeedback, StatusPill } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import type { OrderOut, OrderStatus } from '../operations';
import { CART_KEEPER, EMPLOYEE, flush, type MountOptions, mountCartCheckout, page } from '../__tests__/mount-cart-checkout';
import FailOrderModal from '../components/FailOrderModal.vue';
import OrdersPage from './OrdersPage.vue';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'cart_checkout.order.list';
const order = (id: string, status: OrderStatus, over: Partial<OrderOut> = {}): OrderOut => ({
  id,
  cart_id: 'c1',
  session_token: 'sess_1',
  order_number: `OS-20261014-000${id}`,
  customer_email: 'ana@example.com',
  shipping_address: {},
  billing_address: {},
  shipping_method: '',
  payment_method: 'Card',
  status,
  total_amount: 3150,
  currency: 'EUR',
  notes: '',
  failure_reason: '',
  placed_at: '2026-10-14T10:00:00Z',
  paid_at: null,
  failed_at: null,
  completed_at: null,
  created_by: 'Ana',
  updated_by: 'Ana',
  created_at: '2026-10-14T10:00:00Z',
  updated_at: '2026-10-14T10:00:00Z',
  ...over,
});
const INITIATED = order('1', 'initiated');
const PAID = order('2', 'paid', { payment_method: '' });
const FAILED = order('3', 'failed', { failure_reason: 'Card declined' });
const COMPLETED = order('4', 'completed', { total_amount: 1999, currency: 'JPY' });
const ROWS = [INITIATED, PAID, FAILED, COMPLETED];
const NUMBER_WIDTH = 'minmax(10.5rem, 1fr)';

async function setup(options: MountOptions = {}) {
  const m = await mountCartCheckout(OrdersPage, { path: '/cart_checkout/orders', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="cart-checkout-orders-row"]');
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => c.text().trim());
  const action = (id: string) => prop<DataTableAction<OrderOut>[]>('actions').find((a) => a.id === id)!;
  const offered = (row: OrderOut) =>
    prop<DataTableAction<OrderOut>[]>('actions')
      .filter((a) => !a.hidden?.(row))
      .map((a) => (typeof a.label === 'function' ? a.label(row) : a.label));
  return { ...m, table, prop, rows, cells, action, offered, list: () => m.params(OP), show: (data: unknown) => m.result(OP, data) };
}

describe('OrdersPage', () => {
  it('while the first page loads, the table paints the loading state and counts nothing (pm#611)', async () => {
    const s = await setup();
    expect(s.prop('loading')).toBe(true);
    expect(s.find('cart-checkout-orders-loading').exists()).toBe(true);
    expect(s.wrapper.text()).not.toMatch(/\b0 orders?\b/i);
    await s.show(page(ROWS));
    expect(s.prop('loading')).toBe(false);
    expect(s.find('cart-checkout-orders-loading').exists()).toBe(false);
  });

  it('follows the orders newest first, with the old table’s columns and no add', async () => {
    const s = await setup();
    expect(s.list()).toEqual([{ sort: '-created_at', limit: 50, offset: 0 }]);
    await s.show(page(ROWS));
    // The topbar names the app, as the old hub's did; the tabbar says which section.
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Cart & Checkout');
    expect(s.prop('searchPlaceholder')).toBe('Search order or email…');
    expect(s.prop('addable')).toBe(false);
    expect(s.prop<Array<{ key: string; label: string }>>('columns').map((c) => [c.key, c.label])).toEqual([
      ['order_number', 'Order'],
      ['customer_email', 'Email'],
      ['status', 'Status'],
      ['payment_method', 'Payment'],
      ['total_amount', 'Total'],
    ]);
    expect(s.cells(0).slice(0, 5)).toEqual(['OS-20261014-0001', 'ana@example.com', 'Initiated', 'Card', '€31.50']);
    // The number's column holds a whole «OS-AAAAMMDD-NNNN»: it tells one order from the next.
    expect(s.prop<Array<{ key: string; width?: string }>>('columns')[0].width).toBe(NUMBER_WIDTH);
    // No payment method: a dash, as the old table.
    expect(s.cells(1)[3]).toBe('—');
    // The total in the order's own currency (the old screen used the business's).
    expect(s.cells(3)[4]).toBe('¥1,999');
  });

  it('paints every status as its pill, and a failed order its reason', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(s.wrapper.findAllComponents(StatusPill).map((p) => [p.props('label'), p.props('tone')])).toEqual([
      ['Initiated', 'neutral'],
      ['Paid', 'info'],
      ['Failed', 'danger'],
      ['Completed', 'success'],
    ]);
    expect(s.cells(2)[2]).toContain('Reason: Card declined');
  });

  it('filters on the server: fragments, the status by list, the total in euros', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    const columns = s.prop<Array<{ key: string; filter?: { type: string; options?: Array<{ value: string }> } }>>('columns');
    expect(columns.map((c) => [c.key, c.filter?.type ?? null])).toEqual([
      ['order_number', 'text'],
      ['customer_email', 'text'],
      ['status', 'select'],
      ['payment_method', 'text'],
      ['total_amount', 'range'],
    ]);
    expect(columns[2].filter?.options?.map((o) => o.value)).toEqual(['initiated', 'paid', 'failed', 'completed']);
    s.table().vm.$emit('filtersChange', {
      order_number: '0003',
      customer_email: 'ana',
      status: 'paid',
      payment_method: 'card',
      total_amount_from: '12',
      total_amount_to: '50',
    });
    await flush();
    expect(s.list()).toEqual([
      {
        order_number: '0003',
        customer_email: 'ana',
        status: 'paid',
        payment_method: 'card',
        total_amount_min: 1200,
        total_amount_max: 5000,
        sort: '-created_at',
        limit: 50,
        offset: 0,
      },
    ]);
  });

  it('the total is typed as an amount, read as it is pasted, and one it cannot read says so under its box (pm#521)', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    const total = s.prop<Array<{ key: string; filter?: unknown }>>('columns').find((c) => c.key === 'total_amount');
    expect(total?.filter).toEqual({ type: 'range', amount: true });
    s.table().vm.$emit('filtersChange', { total_amount_from: '1.250,50', total_amount_to: '1.250' });
    await flush();
    // «1.250» is 1.250 € or 1,25 €: it filters nothing and says why, never the wrong amount.
    expect(s.list()).toEqual([{ total_amount_min: 125050, sort: '-created_at', limit: 50, offset: 0 }]);
    expect(s.prop('filterErrors')).toEqual({ total_amount_to: 'Type an amount, like 12.50' });
    s.table().vm.$emit('filtersChange', { total_amount_from: '12' });
    await flush();
    expect(s.prop('filterErrors')).toEqual({});
  });

  it('none at all says «No orders.» and how they are born; a search without rows «No results»', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No orders.');
    expect(s.wrapper.findComponent(EmptyState).props('message')).toBe('Orders are started from a cart with the assistant or the API.');
    s.table().vm.$emit('update:search', 'OS-');
    await flush();
    await s.reopen();
    await s.show(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No results');
  });

  it('each row offers the step it can take', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(ROWS.map((row) => s.offered(row))).toEqual([['Mark paid', 'Fail'], ['Complete', 'Fail'], [], []]);
  });

  it('a step sends its command; a refusal shows above the table', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    s.answer(200, { ...INITIATED, status: 'paid' });
    s.table().vm.$emit('action', { actionId: 'pay', row: INITIATED });
    await flush();
    s.table().vm.$emit('action', { actionId: 'complete', row: PAID });
    await flush();
    expect(s.sent().map((c) => [c.path, c.body])).toEqual([
      ['/api/cart_checkout/orders/mark_paid', { order_id: '1' }],
      ['/api/cart_checkout/orders/complete', { order_id: '2' }],
    ]);
    const message = 'Only an initiated order can be marked as paid; this one is Paid.';
    s.answer(409, { error: { code: 'cart_checkout.invalid_transition', message } });
    s.table().vm.$emit('action', { actionId: 'pay', row: INITIATED });
    await flush();
    const banner = s.wrapper.findAllComponents(InlineFeedback).find((b) => b.attributes('data-testid') === 'cart-checkout-orders-row-error');
    expect([banner?.props('heading'), banner?.text()]).toEqual(['Could not complete the action', expect.stringContaining(message)]);
  });

  it('a double tap on a step sends it once, and the row says it is running', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    s.answer(200, { ...INITIATED, status: 'paid' });
    s.table().vm.$emit('action', { actionId: 'pay', row: INITIATED });
    s.table().vm.$emit('action', { actionId: 'pay', row: INITIATED });
    expect(s.action('pay').loading?.(INITIATED)).toBe(true);
    await flush();
    expect(s.sent()).toHaveLength(1);
  });

  it('Fail opens its form with the row', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    s.table().vm.$emit('action', { actionId: 'fail', row: PAID });
    await flush();
    const modal = s.wrapper.findComponent(FailOrderModal);
    expect([modal.props('open'), modal.props('order')]).toEqual([true, PAID]);
    expect(s.sent()).toEqual([]);
  });

  it('cards show the order number', async () => {
    const s = await setup();
    expect(s.prop<(row: OrderOut) => string>('cardTitle')(INITIATED)).toBe('OS-20261014-0001');
  });

  it('whoever may not take orders through checkout, or an employee, only looks', async () => {
    for (const session of [CART_KEEPER, EMPLOYEE]) {
      const s = await setup({ session });
      await s.show(page(ROWS));
      expect(ROWS.map((row) => s.offered(row))).toEqual([[], [], [], []]);
    }
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(page(ROWS));
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Carrito y pago');
    expect(s.prop('searchPlaceholder')).toBe('Buscar pedido o email…');
    expect(s.cells(0).slice(2, 5).map((cell) => cell.replace(/[  ]/g, ' '))).toEqual(['Iniciado', 'Card', '31,50 €']);
    expect(s.offered(INITIATED)).toEqual(['Marcar pagado', 'Fallar']);
    expect(s.offered(PAID)).toEqual(['Completar', 'Fallar']);
  });
});

describe('OrdersPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});

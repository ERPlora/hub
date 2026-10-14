// «Linked orders» on the card (CUSTOMER-F19): the open orders the till linked to this customer, the
// latest first, with when; live.
import { formatDateTime } from '@erplora/ui/components';
import { describe, expect, it } from 'vitest';

import { pageOf } from '../__tests__/fixtures';
import { errorFrame, flush, type MountOptions, mountCustomer, subId } from '../__tests__/mount-customer';
import LinkedOrders from './LinkedOrders.vue';

const LIST = 'customer.order.list';
const order = { order_id: '0192aaaa-bbbb-7ccc-8ddd-eeeeffff0001', customer_id: 'c1', linked_at: '2026-10-03T09:00:00Z' };

async function setup(options: MountOptions = {}) {
  const m = await mountCustomer(LinkedOrders, { props: { customerId: 'c1' }, ...options });
  const call = await m.live();
  return { ...m, call };
}

describe('LinkedOrders', () => {
  it('follows the card\'s orders and paints each with its short id and when it was linked', async () => {
    const s = await setup();
    expect(s.params(LIST)).toEqual([{ customer_id: 'c1', limit: 50, offset: 0 }]);
    await s.result(s.call, LIST, pageOf([order]));
    const item = s.wrapper.get('[data-testid="customer-order"]');
    expect(item.get('.customer-orders__id').text()).toBe('Order ffff0001');
    expect(item.get('.customer-orders__id').attributes('title')).toBe(order.order_id);
    expect(item.get('.customer-orders__when').text()).toBe(formatDateTime('2026-10-03T09:00:00Z', 'en'));
  });

  it('«Show more» grows the window, never asking for more than 100 at once', async () => {
    const s = await setup();
    await s.result(s.call, LIST, { ...pageOf([order]), total: 300 });
    for (let i = 0; i < 2; i++) {
      await s.wrapper.get('[data-testid="customer-orders-more"]').trigger('click');
      await flush();
    }
    const windows = s.params(LIST) as { limit: number; offset: number }[];
    expect(windows.map((w) => [w.offset, w.limit]).sort((a, b) => a[0] - b[0])).toEqual([
      [0, 100],
      [100, 50],
    ]);
  });

  it('says «No linked orders.»; a failed load says so', async () => {
    const s = await setup();
    await s.result(s.call, LIST, pageOf([]));
    expect(s.wrapper.get('[data-testid="customer-orders-empty"]').text()).toBe('No linked orders.');
    s.call.push(errorFrame(subId(s.client, LIST), 'boom'));
    await flush();
    expect(s.wrapper.get('[data-testid="customer-orders-error"]').text()).toContain('The orders could not be loaded');
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.result(s.call, LIST, pageOf([order]));
    expect(s.wrapper.get('h3').text()).toBe('Pedidos enlazados');
    expect(s.wrapper.get('.customer-orders__id').text()).toBe('Pedido ffff0001');
  });
});

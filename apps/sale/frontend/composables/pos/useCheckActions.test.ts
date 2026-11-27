import { toastError } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { EMPLOYEE } from '../../__tests__/mount-sale';
import { answers, asks, CHECK, freshEachTest, setup } from '../../__tests__/till';
import { product, refused } from '../../components/pos/__tests__/fixtures';
import { CURRENT_CHECK_KEY } from './useCurrentCheck';

freshEachTest();

describe('useTill: the check', () => {
  it('a title typed with a check open is saved on it; a refusal says so', async () => {
    const s = await setup();
    s.reply(CHECK);
    await s.till().addProduct(product({ id: 'p1' }), null);
    await s.till().rename('Table 4');
    expect(s.calls().at(-1)).toEqual(['/set_label', { order_id: 'o1', label: 'Table 4' }]);
    s.net.onApi(() => Promise.reject(new TypeError('Failed to fetch')));
    await s.till().rename('Table 5');
    expect(toastError).toHaveBeenCalledWith('The check title could not be saved');
  });

  it('parks under a title and lets the screen go', async () => {
    const s = await setup();
    s.reply(CHECK);
    await s.till().addProduct(product({ id: 'p1' }), null);
    expect(await s.till().park('Ana')).toEqual({ ok: true });
    expect(s.calls().at(-1)).toEqual(['/set_label', { order_id: 'o1', label: 'Ana' }]);
    expect(s.till().order.value).toBeNull();
    expect(s.till().orderId.value).toBeNull();
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBeNull();
  });

  it('a refused park keeps the check on screen', async () => {
    const s = await setup();
    s.reply(CHECK);
    await s.till().addProduct(product({ id: 'p1' }), null);
    s.net.onApi(() => Promise.reject(new TypeError('Failed to fetch')));
    expect(await s.till().park('Ana')).toEqual({ ok: false, message: 'The check could not be parked. It is still on screen.' });
    expect(s.till().orderId.value).toBe('o1');
  });

  it('voids the check on screen and lets it go', async () => {
    const s = await setup();
    s.reply(CHECK);
    await s.till().addProduct(product({ id: 'p1' }), null);
    expect(await s.till().voidCheck()).toEqual({ ok: true });
    expect(s.calls().at(-1)).toEqual(['/void', { order_id: 'o1' }]);
    expect(s.till().orderId.value).toBeNull();
  });

  it('an employee deletes a check with something on it once a manager approves it with their PIN', async () => {
    const s = await setup({ session: EMPLOYEE });
    s.reply(CHECK);
    await s.till().addProduct(product({ id: 'p1' }), null);
    s.net.onApi(
      answers(
        refused('permission_denied', 'Permission “sale.void_sale” is required.', 403),
        asks('sale.order.void_ordered', 'Delete an open check with something on it'),
        Response.json({ ...CHECK, status: 'voided' }),
      ),
    );
    expect(await s.till().voidCheck()).toEqual({ ok: true });
    expect(s.calls().slice(1)).toEqual([
      ['/void', { order_id: 'o1' }],
      ['/void_ordered', { order_id: 'o1' }],
      ['/void_ordered', { order_id: 'o1' }],
    ]);
    expect(s.till().orderId.value).toBeNull();
  });
});

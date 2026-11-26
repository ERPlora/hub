import { describe, expect, it } from 'vitest';

import { flush } from '../../__tests__/mount-sale';
import { CHECK, freshEachTest, setup } from '../../__tests__/till';
import { deferred, line, order, product } from '../../components/pos/__tests__/fixtures';

freshEachTest();

describe('useTill: adding products', () => {
  it('one write at a time: two quick taps never open two checks', async () => {
    const s = await setup();
    const first = deferred();
    let count = 0;
    s.net.onApi(() => (++count === 1 ? first.promise : Response.json(order({ version: 2, lines: [line(), line({ id: 'l2', product_id: 'p2' })] }))));
    const a = s.till().addProduct(product({ id: 'p1' }), null);
    const b = s.till().addProduct(product({ id: 'p2' }), null);
    await flush();
    expect(s.calls()).toHaveLength(1);
    expect(s.till().busy.value).toBe(true);
    first.resolve(Response.json(CHECK));
    await Promise.all([a, b]);
    expect(s.calls()).toEqual([
      ['', { lines: [{ product_id: 'p1' }] }],
      ['/add_line', { order_id: 'o1', product_id: 'p2' }],
    ]);
    expect(s.till().busy.value).toBe(false);
  });
});

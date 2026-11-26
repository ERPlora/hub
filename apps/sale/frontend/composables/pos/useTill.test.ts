// `useTill()`: the check on screen and every write to it (SALE-F01, F09, F13–F18; spec «Cart → order
// mapping»). The first line opens the check (and the device remembers it); the next ones go to it; a
// second tap on the same product raises its line. One write in flight at a time per check. What the
// screen shows is what the operations answer (no money of its own); a refusal says the server's words. What the
// cashier's role does not allow, a manager approves with their PIN on this very device (BASE-F84).
import { describe, expect, it } from 'vitest';

import { CHECK, freshEachTest, setup } from '../../__tests__/till';
import { product } from '../../components/pos/__tests__/fixtures';
import { CURRENT_CHECK_KEY } from './useCurrentCheck';

freshEachTest();

describe('useTill: adding products', () => {
  it('the first product opens the check with it; the device remembers the check', async () => {
    const s = await setup();
    s.reply(CHECK);
    await s.till().addProduct(product({ id: 'p1' }), null);
    expect(s.calls()).toEqual([['', { lines: [{ product_id: 'p1' }] }]]);
    expect(s.till().order.value).toEqual(CHECK);
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBe('o1');
    expect(s.opened).toEqual(['o1']);
  });
});

// The live check on screen (`sale.order.get`) and, only while it has lines (`valued`, which the page
// knows from the last answer, a write's or this one's), its preview (`sale.checkout.preview`: the total
// the cart paints). Renderless: the page mounts it only while there is a check (`useLive` has no
// «skip») and receives what the server says.
import { describe, expect, it } from 'vitest';

import { errorFrame, mountSale } from '../../__tests__/mount-sale';
import { order, preview } from './__tests__/fixtures';
import CheckFollower from './CheckFollower.vue';

async function setup(valued = false) {
  const m = await mountSale(CheckFollower, { props: { orderId: 'o1', valued } });
  await m.live();
  return m;
}

describe('CheckFollower', () => {
  it('follows the check and hands every answer up', async () => {
    const m = await setup();
    expect(m.params('sale.order.get')).toEqual([{ order_id: 'o1' }]);
    const check = order({ lines: [] });
    await m.result('sale.order.get', check);
    expect(m.wrapper.emitted('order')).toEqual([[check]]);
  });

  it('values it on the server only while it has lines, and hands the preview up', async () => {
    const m = await setup();
    await m.result('sale.order.get', order({ lines: [] }));
    await m.reopen();
    expect(m.params('sale.checkout.preview')).toEqual([]);
    await m.wrapper.setProps({ valued: true });
    await m.reopen();
    expect(m.params('sale.checkout.preview')).toEqual([{ order_id: 'o1' }]);
    const valued = preview();
    await m.result('sale.checkout.preview', valued);
    expect(m.wrapper.emitted('preview')?.at(-1)).toEqual([valued]);
  });

  it('a check that no longer exists is said', async () => {
    const m = await setup();
    m.net.lastStream().push(errorFrame(m.subId('sale.order.get'), 'not_found'));
    await m.reopen();
    expect(m.wrapper.emitted('gone')).toHaveLength(1);
  });

  it('a check that cannot be valued leaves the total unknown', async () => {
    const m = await setup(true);
    await m.result('sale.order.get', order());
    await m.reopen();
    await m.result('sale.checkout.preview', preview());
    m.net.lastStream().push(errorFrame(m.subId('sale.checkout.preview'), 'sale.tax_category_missing'));
    await m.reopen();
    expect(m.wrapper.emitted('preview')?.at(-1)).toEqual([undefined]);
  });
});

// The live preview of the check on screen (`sale.checkout.preview` of all of it): what the cart paints
// as Total and the FAB carries. Renderless; mounted only while the check has lines. An error leaves the
// total unknown (never a number of the screen's own).
import { describe, expect, it } from 'vitest';

import { errorFrame, mountSale } from '../../__tests__/mount-sale';
import { preview } from './__tests__/fixtures';
import PreviewFollower from './PreviewFollower.vue';

describe('PreviewFollower', () => {
  it('values the whole check and hands the answer up; an error hands nothing', async () => {
    const m = await mountSale(PreviewFollower, { props: { orderId: 'o1' } });
    await m.live();
    expect(m.params('sale.checkout.preview')).toEqual([{ order_id: 'o1' }]);
    const valued = preview();
    await m.result('sale.checkout.preview', valued);
    expect(m.wrapper.emitted('preview')?.at(-1)).toEqual([valued]);
    m.net.lastStream().push(errorFrame(m.subId('sale.checkout.preview'), 'sale.order_changed'));
    await m.reopen();
    expect(m.wrapper.emitted('preview')?.at(-1)).toEqual([undefined]);
  });

  it('says the preview is gone when it is let go', async () => {
    const m = await mountSale(PreviewFollower, { props: { orderId: 'o1' } });
    m.wrapper.unmount();
    expect(m.wrapper.emitted('preview')?.at(-1)).toEqual([undefined]);
  });
});

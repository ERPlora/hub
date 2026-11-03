// One product of Inventory followed live (`inventory.product.get`): the till's notice of a refused tap
// goes the moment the product can be sold again (SALE-F07). Renderless; mounted only while that notice is up.
import { RELEASE_GRACE_MS } from '@erplora/ui/sdk';
import { describe, expect, it } from 'vitest';

import { errorFrame, mountSale } from '../../__tests__/mount-sale';
import { product } from './__tests__/fixtures';
import ProductFollower from './ProductFollower.vue';

const GET = 'inventory.product.get';

describe('ProductFollower', () => {
  it('follows the product by its id and hands every answer up', async () => {
    const m = await mountSale(ProductFollower, { props: { productId: 'p1' } });
    await m.live();
    expect(m.params(GET)).toEqual([{ id: 'p1' }]);
    const soldOut = product({ id: 'p1', is_sold_out: true });
    await m.result(GET, soldOut);
    expect(m.wrapper.emitted('product')).toEqual([[soldOut]]);
    const onSale = product({ id: 'p1', is_sold_out: false });
    await m.result(GET, onSale, {}, 2);
    expect(m.wrapper.emitted('product')).toEqual([[soldOut], [onSale]]);
  });

  it('an error hands nothing up: what the till last knew stays', async () => {
    const m = await mountSale(ProductFollower, { props: { productId: 'p1' } });
    await m.live();
    m.net.lastStream().push(errorFrame(m.subId(GET), 'permission_denied'));
    await m.reopen();
    expect(m.wrapper.emitted('product')).toBeUndefined();
  });

  it('lets the product go when it is let go', async () => {
    const m = await mountSale(ProductFollower, { props: { productId: 'p1' } });
    await m.live();
    m.wrapper.unmount();
    await m.clock.advance(RELEASE_GRACE_MS);
    expect(m.params(GET)).toEqual([]);
  });
});

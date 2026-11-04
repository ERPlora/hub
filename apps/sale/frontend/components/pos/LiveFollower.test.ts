// One record followed live by its id and handed up on every answer: the till's notice of a refused tap goes the moment
// the record can be sold (SALE-F07, SALE-F38). Renderless; mounted only while that notice is up. The same for what the
// till follows: a product of Inventory and a service of Services.
import { RELEASE_GRACE_MS } from '@erplora/ui/sdk';
import { describe, expect, it } from 'vitest';

import { errorFrame, mountSale } from '../../__tests__/mount-sale';
import { product, service } from './__tests__/fixtures';
import LiveFollower from './LiveFollower.vue';
import type { FollowedRead } from './till';

describe.each<{ op: FollowedRead; id: string; refused: object; sellable: object }>([
  {
    op: 'inventory.product.get',
    id: 'p1',
    refused: product({ id: 'p1', is_sold_out: true }),
    sellable: product({ id: 'p1', is_sold_out: false }),
  },
  {
    op: 'service.service.get',
    id: 'sv1',
    refused: service({ id: 'sv1', needs_tax_setup: true }),
    sellable: service({ id: 'sv1', needs_tax_setup: false }),
  },
])('LiveFollower of $op', ({ op, id, refused, sellable }) => {
  async function followed() {
    const m = await mountSale(LiveFollower, { props: { op, id } });
    await m.live();
    return m;
  }

  it('follows the record by its id and hands every answer up', async () => {
    const m = await followed();
    expect(m.params(op)).toEqual([{ id }]);
    await m.result(op, refused);
    expect(m.wrapper.emitted('answer')).toEqual([[refused]]);
    await m.result(op, sellable, {}, 2);
    expect(m.wrapper.emitted('answer')).toEqual([[refused], [sellable]]);
  });

  it('an error hands nothing up: what the till last knew stays', async () => {
    const m = await followed();
    m.net.lastStream().push(errorFrame(m.subId(op), 'permission_denied'));
    await m.reopen();
    expect(m.wrapper.emitted('answer')).toBeUndefined();
  });

  it('lets the record go when it is let go', async () => {
    const m = await followed();
    m.wrapper.unmount();
    await m.clock.advance(RELEASE_GRACE_MS);
    expect(m.params(op)).toEqual([]);
  });
});

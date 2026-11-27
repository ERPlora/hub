// The services' tiles of the till's grid: the offered services 100 at a time, a tile each, «Load more» while there are
// more and the error with «Retry». Inside «All» (other tiles around them) they say nothing while loading or when there
// are none; alone («Services») they show a spinner and «No services.». The total goes up for the chips.
import { describe, expect, it } from 'vitest';

import { click, errorFrame, mountSale } from '../../__tests__/mount-sale';
import { page, service } from './__tests__/fixtures';
import ServiceTiles from './ServiceTiles.vue';

const OP = 'service.service.list_for_sale';

async function setup(props: Record<string, unknown> = {}) {
  const m = await mountSale(ServiceTiles, { props });
  await m.live();
  return m;
}

describe('ServiceTiles', () => {
  it('paints a tile per offered service and hands the total up', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ limit: 100, offset: 0 }]);
    await s.result(OP, page([service({ id: 'sv1' }), service({ id: 'sv2', name: 'Colour' })], 2));
    expect(s.find('pos-service-sv1').exists()).toBe(true);
    expect(s.find('pos-service-sv2').exists()).toBe(true);
    expect(s.wrapper.emitted('total')?.at(-1)).toEqual([2]);
  });

  it('among other tiles: nothing while loading and nothing when there are none', async () => {
    const s = await setup();
    expect(s.find('pos-services-loading').exists()).toBe(false);
    await s.result(OP, page([]));
    expect(s.find('pos-services-empty').exists()).toBe(false);
  });

  it('alone: a spinner until the first answer, then «No services.» when there are none', async () => {
    const s = await setup({ alone: true });
    expect(s.find('pos-services-loading').exists()).toBe(true);
    await s.result(OP, page([]));
    expect(s.find('pos-services-empty').text()).toBe('No services.');
  });

  it('a failed read says so with «Retry», among other tiles too', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'internal_error'));
    await s.reopen();
    expect(s.find('pos-services-error').text()).toContain('The services could not be loaded.');
    expect(s.find('pos-services-retry').exists()).toBe(true);
  });

  it('«Load more» asks the next 100; a tap hands the service up', async () => {
    const s = await setup();
    await s.result(OP, page([service()], 150));
    await click(s.find('pos-services-more').element);
    await s.reopen();
    expect(s.params(OP)).toEqual([
      { limit: 100, offset: 0 },
      { limit: 100, offset: 100 },
    ]);
    await click(s.find('pos-service-sv1').element);
    expect(s.wrapper.emitted('pick')).toEqual([[service()]]);
  });
});

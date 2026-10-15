// The till's grid of services (SALE-F38): Services' offered services 100 at a time (`service.service.
// list_for_sale`, live), a tile each, «Load more» while there are more, «No services.» when there are
// none, a spinner until the first answer and the error with «Retry». It hands its total up for the chip.
import { describe, expect, it } from 'vitest';

import { click, errorFrame, mountSale } from '../../__tests__/mount-sale';
import { page, service } from './__tests__/fixtures';
import ServiceGrid from './ServiceGrid.vue';

const OP = 'service.service.list_for_sale';

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountSale(ServiceGrid, { locale });
  await m.live();
  return m;
}

describe('ServiceGrid', () => {
  it('follows the first 100 offered services and paints a tile each; the total goes up', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ limit: 100, offset: 0 }]);
    expect(s.find('pos-services-loading').exists()).toBe(true);
    await s.result(OP, page([service({ id: 'sv1' }), service({ id: 'sv2', name: 'Color' })], 2));
    expect(s.find('pos-service-sv1').exists()).toBe(true);
    expect(s.find('pos-service-sv2').exists()).toBe(true);
    expect(s.wrapper.emitted('total')?.at(-1)).toEqual([2]);
  });

  it('«Load more» asks the next 100 as one more window', async () => {
    const s = await setup();
    await s.result(OP, page([service()], 230));
    await click(s.find('pos-services-more').element);
    await s.reopen();
    expect(s.params(OP)).toEqual([
      { limit: 100, offset: 0 },
      { limit: 100, offset: 100 },
    ]);
  });

  it('says when there is no service', async () => {
    const s = await setup('es');
    await s.result(OP, page([]));
    expect(s.find('pos-services-empty').text()).toBe('Sin servicios.');
  });

  it('a failed read says so with «Retry»', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'internal_error'));
    await s.reopen();
    expect(s.find('pos-services-error').text()).toContain('The services could not be loaded.');
    expect(s.find('pos-services-retry').exists()).toBe(true);
  });

  it('a tap hands the service up', async () => {
    const s = await setup();
    await s.result(OP, page([service()]));
    await click(s.find('pos-service-sv1').element);
    expect(s.wrapper.emitted('pick')).toEqual([[service()]]);
  });
});

// The till's «Services» grid (SALE-F38): the services' tiles alone in the grid (their own behaviour, in
// ServiceTiles.test.ts), with their spinner and «No services.»; the total and a tap go up to the till.
import { describe, expect, it } from 'vitest';

import { click, mountSale } from '../../__tests__/mount-sale';
import { page, service } from './__tests__/fixtures';
import ServiceGrid from './ServiceGrid.vue';

const OP = 'service.service.list_for_sale';

describe('ServiceGrid', () => {
  it('holds the services alone in the grid: spinner, tiles and «No services.»; the total and a tap go up', async () => {
    const s = await mountSale(ServiceGrid, { locale: 'es' });
    await s.live();
    expect(s.find('pos-services-loading').exists()).toBe(true);
    await s.result(OP, page([service({ id: 'sv1' })], 1));
    expect(s.wrapper.find('.pos-grid [data-testid="pos-service-sv1"]').exists()).toBe(true);
    expect(s.wrapper.emitted('total')?.at(-1)).toEqual([1]);
    await click(s.find('pos-service-sv1').element);
    expect(s.wrapper.emitted('pick')).toEqual([[service({ id: 'sv1' })]]);
    await s.result(OP, page([]), {}, 2);
    expect(s.find('pos-services-empty').text()).toBe('Sin servicios.');
  });
});

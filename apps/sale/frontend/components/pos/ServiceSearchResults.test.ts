// The services the till's search finds (SALE-F38): Services' offered services whose name holds what is
// typed, 20 at a time, under «Services»; a row says the duration (or why it cannot be sold) and the
// price, and a tap hands the service up. Nothing found: nothing painted.
import { describe, expect, it } from 'vitest';

import { click, mountSale, taxSettings } from '../../__tests__/mount-sale';
import { plain } from '../../lib/format';
import { page, service } from './__tests__/fixtures';
import ServiceSearchResults from './ServiceSearchResults.vue';

const OP = 'service.service.list_for_sale';

async function setup(term = 'cor') {
  const m = await mountSale(ServiceSearchResults, { props: { term }, locale: 'es' });
  await m.live();
  return m;
}

describe('ServiceSearchResults', () => {
  it('asks Services for what is typed, 20 at a time', async () => {
    const m = await setup();
    expect(m.params(OP)).toEqual([{ search: 'cor', limit: 20, offset: 0 }]);
  });

  it('lists each service with its duration and price under «Services»; a tap hands it up', async () => {
    const m = await setup();
    const cut = service({ id: 'sv1', name: 'Corte', duration_minutes: 30, price: 1800 });
    await m.result(OP, page([cut]));
    expect(m.find('pos-search-services-title').text()).toBe('Servicios');
    const row = m.find('pos-search-service-sv1');
    expect(row.find('p').text()).toBe('30 min');
    expect(plain(row.find('.pos-search__price').text())).toBe('18,00 €');
    await click(row.element);
    expect(m.wrapper.emitted('pick')).toEqual([[cut]]);
  });

  it('a service without VAT says why and still takes the tap', async () => {
    const m = await setup();
    await m.result(OP, page([service({ id: 'sv2', needs_tax_setup: true })]));
    const row = m.find('pos-search-service-sv2');
    expect(row.attributes('aria-disabled')).toBe('true');
    expect(row.find('p').text()).toBe('No se puede vender: sin categoría fiscal. Falta configurar el IVA.');
  });

  it('in the Canary Islands a service without its tax names the IGIC', async () => {
    const m = await setup();
    await m.result('tax.settings.get', taxSettings('igic'));
    await m.result(OP, page([service({ id: 'sv2', needs_tax_setup: true })]));
    expect(m.find('pos-search-service-sv2').find('p').text()).toBe('No se puede vender: sin categoría fiscal. Falta configurar el IGIC.');
  });

  it('nothing found paints nothing', async () => {
    const m = await setup();
    await m.result(OP, page([]));
    expect(m.find('pos-search-services-title').exists()).toBe(false);
  });
});

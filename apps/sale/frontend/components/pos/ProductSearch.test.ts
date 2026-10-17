// The till's product search (WORKBOOK «Vender»: the magnifier opens «Search product…», by name or SKU,
// on the server, across the whole catalogue whatever the category): a floating panel over the grid
// with the live answer; a tap adds the product (the page applies the same rules as a tile).
import { describe, expect, it } from 'vitest';

import { click, errorFrame, ionValue, mountSale } from '../../__tests__/mount-sale';
import { plain } from '../../lib/format';
import { page, product, service } from './__tests__/fixtures';
import ProductSearch from './ProductSearch.vue';

const OP = 'inventory.product.list';

async function setup(locale: 'en' | 'es' = 'en', props: Record<string, unknown> = {}) {
  const m = await mountSale(ProductSearch, { locale, props });
  await m.live();
  return m;
}

describe('ProductSearch', () => {
  it('asks the server for the active articles by name, 20 at a time, and asks again with what is typed', async () => {
    const m = await setup();
    expect(m.params(OP)).toEqual([{ search: '', is_active: true, sort: 'name', limit: 20, offset: 0 }]);
    expect((m.wrapper.find('ion-searchbar').element as unknown as { placeholder?: string }).placeholder).toBe('Search product…');
    await ionValue(m.wrapper.find('ion-searchbar').element, ' caf ', 'ionInput');
    await m.reopen();
    expect(m.params(OP)).toEqual([{ search: 'caf', is_active: true, sort: 'name', limit: 20, offset: 0 }]);
  });

  it('lists each match with its name, SKU and price; a tap hands it up', async () => {
    const m = await setup('es');
    const coffee = product({ id: 'p1', name: 'Café', sku: 'CAF-1', price: 150 });
    await m.result(OP, page([coffee]));
    const row = m.find('pos-search-p1');
    expect(row.find('h3').text()).toBe('Café');
    expect(row.find('p').text()).toBe('CAF-1');
    expect(plain(row.find('.pos-search__price').text())).toBe('1,50 €');
    await click(row.element);
    expect(m.wrapper.emitted('pick')).toEqual([[coffee]]);
  });

  it('a match without VAT says why instead of its SKU and still takes the tap', async () => {
    const m = await setup();
    const blocked = product({ id: 'p2', name: 'Tea', needs_tax_setup: true });
    await m.result(OP, page([blocked]));
    const row = m.find('pos-search-p2');
    expect(row.attributes('aria-disabled')).toBe('true');
    expect(row.find('p').text()).toBe('Cannot be sold: no tax category. VAT needs to be set up.');
    await click(row.element);
    expect(m.wrapper.emitted('pick')).toEqual([[blocked]]);
  });

  it('in Ceuta or Melilla a match without its tax names the IPSI', async () => {
    const m = await setup();
    await m.result('sale.sale.tax_kind', { tax: 'ipsi' });
    await m.result(OP, page([product({ id: 'p2', name: 'Tea', needs_tax_setup: true })]));
    expect(m.find('pos-search-p2').find('p').text()).toBe('Cannot be sold: no tax category. IPSI needs to be set up.');
  });

  it('says «No products.» when nothing matches and the error when the catalogue cannot be read', async () => {
    const m = await setup();
    await m.result(OP, page([]));
    expect(m.find('pos-search-empty').text()).toBe('No products.');
    m.net.lastStream().push(errorFrame(m.subId(OP), 'app_inactive'));
    await m.reopen();
    expect(m.find('pos-search-error').text()).toBe('msg app_inactive');
  });

  it('closes with its button and with Escape', async () => {
    const m = await setup();
    await click(m.find('pos-search-close').element);
    m.find('pos-search').element.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(m.wrapper.emitted('close')).toHaveLength(2);
    expect(m.find('pos-search-close').attributes('aria-label')).toBe('Close the search');
  });
});

describe('ProductSearch: the services of Services (SALE-F38)', () => {
  const SERVICES = 'service.service.list_for_sale';

  it('with services, it asks Services too with what is typed and lists them under «Services»', async () => {
    const m = await setup('es', { withServices: true });
    expect(m.params(SERVICES)).toEqual([{ search: '', limit: 20, offset: 0 }]);
    await ionValue(m.wrapper.find('ion-searchbar').element, ' cor ', 'ionInput');
    await m.reopen();
    expect(m.params(SERVICES)).toEqual([{ search: 'cor', limit: 20, offset: 0 }]);
    const cut = service({ id: 'sv1', name: 'Corte de pelo', price: 2500 });
    await m.result(SERVICES, page([cut]));
    expect(m.find('pos-search-services-title').text()).toBe('Servicios');
    const row = m.find('pos-search-service-sv1');
    expect(row.find('h3').text()).toBe('Corte de pelo');
    expect(plain(row.find('.pos-search__price').text())).toBe('25,00 €');
    await click(row.element);
    expect(m.wrapper.emitted('pickService')).toEqual([[cut]]);
  });

  it('without services, Services is not asked', async () => {
    const m = await setup();
    expect(m.params(SERVICES)).toEqual([]);
  });
});

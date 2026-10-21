// The till's catalogue column (WORKBOOK «Vender»; SALE-F01 step 1, F07): Inventory's categories with
// their counts, the magnifier, the ⋮ screen menu, the notices and the grid, which asks its articles 100
// at a time per category (more = one more window, never a bigger `limit`) and searches on the server.
// A sellable tap is handed up; a blocked one says why and adds nothing; Inventory off is explained and
// the open price stays.
import { toast } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { click, errorFrame, mountSale, taxSettings } from '../../__tests__/mount-sale';
import { category, page, product, service } from './__tests__/fixtures';
import CategoryStrip from './CategoryStrip.vue';
import PosCatalog from './PosCatalog.vue';
import ProductGrid from './ProductGrid.vue';
import ProductSearch from './ProductSearch.vue';
import ServiceGrid from './ServiceGrid.vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toast: vi.fn(() => Promise.resolve()),
}));

afterEach(() => vi.mocked(toast).mockClear());

const PRODUCTS = 'inventory.product.list';
const CATEGORIES = 'inventory.category.list';
// The grid shows what is sold out too, greyed (SALE-F07): the count of «All» is what is on sale.
const GRID = { is_active: true, include_sold_out: true, sort: 'name' };

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountSale(PosCatalog, { props: { showProducts: true, canOpenPrice: true, ...props }, locale });
  await m.live();
  const grid = () => m.wrapper.findComponent(ProductGrid);
  const gridParams = () => m.params(PRODUCTS).filter((p) => p.sort === 'name');
  return { ...m, grid, gridParams };
}

describe('PosCatalog: what it asks', () => {
  it('follows the categories by name, the count of «All» and the first 100 articles of every category', async () => {
    const s = await setup();
    expect(s.params(CATEGORIES)).toEqual([{ sort: 'name', limit: 100, offset: 0 }]);
    expect(s.params(PRODUCTS)).toEqual(
      expect.arrayContaining([
        { is_active: true, limit: 1, offset: 0 },
        { ...GRID, limit: 100, offset: 0 },
      ]),
    );
  });

  it('a category asks its own articles; «Load more» asks the next 100 as one more subscription', async () => {
    const s = await setup();
    await s.result(CATEGORIES, page([category({ id: 'c1' })]));
    s.wrapper.findComponent(CategoryStrip).vm.$emit('update:modelValue', 'c1');
    await s.reopen();
    expect(s.gridParams()).toEqual([{ ...GRID, category_id: 'c1', limit: 100, offset: 0 }]);
    await s.result(PRODUCTS, page([product()], 250), { category_id: 'c1' });
    expect(s.grid().props('hasMore')).toBe(true);
    s.grid().vm.$emit('loadMore');
    await s.reopen();
    expect(s.gridParams()).toEqual([
      { ...GRID, category_id: 'c1', limit: 100, offset: 0 },
      { ...GRID, category_id: 'c1', limit: 100, offset: 100 },
    ]);
    expect(s.gridParams().every((p) => (p.limit as number) <= 100)).toBe(true);
  });

  it('paints the counts and the products the server answers', async () => {
    const s = await setup();
    await s.result(CATEGORIES, page([category({ id: 'c1', name: 'Drinks' })]));
    await s.result(PRODUCTS, page([], 7, 1), { limit: 1, needs_tax_setup: undefined });
    await s.result(PRODUCTS, page([product({ id: 'p1' }), product({ id: 'p2' })]), { sort: 'name' });
    expect(s.wrapper.findComponent(CategoryStrip).props('allCount')).toBe(7);
    expect(s.find('pos-category-c1').exists()).toBe(true);
    expect(s.find('pos-product-p1').exists()).toBe(true);
    expect(s.find('pos-product-p2').exists()).toBe(true);
  });
});

describe('PosCatalog: taps', () => {
  it('hands a sellable article up', async () => {
    const s = await setup();
    const coffee = product({ id: 'p1' });
    await s.result(PRODUCTS, page([coffee]), { sort: 'name' });
    await click(s.find('pos-product-p1').element);
    expect(s.wrapper.emitted('add')).toEqual([[coffee]]);
  });

  it('a blocked article adds nothing: the reason goes above the grid and in a warning toast', async () => {
    const s = await setup({}, 'es');
    await s.result(PRODUCTS, page([product({ id: 'p1', needs_tax_setup: true })]), { sort: 'name' });
    await click(s.find('pos-product-p1').element);
    expect(s.wrapper.emitted('add')).toBeUndefined();
    const reason = 'No se puede vender: sin categoría fiscal. Falta configurar el IVA.';
    expect(s.find('pos-tap-notice').text()).toBe(reason);
    expect(toast).toHaveBeenCalledExactlyOnceWith(reason, 'warning');
  });

  it('in the Canary Islands the reason of a blocked tap names the IGIC', async () => {
    const s = await setup({}, 'es');
    await s.result('tax.settings.get', taxSettings('igic'));
    await s.result(PRODUCTS, page([product({ id: 'p1', needs_tax_setup: true })]), { sort: 'name' });
    await click(s.find('pos-product-p1').element);
    const reason = 'No se puede vender: sin categoría fiscal. Falta configurar el IGIC.';
    expect(s.find('pos-tap-notice').text()).toBe(reason);
    expect(toast).toHaveBeenCalledExactlyOnceWith(reason, 'warning');
  });

  it('a sold-out article adds nothing: «… is sold out.» goes above the grid and in a warning toast', async () => {
    const s = await setup({}, 'es');
    await s.result(PRODUCTS, page([product({ id: 'p1', name: 'Croquetas', is_sold_out: true })]), { sort: 'name' });
    await click(s.find('pos-product-p1').element);
    expect(s.wrapper.emitted('add')).toBeUndefined();
    const reason = '«Croquetas» está agotado.';
    expect(s.find('pos-tap-notice').text()).toBe(reason);
    expect(toast).toHaveBeenCalledExactlyOnceWith(reason, 'warning');
  });

  it('the next sellable tap clears that notice', async () => {
    const s = await setup();
    await s.result(PRODUCTS, page([product({ id: 'p1', needs_tax_setup: true }), product({ id: 'p2' })]), { sort: 'name' });
    await click(s.find('pos-product-p1').element);
    await click(s.find('pos-product-p2').element);
    expect(s.find('pos-tap-notice').exists()).toBe(false);
  });

  it('the open-price tile is handed up', async () => {
    const s = await setup();
    await click(s.find('pos-open-price-tile').element);
    expect(s.wrapper.emitted('openPrice')).toHaveLength(1);
  });
});

describe('PosCatalog: search', () => {
  it('the magnifier opens the search; a pick there is a tap on the product and closes it', async () => {
    const s = await setup();
    const trigger = s.find('pos-search-trigger');
    expect(trigger.attributes('aria-label')).toBe('Search');
    expect(s.wrapper.findComponent(ProductSearch).exists()).toBe(false);
    await click(trigger.element);
    expect(trigger.attributes('aria-pressed')).toBe('true');
    const coffee = product({ id: 'p9' });
    s.wrapper.findComponent(ProductSearch).vm.$emit('pick', coffee);
    await s.reopen();
    expect(s.wrapper.emitted('add')).toEqual([[coffee]]);
    expect(s.wrapper.findComponent(ProductSearch).exists()).toBe(false);
  });
});

describe('PosCatalog: states', () => {
  it('Inventory off: the grid says so and the open price stays', async () => {
    const s = await setup({}, 'es');
    s.net.lastStream().push(errorFrame(s.subId(PRODUCTS, { sort: 'name' }), 'app_inactive'));
    await s.reopen();
    expect(s.find('pos-grid-empty').text()).toBe(
      'Inventario no está activa, así que no hay rejilla de productos. Puedes cobrar ventas a precio libre; actívala desde Aplicaciones para vender desde un catálogo.',
    );
    expect(s.find('pos-open-price-tile').exists()).toBe(true);
    expect(s.find('pos-catalog-error').exists()).toBe(false);
  });

  it('a catalogue that does not load says it with «Retry»; the open price stays', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(PRODUCTS, { sort: 'name' }), 'internal_error'));
    await s.reopen();
    expect(s.find('pos-catalog-error').text()).toContain('The catalogue could not be loaded.');
    const streams = s.net.streams.length;
    await click(s.find('pos-catalog-retry').element);
    await s.reopen();
    expect(s.net.streams.length).toBeGreaterThan(streams);
    expect(s.find('pos-open-price-tile').exists()).toBe(true);
  });

  it('with products hidden by the settings only the open price is offered', async () => {
    const s = await setup({ showProducts: false });
    expect(s.wrapper.findComponent(CategoryStrip).exists()).toBe(false);
    expect(s.find('pos-search-trigger').exists()).toBe(false);
    await s.result(PRODUCTS, page([product({ id: 'p1' })]), { sort: 'name' });
    expect(s.find('pos-product-p1').exists()).toBe(false);
    expect(s.find('pos-open-price-tile').exists()).toBe(true);
  });
});

describe('PosCatalog: the services of Services (SALE-F38)', () => {
  const SERVICES = 'service.service.list_for_sale';
  /** `v-show`: the services' grid stays mounted (its count feeds the chip) and hides with display:none. */
  const shownGrid = (s: Awaited<ReturnType<typeof setup>>) =>
    !(s.wrapper.findComponent(ServiceGrid).attributes('style') ?? '').includes('display: none');

  it('without services nothing of Services is asked nor shown', async () => {
    const s = await setup();
    expect(s.params(SERVICES)).toEqual([]);
    expect(s.find('pos-category-services').exists()).toBe(false);
    expect(s.wrapper.findComponent(ServiceGrid).exists()).toBe(false);
  });

  it('with services, the «Services» chip carries their count and shows their grid instead of the products', async () => {
    const s = await setup({ showServices: true });
    expect(s.params(SERVICES)).toEqual([{ limit: 100, offset: 0 }]);
    await s.result(SERVICES, page([service({ id: 'sv1' }), service({ id: 'sv2', name: 'Color' })], 2));
    const strip = s.wrapper.findComponent(CategoryStrip);
    expect(strip.props()).toMatchObject({ withServices: true, servicesCount: 2 });
    expect(shownGrid(s)).toBe(false);
    expect(s.grid().exists()).toBe(true);
    strip.vm.$emit('update:modelValue', 'services');
    await s.reopen();
    expect(shownGrid(s)).toBe(true);
    expect(s.grid().exists()).toBe(false);
    expect(s.find('pos-service-sv2').exists()).toBe(true);
  });

  it('a sellable service is handed up; one without VAT says why and adds nothing', async () => {
    const s = await setup({ showServices: true }, 'es');
    await s.result(SERVICES, page([service({ id: 'sv1' }), service({ id: 'sv2', needs_tax_setup: true })]));
    s.wrapper.findComponent(CategoryStrip).vm.$emit('update:modelValue', 'services');
    await s.reopen();
    await click(s.find('pos-service-sv1').element);
    expect(s.wrapper.emitted('service')).toEqual([[service({ id: 'sv1' })]]);
    await click(s.find('pos-service-sv2').element);
    expect(s.wrapper.emitted('service')).toHaveLength(1);
    expect(s.find('pos-tap-notice').text()).toBe('No se puede vender: sin categoría fiscal. Falta configurar el IVA.');
  });

  it('with products hidden, the services come first and «All» keeps the open price', async () => {
    const s = await setup({ showProducts: false, showServices: true });
    await s.result(SERVICES, page([service()]));
    expect(shownGrid(s)).toBe(true);
    expect(s.find('pos-search-trigger').exists()).toBe(false);
    s.wrapper.findComponent(CategoryStrip).vm.$emit('update:modelValue', '');
    await s.reopen();
    expect(s.find('pos-open-price-tile').exists()).toBe(true);
  });

  it('the search looks for services too, and a service found is handed up', async () => {
    const s = await setup({ showServices: true });
    await click(s.find('pos-search-trigger').element);
    expect(s.wrapper.findComponent(ProductSearch).props('withServices')).toBe(true);
    s.wrapper.findComponent(ProductSearch).vm.$emit('pickService', service({ id: 'sv7' }));
    await s.reopen();
    expect(s.wrapper.emitted('service')).toEqual([[service({ id: 'sv7' })]]);
    expect(s.wrapper.findComponent(ProductSearch).exists()).toBe(false);
  });
});

describe('PosCatalog: the menus of Menus (SALE-F12)', () => {
  const MENUS = 'combo.combo.for_sale';
  const MENU = { id: 'm1', name: 'Menu of the day', kitchen_name: '', price: 1350, supply_kind: 'service' as const, sort_order: 0, groups: [] };

  it('without menus nothing of Menus is asked nor shown', async () => {
    const s = await setup();
    expect(s.params(MENUS)).toEqual([]);
  });

  it('with menus, «All» shows them first in the grid, before the products', async () => {
    const s = await setup({ showCombos: true });
    await s.result(MENUS, page([MENU]));
    await s.result(PRODUCTS, page([product()]), GRID);
    const tiles = s.wrapper.findAll('.pos-grid > button').map((tile) => tile.attributes('data-testid'));
    expect(tiles.slice(0, 2)).toEqual(['pos-menu-m1', 'pos-product-p1']);
  });

  it('a category of products leaves the menus out; a menu tapped is handed up', async () => {
    const s = await setup({ showCombos: true });
    await s.result(MENUS, page([MENU]));
    await click(s.find('pos-menu-m1').element);
    expect(s.wrapper.emitted('combo')).toEqual([[MENU]]);
    await s.result(CATEGORIES, page([category({ id: 'c1' })]));
    s.wrapper.findComponent(CategoryStrip).vm.$emit('update:modelValue', 'c1');
    await s.reopen();
    expect(s.find('pos-menu-m1').exists()).toBe(false);
  });
});

describe('PosCatalog: the VeriFactu notice (SALE-F07)', () => {
  it('asks VeriFactu only when the page says it is on and readable', async () => {
    expect((await setup()).params('verifactu.config.get')).toEqual([]);
    expect((await setup({ fiscal: true })).params('verifactu.config.get')).toEqual([{}]);
  });
});

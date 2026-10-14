// The till's catalogue column (WORKBOOK «Vender»; SALE-F01 step 1, F07): Inventory's categories with
// their counts, the magnifier, the ⋮ screen menu, the notices and the grid, which asks its articles 100
// at a time per category (more = one more window, never a bigger `limit`) and searches on the server.
// A sellable tap is handed up; a blocked one says why and adds nothing; Inventory off is explained and
// the open price stays.
import { toast } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { click, errorFrame, mountSale } from '../../__tests__/mount-sale';
import { category, page, product } from './__tests__/fixtures';
import CategoryStrip from './CategoryStrip.vue';
import PosCatalog from './PosCatalog.vue';
import ProductGrid from './ProductGrid.vue';
import ProductSearch from './ProductSearch.vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toast: vi.fn(() => Promise.resolve()),
}));

afterEach(() => vi.mocked(toast).mockClear());

const PRODUCTS = 'inventory.product.list';
const CATEGORIES = 'inventory.category.list';
const GRID = { is_active: true, sort: 'name' };

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountSale(PosCatalog, { props: { showProducts: true, canOpenPrice: true, target: null, ...props }, locale });
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

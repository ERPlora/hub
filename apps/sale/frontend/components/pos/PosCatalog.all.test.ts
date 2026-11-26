// «All», the till's first chip: it shows everything the till sells. With the services of Services they come after the
// menus and before Inventory's articles, and the count of «All» counts both; without Services it shows and counts only
// Inventory's articles.
import { describe, expect, it } from 'vitest';

import { click, mountSale } from '../../__tests__/mount-sale';
import { category, page, product, service } from './__tests__/fixtures';
import CategoryStrip from './CategoryStrip.vue';
import PosCatalog from './PosCatalog.vue';
import ProductGrid from './ProductGrid.vue';

const PRODUCTS = 'inventory.product.list';
const SERVICES = 'service.service.list_for_sale';
const MENUS = 'combo.combo.for_sale';
const CATEGORIES = 'inventory.category.list';
const MENU = { id: 'm1', name: 'Menu of the day', kitchen_name: '', price: 1350, supply_kind: 'service' as const, sort_order: 0, groups: [] };

async function setup(props: Record<string, unknown> = {}) {
  const m = await mountSale(PosCatalog, { props: { showProducts: true, showServices: true, ...props } });
  await m.live();
  const allCount = () => m.wrapper.findComponent(CategoryStrip).props('allCount');
  /** What «All» paints: the grid of articles, with what goes before them. */
  const all = () => m.wrapper.findComponent(ProductGrid);
  const tiles = () => all().findAll('.pos-grid > ion-button.pos-tile').map((tile) => tile.attributes('data-testid'));
  const inAll = (testid: string) => (all().exists() ? all().findAll(`[data-testid="${testid}"]`) : []);
  return { ...m, allCount, tiles, inAll };
}

/** Inventory says how many articles «All» has (its count subscription asks one row of everything active). */
const articles = (s: Awaited<ReturnType<typeof setup>>, total: number) =>
  s.result(PRODUCTS, page([], total, 1), { limit: 1, include_sold_out: true });

describe('PosCatalog: «All» with the services of Services', () => {
  it('shows the services after the menus and before the articles', async () => {
    const s = await setup({ showCombos: true });
    await s.result(MENUS, page([MENU]));
    await s.result(SERVICES, page([service({ id: 'sv1' }), service({ id: 'sv2', name: 'Colour' })]));
    await s.result(PRODUCTS, page([product({ id: 'p1' })]), { sort: 'name' });
    expect(s.tiles().slice(0, 4)).toEqual(['pos-menu-m1', 'pos-service-sv1', 'pos-service-sv2', 'pos-product-p1']);
    expect(s.inAll('pos-service-sv1')).toHaveLength(1);
    expect(s.wrapper.findAll('[data-testid="pos-service-sv1"]')).toHaveLength(1);
  });

  it('counts the articles and the services, once both are known', async () => {
    const s = await setup();
    await articles(s, 5);
    expect(s.allCount()).toBeUndefined();
    await s.result(SERVICES, page([service()], 10));
    expect(s.allCount()).toBe(15);
  });

  it('a service tapped in «All» is handed up', async () => {
    const s = await setup();
    await s.result(SERVICES, page([service({ id: 'sv1' })]));
    await click(s.inAll('pos-service-sv1')[0]!.element);
    expect(s.wrapper.emitted('service')).toEqual([[service({ id: 'sv1' })]]);
  });

  it('a category of articles leaves the services out, and the count of «All» keeps following them', async () => {
    const s = await setup();
    await articles(s, 5);
    await s.result(SERVICES, page([service({ id: 'sv1' })], 1));
    await s.result(CATEGORIES, page([category({ id: 'c1' })]));
    s.wrapper.findComponent(CategoryStrip).vm.$emit('update:modelValue', 'c1');
    await s.reopen();
    expect(s.inAll('pos-service-sv1')).toHaveLength(0);
    await s.result(SERVICES, page([service({ id: 'sv1' }), service({ id: 'sv2' })], 2), {}, 2);
    expect(s.allCount()).toBe(7);
  });

  it('more than 100 services: «Load more» in «All» asks the next 100', async () => {
    const s = await setup();
    await s.result(SERVICES, page([service()], 150));
    await click(s.inAll('pos-services-more')[0]!.element);
    await s.reopen();
    expect(s.params(SERVICES)).toEqual([
      { limit: 100, offset: 0 },
      { limit: 100, offset: 100 },
    ]);
  });

  it('with products hidden, «All» shows the services with the open price and counts only them', async () => {
    const s = await setup({ showProducts: false });
    await s.result(SERVICES, page([service({ id: 'sv1' })], 1));
    s.wrapper.findComponent(CategoryStrip).vm.$emit('update:modelValue', '');
    await s.reopen();
    expect(s.inAll('pos-service-sv1')).toHaveLength(1);
    expect(s.find('pos-open-price-tile').exists()).toBe(true);
    expect(s.allCount()).toBe(1);
  });
});

describe('PosCatalog: «All» without Services', () => {
  it('shows and counts only the articles', async () => {
    const s = await setup({ showServices: false });
    await articles(s, 5);
    await s.result(PRODUCTS, page([product({ id: 'p1' })]), { sort: 'name' });
    expect(s.allCount()).toBe(5);
    expect(s.tiles()[0]).toBe('pos-product-p1');
    expect(s.params(SERVICES)).toEqual([]);
  });
});

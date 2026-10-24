// The till's product grid (WORKBOOK «Vender»): the tiles of the category in use, the «Open price» tile
// always last, «Load more» when the server has more rows than the windows asked, «No products.» (or
// the reason the page passes) when there is nothing, and a spinner until the first answer.
import { describe, expect, it } from 'vitest';

import { click, mountSale } from '../../__tests__/mount-sale';
import { product } from './__tests__/fixtures';
import ProductGrid from './ProductGrid.vue';

const PRODUCTS = [product({ id: 'p1', name: 'Coffee' }), product({ id: 'p2', name: 'Tea' })];

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  return mountSale(ProductGrid, {
    props: { products: PRODUCTS, loading: false, hasMore: false, ...props },
    locale,
  });
}

describe('ProductGrid', () => {
  it('paints a tile per product and the «Open price» tile last', async () => {
    const m = await setup();
    const tiles = m.wrapper.findAll('.pos-grid > [data-testid]').map((tile) => tile.attributes('data-testid'));
    expect(tiles).toEqual(['pos-product-p1', 'pos-product-p2', 'pos-open-price-tile']);
    const open = m.find('pos-open-price-tile');
    expect(open.find('.pos-tile__name').text()).toBe('Open price');
    expect(open.find('.pos-tile__price').text()).toBe('+ €');
  });

  it('hands a picked product up and opens the open price from its tile', async () => {
    const m = await setup();
    await click(m.find('pos-product-p2').element);
    await click(m.find('pos-open-price-tile').element);
    expect(m.wrapper.emitted('pick')).toEqual([[PRODUCTS[1]]]);
    expect(m.wrapper.emitted('openPrice')).toHaveLength(1);
  });

  it('the open-price tile is the same for everyone: a manager approves it when it is added (SALE-F09)', async () => {
    const m = await setup({}, 'es');
    const open = m.find('pos-open-price-tile');
    expect(open.find('.pos-tile__name').text()).toBe('Precio libre');
    expect(open.find('.pos-tile__price').text()).toBe('+ €');
    await click(open.element);
    expect(m.wrapper.emitted('openPrice')).toHaveLength(1);
  });

  it('asks the next window with «Load more» while the server has more', async () => {
    const m = await setup({ hasMore: true });
    const more = m.find('pos-grid-more');
    expect(more.text()).toBe('Load more');
    await click(more.element);
    expect(m.wrapper.emitted('loadMore')).toHaveLength(1);
    expect((await setup()).find('pos-grid-more').exists()).toBe(false);
  });

  it('says «No products.» when there is nothing, or the reason it is given; the open price stays', async () => {
    const empty = await setup({ products: [] }, 'es');
    expect(empty.find('pos-grid-empty').text()).toBe('Sin productos.');
    expect(empty.find('pos-open-price-tile').exists()).toBe(true);
    const reason = await setup({ products: [], emptyText: 'Inventory is not active.' });
    expect(reason.find('pos-grid-empty').text()).toBe('Inventory is not active.');
  });

  it('shows a spinner until the first answer, not «No products.»', async () => {
    const m = await setup({ products: [], loading: true });
    expect(m.find('pos-grid-loading').exists()).toBe(true);
    expect(m.find('pos-grid-empty').exists()).toBe(false);
  });
});

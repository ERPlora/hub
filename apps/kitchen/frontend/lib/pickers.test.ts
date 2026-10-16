// The pickers of the kitchen's forms: products and categories of Inventory (a `requires`), searched on the
// server by their own operations, as the person types (the routing panel, a ticket made by hand).
import { useLiveClient } from '@erplora/ui/sdk';
import { describe, expect, it } from 'vitest';
import { defineComponent, h } from 'vue';

import { mountKitchen, page } from '../__tests__/mount-kitchen';
import { searchCategories, searchProducts } from './pickers';

async function setup() {
  const exposed: { client?: ReturnType<typeof useLiveClient> } = {};
  const Host = defineComponent({
    setup() {
      exposed.client = useLiveClient();
      return () => h('p');
    },
  });
  const m = await mountKitchen(Host);
  return { ...m, client: exposed.client! };
}

describe('pickers', () => {
  it('search the products of the catalogue by name, with their SKU as a hint', async () => {
    const s = await setup();
    s.answerBy({ '/api/inventory/products': [200, page([{ id: 'p1', name: 'Burger', sku: 'BUR' }])] });
    expect(await searchProducts(s.client)('bur')).toEqual([{ id: 'p1', label: 'Burger', hint: 'BUR' }]);
    expect(s.sent()[0]).toMatchObject({ method: 'GET', path: '/api/inventory/products', query: { search: 'bur', limit: '20' } });
  });

  it('search the categories by name', async () => {
    const s = await setup();
    s.answerBy({ '/api/inventory/categories': [200, page([{ id: 'c1', name: 'Drinks' }])] });
    expect(await searchCategories(s.client)('')).toEqual([{ id: 'c1', label: 'Drinks' }]);
    expect(s.sent()[0].query).toEqual({ limit: '20' });
  });
});

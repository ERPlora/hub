// The searches behind the pricing forms' pickers: products and categories of Inventory, services of
// Services and customer groups of Customers, read through their own operations, 20 at a time.
import { describe, expect, it, vi } from 'vitest';

import type { LiveClient } from '@erplora/ui/sdk';

import { searchCategories, searchGroups, searchProducts, searchServices } from './pickers';

const EUR = { currency: 'EUR', decimals: 2 };
const PLN = { currency: 'PLN', decimals: 2 };

function client(answer: unknown) {
  const call = vi.fn(async () => answer);
  return { client: { api: { call } } as unknown as LiveClient, call };
}

describe('pickers', () => {
  it('searches products by name or SKU, with the SKU and the catalog price as hint', async () => {
    const { client: c, call } = client({ rows: [{ id: 'p1', name: 'Shampoo', sku: 'SH-1', price: 1500 }], total: 1 });
    expect(await searchProducts(c, 'es', EUR)(' sham ')).toEqual([{ id: 'p1', label: 'Shampoo', hint: 'SH-1 · 15,00\u00a0€' }]);
    expect(call).toHaveBeenCalledWith('inventory.product.list', { search: 'sham', limit: 20 });
  });

  it('searches services, with their catalog price as hint', async () => {
    const { client: c, call } = client({ rows: [{ id: 's1', name: 'Haircut', price: 1800 }], total: 1 });
    expect(await searchServices(c, 'en', EUR)('')).toEqual([{ id: 's1', label: 'Haircut', hint: '€18.00' }]);
    expect(call).toHaveBeenCalledWith('service.service.list', { limit: 20 });
  });

  it('the catalog price is in the business’s currency: in Poland, zlotys; a bare figure until it answers', async () => {
    const products = client({ rows: [{ id: 'p1', name: 'Shampoo', sku: 'SH-1', price: 1500 }], total: 1 });
    expect(await searchProducts(products.client, 'es', PLN)('')).toEqual([{ id: 'p1', label: 'Shampoo', hint: 'SH-1 · 15,00\u00a0zł' }]);
    const services = client({ rows: [{ id: 's1', name: 'Haircut', price: 1800 }], total: 1 });
    expect(await searchServices(services.client, 'en', PLN)('')).toEqual([{ id: 's1', label: 'Haircut', hint: 'zł\u00a018.00' }]);
    expect(await searchServices(services.client, 'en')('')).toEqual([{ id: 's1', label: 'Haircut', hint: '18.00' }]);
  });

  it('searches the active customer groups and the categories', async () => {
    const groups = client({ rows: [{ id: 'g1', name: 'VIP' }], total: 1 });
    expect(await searchGroups(groups.client)('vi')).toEqual([{ id: 'g1', label: 'VIP' }]);
    expect(groups.call).toHaveBeenCalledWith('customer.group.list', { search: 'vi', is_active: true, limit: 20 });
    const categories = client({ rows: [{ id: 'c1', name: 'Colour' }], total: 1 });
    expect(await searchCategories(categories.client)('col')).toEqual([{ id: 'c1', label: 'Colour' }]);
    expect(categories.call).toHaveBeenCalledWith('inventory.category.list', { search: 'col', limit: 20 });
  });
});

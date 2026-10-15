// The searches behind the modifier forms' pickers (Combo): they ask the server what the person types
// (20 at a time), through the required apps' own operations (Inventory, Taxes), and turn each row into an
// option with what the person reads. A tax category's option is its key, named by its translated name
// and its rate («Product — generic · 21%»); a product's, its id with its SKU as a hint; a category's,
// its id.
import type { LiveClient } from '@erplora/ui/sdk';
import { describe, expect, it, vi } from 'vitest';

import { searchCategories, searchProducts, searchTaxCategories } from './pickers';

function client(rows: unknown[]) {
  const call = vi.fn().mockResolvedValue({ rows, total: rows.length, limit: 20, offset: 0 });
  return { client: { api: { call } } as unknown as LiveClient, call };
}

const t = (key: string) => ({ 'modifier.tax.exempt': 'exempt' })[key] ?? key;

describe('searchTaxCategories', () => {
  it('asks Taxes for the categories by their name and offers each by its name and rate', async () => {
    const { client: c, call } = client([
      { key: 'product.generic', display_name: 'Product — generic', rate_pct: '21.00', operation_class: 'subject' },
      { key: 'service.health', display_name: 'Service — healthcare', rate_pct: '0.00', operation_class: 'exempt' },
      { key: 'bar.new', display_name: 'New', rate_pct: null, operation_class: null },
    ]);
    const options = await searchTaxCategories(c, t, 'en')('prod');
    expect(call).toHaveBeenCalledWith('tax.category.list', { search: 'prod', limit: 20, sort: 'display_name' });
    expect(options).toEqual([
      { id: 'product.generic', label: 'Product — generic · 21%' },
      { id: 'service.health', label: 'Service — healthcare · exempt' },
      { id: 'bar.new', label: 'New' },
    ]);
  });

  it('opening the list asks without a search', async () => {
    const { client: c, call } = client([]);
    await searchTaxCategories(c, t, 'en')('  ');
    expect(call).toHaveBeenCalledWith('tax.category.list', { limit: 20, sort: 'display_name' });
  });
});

describe('searchProducts', () => {
  it('offers the products of Inventory by their name, with their SKU', async () => {
    const { client: c, call } = client([{ id: 'p1', name: 'Burger', sku: 'BUR-01' }]);
    expect(await searchProducts(c)('bur')).toEqual([{ id: 'p1', label: 'Burger', hint: 'BUR-01' }]);
    expect(call).toHaveBeenCalledWith('inventory.product.list', { search: 'bur', limit: 20, sort: 'name' });
  });
});

describe('searchCategories', () => {
  it('offers the categories of Inventory by their name', async () => {
    const { client: c, call } = client([{ id: 'c1', name: 'Mains' }]);
    expect(await searchCategories(c)('ma')).toEqual([{ id: 'c1', label: 'Mains' }]);
    expect(call).toHaveBeenCalledWith('inventory.category.list', { search: 'ma', limit: 20 });
  });
});

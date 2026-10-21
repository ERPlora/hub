// The searches behind the combo pickers (Combo of @erplora/ui): they ask the server for what the person
// types (20 at a time) and turn each row into an option. A choice is an active product of Inventory, by
// id, named with its SKU and its price; a menu's VAT category is a Taxes key, named by its name and rate.
import type { LiveClient } from '@erplora/ui/sdk';
import { describe, expect, it, vi } from 'vitest';

import { searchProducts, searchTaxCategories } from './pickers';

function client(rows: unknown[]) {
  const call = vi.fn().mockResolvedValue({ rows, total: rows.length, limit: 20, offset: 0 });
  return { client: { api: { call } } as unknown as LiveClient, call };
}

const plain = (text: string) => text.replace(/[  ]/g, ' ');

describe('searchProducts', () => {
  it('asks Inventory for its active products and offers each by id, with its SKU and price', async () => {
    const portion = { unit: 'ud', pricing_unit: 'ud', price_quantity: '1.000' };
    const { client: c, call } = client([
      { id: 'p1', name: 'Hake', sku: 'HAK', price: 1400, ...portion },
      // Sold by weight, or priced per 100: the server refuses them, so they are not offered.
      { id: 'p2', name: 'Ham', sku: 'HAM', price: 3000, unit: 'kg', pricing_unit: 'kg', price_quantity: '1.000' },
      { id: 'p3', name: 'Napkins', sku: 'NAP', price: 37, unit: 'ud', pricing_unit: 'ud', price_quantity: '100.000' },
    ]);
    const options = await searchProducts(c, 'es')('hak');
    // A sold-out article is still a choice to configure (INVENTORY-F29): only the till hides it.
    expect(call).toHaveBeenCalledWith('inventory.product.list', { search: 'hak', is_active: true, include_sold_out: true, limit: 20 });
    expect(options.map((o) => ({ ...o, hint: plain(o.hint ?? '') }))).toEqual([{ id: 'p1', label: 'Hake', hint: 'HAK · 14,00 €' }]);
  });

  it('opening the list asks without a search', async () => {
    const { client: c, call } = client([]);
    await searchProducts(c, 'en')('  ');
    expect(call).toHaveBeenCalledWith('inventory.product.list', { is_active: true, include_sold_out: true, limit: 20 });
  });
});

describe('searchTaxCategories', () => {
  it('asks Taxes for the categories and offers each by its key, name and rate', async () => {
    const { client: c, call } = client([
      { key: 'restaurant.food', display_name: 'Restaurant — food', rate_pct: '10.00', operation_class: 'subject' },
      { key: 'own.new', display_name: 'New', rate_pct: null, operation_class: null },
    ]);
    const options = await searchTaxCategories(c, 'en')('rest');
    expect(call).toHaveBeenCalledWith('tax.category.list', { search: 'rest', limit: 20, sort: 'display_name' });
    expect(options).toEqual([
      { id: 'restaurant.food', label: 'Restaurant — food · 10%' },
      { id: 'own.new', label: 'New' },
    ]);
  });
});

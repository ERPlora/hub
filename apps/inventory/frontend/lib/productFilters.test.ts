// The filters of Products as the table's funnel holds them (by name, as typed) and as
// `inventory.product.list` takes them: price in cents (typed in euros), stock as an exact quantity.
// flow: ninguno — FIX DataTable parte 2b-2 (PLAN-MIGRATIONS §13: filtros como en la vieja)
import { describe, expect, it } from 'vitest';

import { filterParams, filtersInUse, PRODUCT_STATUSES, unreadableEnds } from './productFilters';

describe('productFilters', () => {
  it('sends name and SKU trimmed, the price in cents and the stock exact', () => {
    expect(filterParams({ name: ' caf ', sku: 'CAF', price_min: '12', price_max: '2,20', stock_min: '1,5', stock_max: '10', status: 'needs_tax_setup' })).toEqual({
      name: 'caf',
      sku: 'CAF',
      price_min: 1200,
      price_max: 220,
      stock_min: '1.5',
      stock_max: '10',
      status: 'needs_tax_setup',
    });
  });

  it('«from 12» is twelve euros, never twelve cents (inventory#115)', () => {
    expect(filterParams({ price_min: '12' })).toEqual({ price_min: 1200 });
    expect(filterParams({ price_max: '1.250,50' })).toEqual({ price_max: 125050 });
  });

  it('«Sold out» (INVENTORY-F29) is a status of the funnel, after «Not configured»', () => {
    expect(PRODUCT_STATUSES).toEqual(['active', 'inactive', 'needs_tax_setup', 'sold_out']);
    expect(filterParams({ status: 'sold_out' })).toEqual({ status: 'sold_out' });
  });

  it('what it cannot read does not filter, and a status it does not know neither', () => {
    expect(filterParams({ price_min: 'doce', price_max: '1.250', stock_min: 'x', name: '   ', status: 'gone' })).toEqual({});
  });

  it('says which ends it cannot read: an amount (and why) or a quantity', () => {
    expect(unreadableEnds({ price_min: 'doce', price_max: '1.250', stock_min: '2,5', stock_max: 'x' })).toEqual([
      { name: 'price_min', problem: { ok: false, reason: 'not_amount' } },
      { name: 'price_max', problem: { ok: false, reason: 'ambiguous', grouped: 125000, decimal: 125 } },
      { name: 'stock_max', problem: 'not_quantity' },
    ]);
    expect(unreadableEnds({ price_min: '12', stock_min: '3' })).toEqual([]);
  });

  it('counts only the filters that really apply', () => {
    expect(filtersInUse({})).toBe(0);
    expect(filtersInUse({ sku: 'CAF', price_min: '1', price_max: '2' })).toBe(3);
    expect(filtersInUse({ price_min: 'doce' })).toBe(0);
  });
});

// The searches behind the combo pickers (`Combo` of @erplora/ui): each asks the server for what the
// person types, 20 at a time, and turns every row into an option. A choice is an active product of
// Inventory, sold out today or not (INVENTORY-F29: only the till hides it) (by id, with its SKU and its price); a menu's VAT category, a Taxes key named by its name
// and its rate in force; a category of Inventory (by id, with how many products it has) narrows «Add
// several» to it. The required apps' lists are read through their own operations.
import type { ComboOption, ComboSearch } from '@erplora/ui/components';
import type { LiveClient } from '@erplora/ui/sdk';

import { formatMoney } from './format';

/** Options asked at once: the person narrows them by typing. */
const PAGE = 20;

const search = (query: string) => (query.trim() ? { search: query.trim() } : {});

/** A portion: sold and priced by the unit, what a menu choice is (the server refuses anything else). */
export function isPortion(row: { unit: string; pricing_unit: string; price_quantity: string }): boolean {
  return row.unit === 'ud' && row.pricing_unit === 'ud' && Number(row.price_quantity) === 1;
}

const percent = new Map<string, Intl.NumberFormat>();

function formatRate(rate: string, locale: string): string {
  let found = percent.get(locale);
  if (!found) {
    found = new Intl.NumberFormat(locale, { style: 'percent', maximumFractionDigits: 2 });
    percent.set(locale, found);
  }
  return found.format(Number(rate) / 100);
}

export function searchProducts(client: LiveClient, locale: string): ComboSearch {
  return async (query) => {
    const page = await client.api.call('inventory.product.list', { ...search(query), is_active: true, include_sold_out: true, limit: PAGE });
    return page.rows.filter(isPortion).map((row): ComboOption => ({ id: row.id, label: row.name, hint: `${row.sku} · ${formatMoney(row.price, locale)}` }));
  };
}

export function searchTaxCategories(client: LiveClient, locale: string): ComboSearch {
  return async (query) => {
    const page = await client.api.call('tax.category.list', { ...search(query), limit: PAGE, sort: 'display_name' });
    return page.rows.map((row) => ({
      id: row.key,
      label: row.rate_pct === null || row.operation_class === null ? row.display_name || row.key : `${row.display_name || row.key} · ${formatRate(row.rate_pct, locale)}`,
    }));
  };
}

/** Inventory's categories by name, each with how many products it has (`count` words it). */
export function searchCategories(client: LiveClient, count: (n: number) => string): ComboSearch {
  return async (query) => {
    const page = await client.api.call('inventory.category.list', { ...search(query), limit: PAGE, sort: 'name' });
    return page.rows.map((row): ComboOption => ({ id: row.id, label: row.name, hint: count(row.product_count) }));
  };
}

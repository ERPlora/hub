// The searches behind the pricing forms' pickers (`Combo` of @erplora/ui): each asks the server for what
// the person types, 20 at a time, and turns every row into an option. Products and categories are
// Inventory's, services Services', customer groups Customers' (the active ones): read through their own
// operations, never their models. A catalog price is in the business's `money` (a bare figure until it answers).
import type { ComboOption, ComboSearch } from '@erplora/ui/components';
import type { LiveClient } from '@erplora/ui/sdk';

import { formatMoney, type Money } from './format';

/** Options asked at once: the person narrows them by typing. */
const PAGE = 20;

const search = (query: string) => (query.trim() ? { search: query.trim() } : {});

export function searchProducts(client: LiveClient, locale: string, money?: Money): ComboSearch {
  return async (query) => {
    const page = await client.api.call('inventory.product.list', { ...search(query), limit: PAGE });
    return page.rows.map((row): ComboOption => ({ id: row.id, label: row.name, hint: `${row.sku} · ${formatMoney(row.price, locale, money)}` }));
  };
}

export function searchServices(client: LiveClient, locale: string, money?: Money): ComboSearch {
  return async (query) => {
    const page = await client.api.call('service.service.list', { ...search(query), limit: PAGE });
    return page.rows.map((row): ComboOption => ({ id: row.id, label: row.name, hint: formatMoney(row.price, locale, money) }));
  };
}

export function searchGroups(client: LiveClient): ComboSearch {
  return async (query) => {
    const page = await client.api.call('customer.group.list', { ...search(query), is_active: true, limit: PAGE });
    return page.rows.map((row): ComboOption => ({ id: row.id, label: row.name }));
  };
}

export function searchCategories(client: LiveClient): ComboSearch {
  return async (query) => {
    const page = await client.api.call('inventory.category.list', { ...search(query), limit: PAGE });
    return page.rows.map((row): ComboOption => ({ id: row.id, label: row.name }));
  };
}

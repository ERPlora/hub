// The pickers of the kitchen's forms: the products and the categories of Inventory (a `requires`), searched
// on the server by Inventory's own operations as the person types (the routing panel, a ticket made by
// hand). The first 20 that match; the SKU of a product as its hint.
import type { ComboOption, ComboSearch } from '@erplora/ui/components';
import type { LiveClient } from '@erplora/ui/sdk';

const FIRST = 20;

export function searchProducts(client: LiveClient): ComboSearch {
  return async (query: string): Promise<ComboOption[]> => {
    const text = query.trim();
    const answer = await client.api.call('inventory.product.list', { ...(text ? { search: text } : {}), limit: FIRST });
    return answer.rows.map((product) => ({ id: product.id, label: product.name, hint: product.sku }));
  };
}

export function searchCategories(client: LiveClient): ComboSearch {
  return async (query: string): Promise<ComboOption[]> => {
    const text = query.trim();
    const answer = await client.api.call('inventory.category.list', { ...(text ? { search: text } : {}), limit: FIRST });
    return answer.rows.map((category) => ({ id: category.id, label: category.name }));
  };
}

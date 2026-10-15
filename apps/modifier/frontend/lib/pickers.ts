// The searches behind the modifier forms' pickers (`Combo` of @erplora/ui): each asks the server for what
// the person types, 20 at a time, and turns every row into an option. The required apps' lists are read
// through their own operations (Inventory, Taxes), never their models. A tax category is chosen by its
// key (what the option saves), named by its translated name and its rate in force; the rest by id.
import type { ComboOption, ComboSearch } from '@erplora/ui/components';
import type { LiveClient } from '@erplora/ui/sdk';

/** Options asked at once: the person narrows them by typing. */
const PAGE = 20;

type Translate = (key: string) => string;

const search = (query: string) => (query.trim() ? { search: query.trim() } : {});
const percents = new Map<string, Intl.NumberFormat>();

function percent(rate: string, locale: string): string {
  let found = percents.get(locale);
  if (!found) {
    found = new Intl.NumberFormat(locale, { style: 'percent', maximumFractionDigits: 2 });
    percents.set(locale, found);
  }
  return found.format(Number(rate) / 100);
}

/** «Name · 21%», «Name · exempt», or the bare name when the category has no rule yet. */
export function taxOptionLabel(
  row: { display_name: string; key: string; rate_pct: string | null; operation_class: string | null },
  t: Translate,
  locale: string,
): string {
  const name = row.display_name || row.key;
  if (row.operation_class === null || row.rate_pct === null) return name;
  if (row.operation_class !== 'subject') return `${name} · ${t('modifier.tax.exempt')}`;
  return `${name} · ${percent(row.rate_pct, locale)}`;
}

export function searchTaxCategories(client: LiveClient, t: Translate, locale: string): ComboSearch {
  return async (query) => {
    const page = await client.api.call('tax.category.list', { ...search(query), limit: PAGE, sort: 'display_name' });
    return page.rows.map((row) => ({ id: row.key, label: taxOptionLabel(row, t, locale) }));
  };
}

export function searchProducts(client: LiveClient): ComboSearch {
  return async (query) => {
    const page = await client.api.call('inventory.product.list', { ...search(query), limit: PAGE, sort: 'name' });
    return page.rows.map((row): ComboOption => ({ id: row.id, label: row.name, hint: row.sku }));
  };
}

export function searchCategories(client: LiveClient): ComboSearch {
  return async (query) => {
    const page = await client.api.call('inventory.category.list', { ...search(query), limit: PAGE });
    return page.rows.map((row): ComboOption => ({ id: row.id, label: row.name }));
  };
}

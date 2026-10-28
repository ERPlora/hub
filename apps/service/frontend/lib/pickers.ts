// The searches behind the service forms' pickers (`Combo` of @erplora/ui): each asks the server for what
// the person types, 20 at a time, and turns every row into an option. A tax category is chosen by its
// key (what the service saves), named by its translated name and its rate in force; the rest by id. A
// service shows its price in the business's currency (a bare figure until it answers).
// The required apps' lists are read through their own operations (Taxes, Staff), never their models.
import type { ComboOption, ComboSearch } from '@erplora/ui/components';
import type { LiveClient } from '@erplora/ui/sdk';

import { formatMoney, formatPercentBp, type Money } from './format';

/** Options asked at once: the person narrows them by typing. */
const PAGE = 20;

type Translate = (key: string) => string;

const search = (query: string) => (query.trim() ? { search: query.trim() } : {});

/** «Name · 21 %», «Name · exempt», or the bare name when the category has no rule yet. */
export function taxOptionLabel(
  row: { display_name: string; key: string; rate_pct: string | null; operation_class: string | null },
  t: Translate,
  locale: string,
): string {
  const name = row.display_name || row.key;
  if (row.operation_class === null || row.rate_pct === null) return name;
  if (row.operation_class !== 'subject') return `${name} · ${t('service.tax.exempt')}`;
  return `${name} · ${formatPercentBp(Math.round(Number(row.rate_pct) * 100), locale)}`;
}

export function searchTaxCategories(client: LiveClient, t: Translate, locale: string): ComboSearch {
  return async (query) => {
    const page = await client.api.call('tax.category.list', { ...search(query), limit: PAGE, sort: 'display_name' });
    return page.rows.map((row) => ({ id: row.key, label: taxOptionLabel(row, t, locale) }));
  };
}

const withHint = (id: string, label: string, hint: string | null | undefined): ComboOption => (hint ? { id, label, hint } : { id, label });

export function searchServiceCategories(client: LiveClient): ComboSearch {
  return async (query) => {
    const page = await client.api.call('service.category.list', { ...search(query), limit: PAGE });
    return page.rows.map((row) => withHint(row.id, row.name, row.parent_name));
  };
}

export function searchServices(client: LiveClient, locale: string, money?: Money): ComboSearch {
  return async (query) => {
    const page = await client.api.call('service.service.list', { ...search(query), limit: PAGE });
    return page.rows.map((row) => withHint(row.id, row.name, formatMoney(row.price, locale, money)));
  };
}

export function searchMembers(client: LiveClient): ComboSearch {
  return async (query) => {
    const page = await client.api.call('staff.member.list', { ...search(query), status: 'active', limit: PAGE });
    return page.rows.map((row) => withHint(row.id, row.full_name, row.role_name));
  };
}

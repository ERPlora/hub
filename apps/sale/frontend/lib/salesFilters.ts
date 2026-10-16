// The filters of the Sales list (SALE-F28: status, payment, date, total), as the table's funnel holds them
// (by the list's parameter names, as typed; a filter not in use is absent) and as `sale.sale.list` takes
// them (the total in cents, sales#428). An amount that is not one, or a «to» day before its «from», never
// reaches the server: the table says it under the field. A date range, when there is one, replaces the
// period. «Payment» searches the business's methods on the server (sales#260): each shown as the reader
// reads it, sent by its stored name, the one a sale keeps (sales#181).
import type { DataTableFilterOption, DataTableFilters } from '@erplora/ui/components';
import type { LiveClient } from '@erplora/ui/sdk';

import type { SaleListIn, SaleStatus } from '../operations';
import { centsFromEuros } from './format';

export const SALE_STATUSES: readonly SaleStatus[] = ['completed', 'voided', 'refunded'];

const AMOUNTS = ['total_min', 'total_max'] as const;
/** A short page: a business has a handful of methods; the search finds the rest. */
const METHODS_PAGE = 20;

const typed = (values: DataTableFilters, key: string): string => (values[key] ?? '').trim();

/** The amount filters typed that are not amounts. */
export function invalidAmounts(values: DataTableFilters): string[] {
  return AMOUNTS.filter((key) => typed(values, key) !== '' && centsFromEuros(values[key]) === undefined);
}

/** «Date to» is a day before «Date from»: neither is sent. */
export function reversedDates(values: DataTableFilters): boolean {
  const from = typed(values, 'date_from');
  const to = typed(values, 'date_to');
  return from !== '' && to !== '' && to < from;
}

/** A date range it can use is set: it replaces the period. */
export function hasDateRange(values: DataTableFilters): boolean {
  return !reversedDates(values) && (typed(values, 'date_from') !== '' || typed(values, 'date_to') !== '');
}

/** What the list query takes from the filters. */
export function filterQuery(values: DataTableFilters): Partial<SaleListIn> {
  const query: Partial<SaleListIn> = {};
  if (SALE_STATUSES.includes(values.status as SaleStatus)) query.status = values.status as SaleStatus;
  const method = typed(values, 'payment_method_name');
  if (method) query.payment_method_name = method;
  if (hasDateRange(values)) {
    const from = typed(values, 'date_from');
    const to = typed(values, 'date_to');
    if (from) query.date_from = from;
    if (to) query.date_to = to;
  }
  for (const key of AMOUNTS) {
    const cents = centsFromEuros(values[key]);
    if (cents !== undefined) query[key] = cents;
  }
  return query;
}

/** The filters that really apply (what it cannot read, or a reversed range, does not). */
export function filtersInUse(values: DataTableFilters): number {
  return Object.keys(filterQuery(values)).length;
}

/** The «Payment» lookup: the first methods matching what is typed, from the server. */
export function paymentMethodSearch(client: Pick<LiveClient, 'api'>): (search: string) => Promise<DataTableFilterOption[]> {
  return async (search) => {
    const text = search.trim();
    const answer = await client.api.call('sale.payment_method.list', { ...(text ? { search: text } : {}), limit: METHODS_PAGE });
    return answer.rows.map((method) => ({ value: method.name, label: method.display_name }));
  };
}

// The filters of the Sales list (SALE-F28: status, payment, date, total), as the panel keeps them (the
// text typed) and as `sale.sale.list` takes them (the total in cents). An amount that is not one never
// reaches the server: the panel marks it. A date range, when there is one, replaces the period.
import { centsFromEuros } from '../../lib/format';
import type { SaleListIn, SaleStatus } from '../../operations';

export const SALE_STATUSES: readonly SaleStatus[] = ['completed', 'voided', 'refunded'];

export type SalesFilterKey = 'status' | 'payment_method_name' | 'date_from' | 'date_to' | 'total_min' | 'total_max';
/** Filter values as typed; a filter not in use is absent. */
export type SalesFilterValues = Readonly<Partial<Record<SalesFilterKey, string>>>;

const AMOUNTS = ['total_min', 'total_max'] as const;

const filled = (values: SalesFilterValues, key: SalesFilterKey): boolean => (values[key] ?? '').trim() !== '';

/** The amount filters typed that are not amounts. */
export function invalidAmounts(values: SalesFilterValues): SalesFilterKey[] {
  return AMOUNTS.filter((key) => filled(values, key) && centsFromEuros(values[key]) === undefined);
}

/** A date range is set: it replaces the period. */
export function hasDateRange(values: SalesFilterValues): boolean {
  return filled(values, 'date_from') || filled(values, 'date_to');
}

/** Filters in use; a range counts once. */
export function filterCount(values: SalesFilterValues): number {
  return [
    filled(values, 'status'),
    filled(values, 'payment_method_name'),
    hasDateRange(values),
    filled(values, 'total_min') || filled(values, 'total_max'),
  ].filter(Boolean).length;
}

/** What the list query takes from the filters. */
export function filterQuery(values: SalesFilterValues): Partial<SaleListIn> {
  const query: Partial<SaleListIn> = {};
  if (SALE_STATUSES.includes(values.status as SaleStatus)) query.status = values.status as SaleStatus;
  if (filled(values, 'payment_method_name')) query.payment_method_name = values.payment_method_name!.trim();
  if (filled(values, 'date_from')) query.date_from = values.date_from!.trim();
  if (filled(values, 'date_to')) query.date_to = values.date_to!.trim();
  for (const key of AMOUNTS) {
    const cents = centsFromEuros(values[key]);
    if (cents !== undefined) query[key] = cents;
  }
  return query;
}

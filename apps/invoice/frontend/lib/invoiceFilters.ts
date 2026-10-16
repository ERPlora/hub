// The filters of the Invoices list (INVOICE-F16: status, type, series, source, issue dates and total), as
// the table's funnel holds them (by the list's parameter names, as typed; a filter not in use is absent)
// and as `invoice.invoice.list` takes them (the total in cents, invoice#113). An amount that is not one,
// or a «to» day before its «from», never reaches the server: the table says it under the field.
import type { DataTableFilters } from '@erplora/ui/components';

import type { InvoiceListIn, InvoiceSource, InvoiceStatus, InvoiceType } from '../operations';
import { centsFromEuros } from './format';
import { SOURCE_CODES, STATUS_CODES, TYPE_CODES } from './invoice';

const AMOUNTS = ['total_amount_from', 'total_amount_to'] as const;

const typed = (values: DataTableFilters, key: string): string => (values[key] ?? '').trim();

/** The amount filters typed that are not amounts. */
export function invalidAmounts(values: DataTableFilters): string[] {
  return AMOUNTS.filter((key) => typed(values, key) !== '' && centsFromEuros(values[key]) === undefined);
}

/** «Issued until» is a day before «Issued from»: neither is sent. */
export function reversedDates(values: DataTableFilters): boolean {
  const from = typed(values, 'issue_date_from');
  const to = typed(values, 'issue_date_to');
  return from !== '' && to !== '' && to < from;
}

/** What the list query takes from the filters. */
export function filterQuery(values: DataTableFilters): Partial<InvoiceListIn> {
  const query: Partial<InvoiceListIn> = {};
  if (STATUS_CODES.includes(values.status as InvoiceStatus)) query.status = values.status as InvoiceStatus;
  if (TYPE_CODES.includes(values.invoice_type as InvoiceType)) query.invoice_type = values.invoice_type as InvoiceType;
  if (SOURCE_CODES.includes(values.source_type as InvoiceSource)) query.source_type = values.source_type as InvoiceSource;
  const series = typed(values, 'series_code');
  if (series) query.series_code = series.toUpperCase();
  if (!reversedDates(values)) {
    const from = typed(values, 'issue_date_from');
    const to = typed(values, 'issue_date_to');
    if (from) query.issue_date_from = from;
    if (to) query.issue_date_to = to;
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

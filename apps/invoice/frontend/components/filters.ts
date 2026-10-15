// The filters of the Invoices list (INVOICE-F16: status, type, series, source, issue dates and total), as
// the panel keeps them (the text typed) and as `invoice.invoice.list` takes them (the total in cents). An
// amount that is not one never reaches the server: the panel marks it.
import { centsFromEuros } from '../lib/format';
import { SOURCE_CODES, STATUS_CODES, TYPE_CODES } from '../lib/invoice';
import type { InvoiceListIn, InvoiceSource, InvoiceStatus, InvoiceType } from '../operations';

export type InvoiceFilterKey =
  | 'status'
  | 'invoice_type'
  | 'series_code'
  | 'source_type'
  | 'issue_date_from'
  | 'issue_date_to'
  | 'total_amount_from'
  | 'total_amount_to';
/** Filter values as typed; a filter not in use is absent. */
export type InvoiceFilterValues = Readonly<Partial<Record<InvoiceFilterKey, string>>>;

const AMOUNTS = ['total_amount_from', 'total_amount_to'] as const;

const filled = (values: InvoiceFilterValues, key: InvoiceFilterKey): boolean => (values[key] ?? '').trim() !== '';

/** The amount filters typed that are not amounts. */
export function invalidAmounts(values: InvoiceFilterValues): InvoiceFilterKey[] {
  return AMOUNTS.filter((key) => filled(values, key) && centsFromEuros(values[key]) === undefined);
}

/** Filters in use; a range counts once. */
export function filterCount(values: InvoiceFilterValues): number {
  return [
    filled(values, 'status'),
    filled(values, 'invoice_type'),
    filled(values, 'series_code'),
    filled(values, 'source_type'),
    filled(values, 'issue_date_from') || filled(values, 'issue_date_to'),
    filled(values, 'total_amount_from') || filled(values, 'total_amount_to'),
  ].filter(Boolean).length;
}

/** What the list query takes from the filters. */
export function filterQuery(values: InvoiceFilterValues): Partial<InvoiceListIn> {
  const query: Partial<InvoiceListIn> = {};
  if (STATUS_CODES.includes(values.status as InvoiceStatus)) query.status = values.status as InvoiceStatus;
  if (TYPE_CODES.includes(values.invoice_type as InvoiceType)) query.invoice_type = values.invoice_type as InvoiceType;
  if (SOURCE_CODES.includes(values.source_type as InvoiceSource)) query.source_type = values.source_type as InvoiceSource;
  if (filled(values, 'series_code')) query.series_code = values.series_code!.trim().toUpperCase();
  if (filled(values, 'issue_date_from')) query.issue_date_from = values.issue_date_from!.trim();
  if (filled(values, 'issue_date_to')) query.issue_date_to = values.issue_date_to!.trim();
  for (const key of AMOUNTS) {
    const cents = centsFromEuros(values[key]);
    if (cents !== undefined) query[key] = cents;
  }
  return query;
}

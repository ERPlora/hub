// The filters of the Invoices list (INVOICE-F16: status, type, series, source, issue dates and total), as
// the table's funnel holds them (by the list's parameter names, as typed) and as `invoice.invoice.list`
// takes them (the total in cents). An amount that is not one, or a «to» day before its «from», never
// reaches the server: the table says it under the field.
// flow: ninguno — FIX DataTable parte 2b-2 (PLAN-MIGRATIONS §13: filtros como en la vieja)
import { describe, expect, it } from 'vitest';

import { filterQuery, filtersInUse, invalidAmounts, reversedDates } from './invoiceFilters';

describe('invoice filters', () => {
  it('take the closed lists, the series in capitals, the days and the totals in cents', () => {
    expect(
      filterQuery({
        status: 'paid',
        invoice_type: 'F2',
        series_code: ' fact ',
        source_type: 'sale',
        issue_date_from: '2026-10-01',
        issue_date_to: '2026-10-14',
        total_amount_from: '12,5',
        total_amount_to: '100',
      }),
    ).toEqual({
      status: 'paid',
      invoice_type: 'F2',
      series_code: 'FACT',
      source_type: 'sale',
      issue_date_from: '2026-10-01',
      issue_date_to: '2026-10-14',
      total_amount_from: 1250,
      total_amount_to: 10000,
    });
  });

  it('«from 12» is twelve euros, never twelve cents (invoice#113)', () => {
    expect(filterQuery({ total_amount_from: '12' })).toEqual({ total_amount_from: 1200 });
  });

  it('drop what is not one of the server’s values and what is blank', () => {
    expect(filterQuery({ status: 'draft', invoice_type: 'X9', source_type: 'web', series_code: '  ' })).toEqual({});
  });

  it('never send an amount that is not one, and say which', () => {
    expect(filterQuery({ total_amount_from: 'abc' })).toEqual({});
    expect(invalidAmounts({ total_amount_from: 'abc', total_amount_to: '3' })).toEqual(['total_amount_from']);
  });

  it('a «to» day before its «from» is said and sends neither; one end alone, or the same day, is fine', () => {
    expect(reversedDates({ issue_date_from: '2026-10-14', issue_date_to: '2026-10-01' })).toBe(true);
    expect(filterQuery({ issue_date_from: '2026-10-14', issue_date_to: '2026-10-01', status: 'paid' })).toEqual({ status: 'paid' });
    expect(reversedDates({ issue_date_from: '2026-10-14', issue_date_to: '2026-10-14' })).toBe(false);
    expect(reversedDates({ issue_date_to: '2026-10-01' })).toBe(false);
    expect(filterQuery({ issue_date_from: '2026-10-14' })).toEqual({ issue_date_from: '2026-10-14' });
  });

  it('count the filters that really apply', () => {
    expect(filtersInUse({})).toBe(0);
    expect(filtersInUse({ status: 'paid', issue_date_from: '2026-10-01', total_amount_to: '5' })).toBe(3);
    expect(filtersInUse({ total_amount_from: 'abc', issue_date_from: '2026-10-14', issue_date_to: '2026-10-01' })).toBe(0);
  });
});

// The filters of the Invoices list (INVOICE-F16: status, type, series, source, issue dates and total), as
// the panel keeps them (the text typed) and as `invoice.invoice.list` takes them (the total in cents). An
// amount that is not one never reaches the server: the panel marks it.
import { describe, expect, it } from 'vitest';

import { filterCount, filterQuery, invalidAmounts } from './filters';

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

  it('drop what is not one of the server’s values and what is blank', () => {
    expect(filterQuery({ status: 'draft', invoice_type: 'X9', source_type: 'web', series_code: '  ' })).toEqual({});
  });

  it('never send an amount that is not one, and say which', () => {
    expect(filterQuery({ total_amount_from: 'abc' })).toEqual({});
    expect(invalidAmounts({ total_amount_from: 'abc', total_amount_to: '3' })).toEqual(['total_amount_from']);
  });

  it('count the filters in use, a range once', () => {
    expect(filterCount({})).toBe(0);
    expect(filterCount({ status: 'paid', issue_date_from: '2026-10-01', issue_date_to: '2026-10-02', total_amount_to: '5' })).toBe(3);
  });
});

// The filters of the Sales list (SALE-F28: status, payment, date, total) as the person types them and
// as `sale.sale.list` takes them: the total in euros typed → cents; an amount that is not one never
// reaches the server (the panel says so); a date range counts once, a total range too.
import { describe, expect, it } from 'vitest';

import { filterCount, filterQuery, hasDateRange, invalidAmounts, SALE_STATUSES } from './filters';

describe('sales filters', () => {
  it('offer the three statuses of a sale', () => {
    expect(SALE_STATUSES).toEqual(['completed', 'voided', 'refunded']);
  });

  it('go to the server as it takes them: the total in cents', () => {
    expect(
      filterQuery({
        status: 'voided',
        payment_method_name: 'Cash',
        date_from: '2026-10-01',
        date_to: '2026-10-14',
        total_min: '12,5',
        total_max: '100',
      }),
    ).toEqual({
      status: 'voided',
      payment_method_name: 'Cash',
      date_from: '2026-10-01',
      date_to: '2026-10-14',
      total_min: 1250,
      total_max: 10000,
    });
    expect(filterQuery({})).toEqual({});
  });

  it('an amount that is not one, or a status that is not one, never goes', () => {
    expect(filterQuery({ total_min: 'abc', total_max: '-5', status: 'open' })).toEqual({});
    expect(invalidAmounts({ total_min: 'abc', total_max: '-5' })).toEqual(['total_min', 'total_max']);
    expect(invalidAmounts({ total_min: '12.50', total_max: ' ' })).toEqual([]);
  });

  it('count a range once', () => {
    expect(filterCount({})).toBe(0);
    expect(filterCount({ status: 'completed', date_from: '2026-10-01', date_to: '2026-10-14', total_max: '50' })).toBe(3);
    expect(filterCount({ payment_method_name: 'Cash', date_to: '2026-10-14' })).toBe(2);
  });

  it('know when a date range replaces the period', () => {
    expect(hasDateRange({ status: 'completed' })).toBe(false);
    expect(hasDateRange({ date_to: '2026-10-14' })).toBe(true);
  });
});

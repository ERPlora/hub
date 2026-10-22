// The filters of the VeriFactu lists as the panel keeps them and as the queries take them.
import { describe, expect, it } from 'vitest';

import { filterCount, filterQuery, invalidAmounts } from './filters';

describe('filters', () => {
  it('count the filters in use, a range once', () => {
    expect(filterCount({})).toBe(0);
    expect(filterCount({ status: 'rejected', issue_date_from: '2026-10-01', issue_date_to: '2026-10-14' })).toBe(2);
    expect(filterCount({ date_from: '2026-10-01', kind: 'failed', severity: 'error' })).toBe(3);
  });

  it('mark an amount that is not one', () => {
    expect(invalidAmounts({ total_amount_from: '12x', total_amount_to: '3' })).toEqual(['total_amount_from']);
  });

  it('turn the panel’s text into the list’s query (totals in cents, a wrong amount left out)', () => {
    expect(filterQuery({ status: 'rejected', total_amount_from: '12,50', total_amount_to: 'x', issue_date_from: '2026-10-01' })).toEqual({
      status: 'rejected',
      total_amount_from: 1250,
      issue_date_from: '2026-10-01',
    });
  });
});

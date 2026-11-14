// The filters of the VeriFactu lists (Records and Events) as the table's funnel holds them (as typed) and as
// the list queries take them: the totals in minor units of the business's money, a day «until» before its «from» left out.
import { describe, expect, it } from 'vitest';

import { EUR, JPY } from '../../../../base/frontend/__tests__/amount-filter';
import { backwardsDays, filterParams, filtersInUse } from './filters';

describe('filters', () => {
  it('turn what is typed into the query: the closed lists and the days as they are, the totals in cents', () => {
    expect(
      filterParams({
        status: 'rejected',
        record_type: 'alta',
        invoice_type: 'F2',
        environment: 'testing',
        issue_date_from: '2026-10-01',
        issue_date_to: '2026-10-14',
        total_amount_from: '12,50',
        total_amount_to: '1000',
      }),
    ).toEqual({
      status: 'rejected',
      record_type: 'alta',
      invoice_type: 'F2',
      environment: 'testing',
      issue_date_from: '2026-10-01',
      issue_date_to: '2026-10-14',
      total_amount_from: 1250,
      total_amount_to: 100000,
    });
    expect(filterParams({ kind: 'failed', severity: 'error', date_from: '2026-10-14', date_to: '2026-10-14' })).toEqual({
      kind: 'failed',
      severity: 'error',
      date_from: '2026-10-14',
      date_to: '2026-10-14',
    });
  });

  it('read a total as every amount filter of the Hub, in the business\'s money', () => {
    expect(filterParams({ total_amount_from: '1.000,50', total_amount_to: '12,50 €' }, EUR)).toEqual({ total_amount_from: 100050, total_amount_to: 1250 });
    expect(filterParams({ total_amount_from: '2 500', total_amount_to: '1,000.50' }, EUR)).toEqual({ total_amount_from: 250000, total_amount_to: 100050 });
    expect(filterParams({ total_amount_from: '1500', total_amount_to: '¥1.500' }, JPY)).toEqual({ total_amount_from: 1500, total_amount_to: 1500 });
  });

  it('never send a total it cannot read: not an amount, negative, or «1.000» that reads two ways in euros', () => {
    expect(filterParams({ total_amount_from: '12x', total_amount_to: '3' }, EUR)).toEqual({ total_amount_to: 300 });
    expect(filterParams({ total_amount_from: '-5', total_amount_to: '1.000' }, EUR)).toEqual({});
    expect(filterParams({ total_amount_from: '12,5' }, JPY)).toEqual({});
  });

  it('mark a day «until» before its «from» and leave it out; the same day is a range', () => {
    expect(backwardsDays({ issue_date_from: '2026-10-14', issue_date_to: '2026-10-01' })).toEqual(['issue_date_to']);
    expect(backwardsDays({ date_from: '2026-10-14', date_to: '2026-10-13' })).toEqual(['date_to']);
    expect(backwardsDays({ date_from: '2026-10-14', date_to: '2026-10-14', issue_date_to: '2026-01-01' })).toEqual([]);
    expect(filterParams({ issue_date_from: '2026-10-14', issue_date_to: '2026-10-01' })).toEqual({ issue_date_from: '2026-10-14' });
    expect(filterParams({ date_from: '2026-10-14', date_to: '2026-10-13' })).toEqual({ date_from: '2026-10-14' });
  });

  it('count only the filters that apply', () => {
    expect(filtersInUse({})).toBe(0);
    expect(filtersInUse({ status: 'rejected', issue_date_from: '2026-10-01', issue_date_to: '2026-10-14' })).toBe(3);
    expect(filtersInUse({ total_amount_from: 'x' })).toBe(0);
    expect(filtersInUse({ total_amount_from: '1.000', total_amount_to: '1.000,50' }, EUR)).toBe(1);
  });
});

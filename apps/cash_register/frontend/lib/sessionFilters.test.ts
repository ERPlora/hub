// The filters of the sessions list (status, number and the four amounts; CASH_REGISTER Pantallas · Caja),
// as the table's funnel holds them (what is typed, in the business's money) and as `cash_register.session.list` takes
// them (cents), read as every amount filter of the Hub (hub#1196). A difference may be negative (a short drawer); an
// amount that is not one never reaches the server (cash_register#103, #107; hub#2271); the page says why under it
// (`SessionsPage.test.ts`).
import { describe, expect, it } from 'vitest';

import { filterParams, filtersInUse } from './sessionFilters';

describe('session filters', () => {
  it('turn what is typed into the query: euros into cents, a signed difference', () => {
    expect(
      filterParams({ status: 'closed', number: ' S-261014 ', opening_min: '100', expected_max: '1.250,50', difference_max: '-0,50', counted_min: '' }),
    ).toEqual({ status: 'closed', number: 'S-261014', opening_min: 10000, expected_max: 125050, difference_max: -50 });
    expect(filterParams({ opening_max: '12', counted_min: '0,5', counted_max: '7', difference_min: '−5', expected_min: '3' })).toEqual({
      opening_max: 1200,
      counted_min: 50,
      counted_max: 700,
      difference_min: -500,
      expected_min: 300,
    });
    expect(filterParams({ status: 'suspended' })).toEqual({});
  });

  it('never send what is no amount; only the difference takes a minus', () => {
    expect(filterParams({ opening_min: 'abc', counted_max: '-5', difference_min: '-5', expected_min: '7' })).toEqual({ difference_min: -500, expected_min: 700 });
    expect(filterParams({ opening_min: 'abc', counted_max: '-5' })).toEqual({});
  });

  it('count only the filters that apply: an amount it cannot read does not', () => {
    expect(filtersInUse({})).toBe(0);
    expect(filtersInUse({ status: 'open', opening_min: '1', opening_max: '2', difference_max: '-1' })).toBe(4);
    expect(filtersInUse({ opening_min: 'abc' })).toBe(0);
  });
});

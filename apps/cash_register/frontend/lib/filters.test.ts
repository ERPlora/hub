// The filters of the sessions list (status, number and the four amounts; CASH_REGISTER Pantallas · Caja),
// as the panel keeps them (what is typed, in euros) and as `cash_register.session.list` takes them (cents).
// A difference may be negative (a short drawer); an amount that is not one never reaches the server.
import { describe, expect, it } from 'vitest';

import { filterCount, filterQuery, invalidAmounts } from './filters';

describe('session filters', () => {
  it('turn what is typed into the query: euros into cents, a signed difference', () => {
    expect(
      filterQuery({ status: 'closed', number: ' S-261014 ', opening_min: '100', expected_max: '1.250,50', difference_max: '-0,50', counted_min: '' }),
    ).toEqual({ status: 'closed', number: 'S-261014', opening_min: 10000, expected_max: 125050, difference_max: -50 });
    expect(filterQuery({ status: 'suspended' })).toEqual({});
  });

  it('mark what is no amount and never send it; only the difference takes a minus', () => {
    expect(invalidAmounts({ opening_min: 'abc', counted_max: '-5', difference_min: '-5', expected_min: '7' })).toEqual(['opening_min', 'counted_max']);
    expect(filterQuery({ opening_min: 'abc', counted_max: '-5' })).toEqual({});
  });

  it('count the filters in use, a range once', () => {
    expect(filterCount({})).toBe(0);
    expect(filterCount({ status: 'open', opening_min: '1', opening_max: '2', difference_max: '-1' })).toBe(3);
  });
});

// The filters of the customer list (CUSTOMER-F02) as `customer.customer.list` takes them: stage and
// source as chosen, active as a yes/no and spent by range typed in the business's currency, sent in its
// minor units (flow customer-business-currency), read as every amount filter of the Hub (hub#1196). An amount it
// cannot read neither counts nor filters (the page says why under it: `CustomerListPage.test.ts`).
import { describe, expect, it } from 'vitest';

import { filterParams, filtersInUse, SOURCES } from './customerFilters';
import type { Money } from './money';

const EUR: Money = { currency: 'EUR', decimals: 2 };
const PLN: Money = { currency: 'PLN', decimals: 2 };
const JPY: Money = { currency: 'JPY', decimals: 0 };

describe('filterParams', () => {
  it('turns the filters into the query: a yes/no for active, cents for spent', () => {
    expect(filterParams({ lifecycle_stage: 'vip', source: 'import', is_active: 'false', spent_from: '10,5', spent_to: '100' }, EUR)).toEqual({
      lifecycle_stage: 'vip',
      source: 'import',
      is_active: false,
      spent_min: 1050,
      spent_max: 10000,
    });
  });

  it('does not guess «1.000» in euros (a thousand or one: it asks, hub#1196); in yen it is a thousand', () => {
    expect(filterParams({ spent_from: '1.000', spent_to: '1.000,50' }, EUR)).toEqual({ spent_max: 100050 });
    expect(filterParams({ spent_from: '1.000' }, JPY)).toEqual({ spent_min: 1000 });
  });

  it('reads «Spent» in the business\'s currency, with its decimals and its symbol', () => {
    expect(filterParams({ spent_from: '12,50 zł', spent_to: 'PLN 100' }, PLN)).toEqual({ spent_min: 1250, spent_max: 10000 });
    expect(filterParams({ spent_from: '1250', spent_to: '¥5,000' }, JPY)).toEqual({ spent_min: 1250, spent_max: 5000 });
  });

  it('does not take another currency\'s amount, nor decimals the currency has not', () => {
    expect(filterParams({ spent_from: '12,50 €', spent_to: '12,5' }, JPY)).toEqual({});
    expect(filtersInUse({ spent_from: '12,50 €' }, PLN)).toBe(0);
  });

  it('leaves out what is not in use or not an amount', () => {
    expect(filterParams({})).toEqual({});
    expect(filterParams({ spent_from: 'abc' })).toEqual({});
  });
});

describe('filtersInUse', () => {
  it('counts only the filters that really apply', () => {
    expect(filtersInUse({ lifecycle_stage: 'vip', spent_from: '1' })).toBe(2);
    expect(filtersInUse({ spent_to: 'mil' })).toBe(0);
  });
});

describe('SOURCES', () => {
  it('offers every source a card can have, imported included', () => {
    expect(SOURCES).toEqual(['walk_in', 'phone', 'whatsapp', 'website', 'social', 'referral', 'import', 'other']);
  });
});

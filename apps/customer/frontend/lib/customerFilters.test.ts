// The filters of the customer list (CUSTOMER-F02) as `customer.customer.list` takes them: stage and
// source as chosen, active as a yes/no and spent by range typed in the business's currency, sent in its
// minor units (flow customer-business-currency). An amount it cannot read is named (the table says it under
// its field) and neither counts nor filters.
import { describe, expect, it } from 'vitest';

import { filterParams, filtersInUse, SOURCES, unreadableAmounts } from './customerFilters';
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

  it('reads «1.000» as a thousand of the business\'s currency', () => {
    expect(filterParams({ spent_from: '1.000' }, EUR)).toEqual({ spent_min: 100000 });
  });

  it('reads «Spent» in the business\'s currency, with its decimals and its symbol', () => {
    expect(filterParams({ spent_from: '12,50 zł', spent_to: 'PLN 100' }, PLN)).toEqual({ spent_min: 1250, spent_max: 10000 });
    expect(filterParams({ spent_from: '1250', spent_to: '¥5,000' }, JPY)).toEqual({ spent_min: 1250, spent_max: 5000 });
  });

  it('does not take another currency\'s amount, nor decimals the currency has not', () => {
    expect(filterParams({ spent_from: '12,50 €', spent_to: '12,5' }, JPY)).toEqual({});
    expect(unreadableAmounts({ spent_from: '12,50 €', spent_to: '12,5' }, JPY)).toEqual(['spent_from', 'spent_to']);
    expect(filtersInUse({ spent_from: '12,50 €' }, PLN)).toBe(0);
  });

  it('leaves out what is not in use or not an amount', () => {
    expect(filterParams({})).toEqual({});
    expect(filterParams({ spent_from: 'abc' })).toEqual({});
  });
});

describe('unreadableAmounts', () => {
  it('names the ends of «Spent» it cannot read, and nothing else', () => {
    expect(unreadableAmounts({ spent_from: '10', spent_to: 'mil', source: 'phone' })).toEqual(['spent_to']);
    expect(unreadableAmounts({ spent_from: 'x', spent_to: 'y' })).toEqual(['spent_from', 'spent_to']);
    expect(unreadableAmounts({})).toEqual([]);
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

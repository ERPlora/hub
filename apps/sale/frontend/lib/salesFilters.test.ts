// The filters of the Sales list (SALE-F28: status, payment, date, total) as the table's funnel holds them
// (by the list's parameter names, as typed) and as `sale.sale.list` takes them: the total in euros typed →
// cents (sales#428); an amount that is not one, or a «to» day before its «from», never reaches the server
// (the table says so under it); a date range, when there is one, replaces the period. «Payment» searches
// the business's methods on the server, shown as the reader reads them, sent by their stored name.
// flow: ninguno — FIX DataTable parte 2b-2 (PLAN-MIGRATIONS §13: filtros como en la vieja)
import { describe, expect, it, vi } from 'vitest';

import { filterQuery, filtersInUse, hasDateRange, invalidAmounts, paymentMethodSearch, reversedDates, SALE_STATUSES } from './salesFilters';

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

  it('a «to» day before its «from» is said, sends neither and leaves the period ruling', () => {
    const reversed = { date_from: '2026-10-14', date_to: '2026-10-01', status: 'completed' };
    expect(reversedDates(reversed)).toBe(true);
    expect(filterQuery(reversed)).toEqual({ status: 'completed' });
    expect(hasDateRange(reversed)).toBe(false);
    expect(reversedDates({ date_from: '2026-10-14', date_to: '2026-10-14' })).toBe(false);
    expect(reversedDates({ date_to: '2026-10-01' })).toBe(false);
  });

  it('count the filters that really apply', () => {
    expect(filtersInUse({})).toBe(0);
    expect(filtersInUse({ status: 'completed', date_from: '2026-10-01', total_max: '50' })).toBe(3);
    expect(filtersInUse({ total_min: 'abc', date_from: '2026-10-14', date_to: '2026-10-01' })).toBe(0);
  });

  it('know when a date range replaces the period', () => {
    expect(hasDateRange({ status: 'completed' })).toBe(false);
    expect(hasDateRange({ date_to: '2026-10-14' })).toBe(true);
  });

  it('«Payment» searches the methods on the server: the reader’s name shown, the stored one sent (sales#181)', async () => {
    const call = vi.fn().mockResolvedValue({
      rows: [
        { id: 'm1', name: 'Cash', display_name: 'Efectivo' },
        { id: 'm2', name: 'Card', display_name: 'Tarjeta' },
      ],
      total: 2,
      limit: 20,
      offset: 0,
    });
    const load = paymentMethodSearch({ api: { call } } as never);
    expect(await load('efe')).toEqual([
      { value: 'Cash', label: 'Efectivo' },
      { value: 'Card', label: 'Tarjeta' },
    ]);
    expect(call).toHaveBeenLastCalledWith('sale.payment_method.list', { search: 'efe', limit: 20 });
    await load('');
    expect(call).toHaveBeenLastCalledWith('sale.payment_method.list', { limit: 20 });
  });

  it('a search that fails is the lookup’s error, never a box of free text (sales#260)', async () => {
    const load = paymentMethodSearch({ api: { call: vi.fn().mockRejectedValue(new Error('offline')) } } as never);
    await expect(load('efe')).rejects.toThrow('offline');
  });
});

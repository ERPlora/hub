// The period of the Sales screen (SALE-F28): «Today», «7 days», «30 days» or «All», counted back from
// the business day, both ends included; the server filters by business day (`date_from`, `date_to`).
import { afterEach, describe, expect, it, vi } from 'vitest';

import { deviceDay, PERIODS, periodBounds } from './period';

afterEach(() => {
  vi.useRealTimers();
});

describe('periodBounds', () => {
  it('offers Today, 7 days, 30 days and All, in that order', () => {
    expect(PERIODS).toEqual(['today', 'week', 'month', 'all']);
  });

  it('counts back from the business day, both ends included', () => {
    expect(periodBounds('today', '2026-10-14')).toEqual({ date_from: '2026-10-14', date_to: '2026-10-14' });
    expect(periodBounds('week', '2026-10-14')).toEqual({ date_from: '2026-10-08', date_to: '2026-10-14' });
    expect(periodBounds('month', '2026-10-14')).toEqual({ date_from: '2026-09-15', date_to: '2026-10-14' });
  });

  it('«All» has no bounds', () => {
    expect(periodBounds('all', '2026-10-14')).toEqual({});
  });

  it('crosses months, years and a DST change without slipping a day', () => {
    expect(periodBounds('week', '2026-03-02')).toEqual({ date_from: '2026-02-24', date_to: '2026-03-02' });
    expect(periodBounds('month', '2027-01-10')).toEqual({ date_from: '2026-12-12', date_to: '2027-01-10' });
    expect(periodBounds('week', '2026-10-27')).toEqual({ date_from: '2026-10-21', date_to: '2026-10-27' });
  });
});

describe('deviceDay', () => {
  it('is the device’s local calendar day, as an ISO day', () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date(2026, 9, 14, 23, 30));
    expect(deviceDay()).toBe('2026-10-14');
    vi.setSystemTime(new Date(2026, 0, 2, 0, 5));
    expect(deviceDay()).toBe('2026-01-02');
  });
});

// How the service screens paint money, rates and dates, with the page language's own format (Intl):
// euros from cents, a discount in basis points as the language writes a percentage, and a day.
import { describe, expect, it } from 'vitest';

import { decimalMark, formatDate, formatMoney, formatPercentBp, percentFieldText, readPercentBp } from './format';

describe('formatMoney', () => {
  it('paints whole cents as euros in the page language', () => {
    expect(formatMoney(2250, 'es')).toMatch(/^22,50\s€$/);
    expect(formatMoney(123456, 'es')).toMatch(/^1\.?234,56\s€$/);
    expect(formatMoney(2250, 'en')).toBe('€22.50');
    expect(formatMoney(0, 'en')).toBe('€0.00');
  });
});

describe('decimalMark', () => {
  it('is the comma in Spanish and the point in English', () => {
    expect(decimalMark('es')).toBe(',');
    expect(decimalMark('en')).toBe('.');
  });
});

describe('formatPercentBp', () => {
  it('paints basis points as the language writes a percentage', () => {
    expect(formatPercentBp(1050, 'es')).toMatch(/^10,5\s%$/);
    expect(formatPercentBp(1000, 'en')).toBe('10%');
    expect(formatPercentBp(1234, 'en')).toBe('12.34%');
  });
});

describe('percentFieldText and readPercentBp', () => {
  it('write basis points for a field and read them back, in the page format', () => {
    expect(percentFieldText(1050, 'es')).toBe('10,5');
    expect(percentFieldText(0, 'en')).toBe('0');
    expect(readPercentBp('10,5')).toBe(1050);
    expect(readPercentBp('12.34')).toBe(1234);
    expect(readPercentBp('')).toBe(0);
  });

  it('say null when it is not a percentage from 0 to 100 with at most two decimals', () => {
    for (const text of ['abc', '101', '10,555', '-1']) expect(readPercentBp(text), text).toBeNull();
  });
});

describe('formatDate', () => {
  it('paints the day of a moment in the page language (no time)', () => {
    expect(formatDate('2026-10-13T10:00:00Z', 'es', 'UTC')).toBe('13 oct 2026');
    expect(formatDate('2026-10-13T10:00:00Z', 'en', 'UTC')).toBe('Oct 13, 2026');
    expect(formatDate(null, 'en')).toBe('');
  });
});

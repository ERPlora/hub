// How the VeriFactu screens paint numbers and days (WORKBOOK «Para quien lo mantiene»: money travels in
// signed cents, quantities and rates as decimal strings, days as `YYYY-MM-DD`). One place turns them into
// text in the page's language with `Intl`, and the euros a person types into cents: no page formats by
// hand.
import { describe, expect, it } from 'vitest';

import { centsFromEuros, formatDate, formatMoney, formatPercent, formatQuantity, formatUnitPrice, plain } from './format';

/** Intl puts a narrow no-break space before «€» and «%» in Spanish: compared as a plain space. */
const spaced = (text: string) => plain(text);

describe('formatUnitPrice', () => {
  it('writes a unit price (cents with two decimals) with two decimals, up to four when it has them', () => {
    expect(plain(formatUnitPrice('1000.00', 'en'))).toBe('€10.00');
    expect(plain(formatUnitPrice('82.64', 'en'))).toBe('€0.8264');
    expect(plain(formatUnitPrice('41.30', 'es'))).toBe('0,413 €');
    expect(plain(formatUnitPrice(1250, 'es'))).toBe('12,50 €');
    expect(formatUnitPrice(null, 'en')).toBe('—');
  });
});

describe('formatMoney', () => {
  it('paints cents as euros in the page language, a rectifying amount with its sign', () => {
    expect(formatMoney(123456, 'en')).toBe('€1,234.56');
    expect(spaced(formatMoney(123456, 'es'))).toBe('1234,56 €');
    expect(formatMoney(0, 'en')).toBe('€0.00');
    expect(formatMoney(-350, 'en')).toBe('-€3.50');
    expect(spaced(formatMoney(-1210, 'es'))).toBe('-12,10 €');
  });

  it('a missing amount is a dash, never «NaN», and a broken language falls back to English', () => {
    expect(formatMoney(null, 'en')).toBe('—');
    expect(formatMoney(undefined, 'es')).toBe('—');
    expect(formatMoney(100, 'not a tag!')).toBe('€1.00');
  });
});

describe('formatPercent', () => {
  it('paints a rate without trailing zeros', () => {
    expect(formatPercent('21.00', 'en')).toBe('21%');
    expect(spaced(formatPercent('5.20', 'es'))).toBe('5,2 %');
    expect(formatPercent(null, 'en')).toBe('—');
  });
});

describe('formatQuantity', () => {
  it('paints a quantity with only the decimals it has, and its sign', () => {
    expect(formatQuantity('2.000', 'en')).toBe('2');
    expect(formatQuantity('0.532', 'es')).toBe('0,532');
    expect(formatQuantity('-1.000', 'en')).toBe('-1');
  });
});

describe('formatDate', () => {
  it('paints a calendar day in the page language without moving it to the day before', () => {
    expect(formatDate('2026-09-29', 'es')).toBe('29/9/2026');
    expect(formatDate('2026-09-29', 'en')).toBe('9/29/2026');
    expect(formatDate('2026-01-01', 'es')).toBe('1/1/2026');
  });

  it('nothing or not a day is a dash or the text as it came', () => {
    expect(formatDate('', 'es')).toBe('—');
    expect(formatDate(null, 'es')).toBe('—');
    expect(formatDate('yesterday', 'es')).toBe('yesterday');
  });
});

describe('centsFromEuros', () => {
  it('reads what a person types, with a comma or a dot, into whole cents', () => {
    expect(centsFromEuros('12,5')).toBe(1250);
    expect(centsFromEuros(' 12.50 ')).toBe(1250);
    expect(centsFromEuros('0,01')).toBe(1);
    expect(centsFromEuros(7)).toBe(700);
  });

  it('empty, negative or not an amount is nothing', () => {
    expect(centsFromEuros('')).toBeUndefined();
    expect(centsFromEuros(null)).toBeUndefined();
    expect(centsFromEuros('12,345')).toBeUndefined();
    expect(centsFromEuros('-3')).toBeUndefined();
    expect(centsFromEuros('abc')).toBeUndefined();
  });
});

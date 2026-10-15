// How the sale screens paint numbers (WORKBOOK «Para quien lo mantiene»: money travels in cents,
// quantities and percentages as decimal strings). One place turns them into text in the page's
// language with `Intl.NumberFormat`, and the euros a person types into cents: no page formats by hand.
import { describe, expect, it } from 'vitest';

import { centsFromEuros, formatDay, formatMoney, formatPercent, formatQuantity, plain } from './format';

/** Intl puts a narrow no-break space before «€» and «%» in Spanish: compared as a plain space. */
const spaced = (text: string) => plain(text);

describe('formatMoney', () => {
  it('paints cents as euros in the page language', () => {
    expect(formatMoney(123456, 'en')).toBe('€1,234.56');
    expect(spaced(formatMoney(123456, 'es'))).toBe('1234,56 €');
    expect(formatMoney(0, 'en')).toBe('€0.00');
    expect(formatMoney(-350, 'en')).toBe('-€3.50');
  });

  it('a missing amount is a dash, never «NaN», and a broken language falls back to English', () => {
    expect(formatMoney(null, 'en')).toBe('—');
    expect(formatMoney(undefined, 'es')).toBe('—');
    expect(formatMoney(100, 'not a tag!')).toBe('€1.00');
  });
});

describe('formatPercent', () => {
  it('paints a rate or a discount without trailing zeros', () => {
    expect(formatPercent('21.00', 'en')).toBe('21%');
    expect(spaced(formatPercent('12.50', 'es'))).toBe('12,5 %');
    expect(formatPercent('5.2', 'en')).toBe('5.2%');
    expect(formatPercent(null, 'en')).toBe('—');
  });
});

describe('formatQuantity', () => {
  it('paints a quantity with only the decimals it has, and its unit unless it is units', () => {
    expect(formatQuantity('2.000', 'ud', 'en')).toBe('2');
    expect(formatQuantity('0.532', 'kg', 'es')).toBe('0,532 kg');
    expect(formatQuantity('1.500', 'h', 'en')).toBe('1.5 h');
  });
});

describe('centsFromEuros', () => {
  it('reads what a person types, with a comma or a dot, into whole cents', () => {
    expect(centsFromEuros('12,5')).toBe(1250);
    expect(centsFromEuros(' 12.50 ')).toBe(1250);
    expect(centsFromEuros('0,01')).toBe(1);
    expect(centsFromEuros(7)).toBe(700);
  });

  it('empty or not an amount is nothing', () => {
    expect(centsFromEuros('')).toBeUndefined();
    expect(centsFromEuros(null)).toBeUndefined();
    expect(centsFromEuros('12,345')).toBeUndefined();
    expect(centsFromEuros('abc')).toBeUndefined();
  });
});

describe('formatDay', () => {
  it('a day as the reader writes it (what «Expires on» shows)', () => {
    expect(formatDay('2026-11-14T10:00:00Z', 'es')).toBe('14/11/2026');
    expect(formatDay('2026-11-14T10:00:00Z', 'en')).toBe('11/14/2026');
    expect(formatDay(null, 'es')).toBe('—');
  });
});

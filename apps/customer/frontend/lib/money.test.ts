// Money on the customer screens (WORKBOOK «Reglas que no se rompen»: money travels in cents; the
// screen writes the «Spent» filter in euros). One formatter and one parser, so no page formats or
// scales by hand.
import { describe, expect, it } from 'vitest';

import { centsFromEuros, formatMoney, readEuros } from './money';

describe('formatMoney', () => {
  it('paints cents as euros in the page language', () => {
    expect(formatMoney(123456, 'en')).toBe('€1,234.56');
    expect(formatMoney(123456, 'es').replace(/\s/g, ' ')).toBe('1234,56 €');
    expect(formatMoney(0, 'en')).toBe('€0.00');
  });

  it('a missing amount is a dash, never «NaN»', () => {
    expect(formatMoney(null, 'en')).toBe('—');
    expect(formatMoney(undefined, 'es')).toBe('—');
  });

  it('a broken language falls back to English', () => {
    expect(formatMoney(100, 'not a tag!')).toBe('€1.00');
  });
});

describe('centsFromEuros', () => {
  it('reads what a person types, with a comma or a dot, into whole cents', () => {
    expect(centsFromEuros('12,5')).toBe(1250);
    expect(centsFromEuros(' 12.50 ')).toBe(1250);
    expect(centsFromEuros('100')).toBe(10000);
    expect(centsFromEuros('0,01')).toBe(1);
    expect(centsFromEuros(7)).toBe(700);
  });

  it('reads thousands separators, the Spanish way and the English way', () => {
    expect(centsFromEuros('1.000')).toBe(100000);
    expect(centsFromEuros('1.000,50')).toBe(100050);
    expect(centsFromEuros('1,000.50')).toBe(100050);
    expect(centsFromEuros('1.000.000')).toBe(100000000);
    expect(centsFromEuros('2 500')).toBe(250000);
  });

  it('empty is no bound', () => {
    expect(centsFromEuros('')).toBeUndefined();
    expect(centsFromEuros('   ')).toBeUndefined();
    expect(centsFromEuros(null)).toBeUndefined();
    expect(centsFromEuros(undefined)).toBeUndefined();
  });

  it('text that is not an amount, or a negative one, is no bound either (the filter just does not apply)', () => {
    expect(centsFromEuros('abc')).toBeUndefined();
    expect(centsFromEuros('-5')).toBeUndefined();
    expect(centsFromEuros('1.2.3')).toBeUndefined();
    expect(centsFromEuros('1.0000')).toBeUndefined();
    expect(centsFromEuros('12,345')).toBe(1234500);
  });

  it('tells blank, an amount and what it cannot read apart', () => {
    expect(readEuros('  ')).toEqual({ kind: 'blank' });
    expect(readEuros('1.000,5')).toEqual({ kind: 'amount', cents: 100050 });
    expect(readEuros('mil')).toEqual({ kind: 'invalid' });
  });
});

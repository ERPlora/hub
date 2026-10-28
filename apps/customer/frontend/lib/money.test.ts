// Money on the customer screens (WORKBOOK «Reglas que no se rompen»: money travels in minor units; the
// screen paints and the «Spent» filter is typed in the business's currency, flow customer-business-currency).
// One formatter and one parser, so no page formats or scales by hand. The decimals are the server's
// (`currency_decimals`), never the browser's Intl; while the business has not answered, a figure without a
// symbol, never the euro by default.
import { describe, expect, it } from 'vitest';

import { centsFromAmount, formatMoney, type Money, readAmount, recordMoney } from './money';

const EUR: Money = { currency: 'EUR', decimals: 2 };
const PLN: Money = { currency: 'PLN', decimals: 2 };
const JPY: Money = { currency: 'JPY', decimals: 0 };
const KWD: Money = { currency: 'KWD', decimals: 3 };
/** CLDR (the server) counts the forint in fillér; the browser's Intl gives it none. */
const HUF: Money = { currency: 'HUF', decimals: 2 };

const plain = (text: string) => text.replace(/\s/g, ' ');

describe('formatMoney', () => {
  it('paints minor units in the money it is given, in the page language', () => {
    expect(plain(formatMoney(123456, 'en', PLN))).toBe('zł 1,234.56');
    expect(plain(formatMoney(123456, 'es', PLN))).toBe('1234,56 zł');
    expect(formatMoney(123456, 'en', EUR)).toBe('€1,234.56');
    expect(plain(formatMoney(123456, 'es', EUR))).toBe('1234,56 €');
    expect(formatMoney(0, 'en', EUR)).toBe('€0.00');
  });

  it('uses the decimals the server counts, never the browser’s', () => {
    expect(formatMoney(1250, 'en', JPY)).toBe('¥1,250');
    expect(plain(formatMoney(12500, 'en', KWD))).toBe('KWD 12.500');
    expect(plain(formatMoney(123456, 'en', HUF))).toBe('Ft 1,234.56');
  });

  it('is a figure without a symbol while the money is unknown, never euros', () => {
    expect(formatMoney(123456, 'en')).toBe('1,234.56');
    expect(plain(formatMoney(123456, 'es'))).toBe('1234,56');
    expect(formatMoney(123456, 'en')).not.toContain('€');
  });

  it('says «—» when there is nothing to show', () => {
    expect(formatMoney(null, 'en', PLN)).toBe('—');
    expect(formatMoney(undefined, 'es')).toBe('—');
  });

  it('falls back to English for a language tag it cannot read', () => {
    expect(plain(formatMoney(100, 'not a tag!', PLN))).toBe('zł 1.00');
  });
});

describe('recordMoney', () => {
  it('is the record’s own currency with its decimals: a record is never rewritten', () => {
    expect(recordMoney({ currency: 'EUR', currency_decimals: 2 }, PLN)).toEqual(EUR);
    expect(recordMoney({ currency: 'JPY', currency_decimals: 0 }, PLN)).toEqual(JPY);
  });

  it('is the business’s when the record has no currency of its own', () => {
    expect(recordMoney({ currency: '', currency_decimals: null }, PLN)).toEqual(PLN);
    expect(recordMoney({ currency: '', currency_decimals: null })).toBeUndefined();
    expect(recordMoney({ currency: 7, currency_decimals: null }, PLN)).toEqual(PLN);
  });
});

describe('centsFromAmount', () => {
  it('reads a decimal comma or point into minor units', () => {
    expect(centsFromAmount('12,5', PLN)).toBe(1250);
    expect(centsFromAmount(' 12.50 ', PLN)).toBe(1250);
    expect(centsFromAmount('100', PLN)).toBe(10000);
    expect(centsFromAmount('0,01', PLN)).toBe(1);
    expect(centsFromAmount(7, PLN)).toBe(700);
  });

  it('reads the thousands either convention writes', () => {
    expect(centsFromAmount('1.000', PLN)).toBe(100000);
    expect(centsFromAmount('1.000,50', PLN)).toBe(100050);
    expect(centsFromAmount('1,000.50', PLN)).toBe(100050);
    expect(centsFromAmount('1.000.000', PLN)).toBe(100000000);
    expect(centsFromAmount('2 500', PLN)).toBe(250000);
    expect(centsFromAmount('12,345', PLN)).toBe(1234500);
  });

  it('takes the currency’s code or symbol around the figure, not another currency’s', () => {
    expect(centsFromAmount('12,50 zł', PLN)).toBe(1250);
    expect(centsFromAmount('PLN 12.50', PLN)).toBe(1250);
    expect(centsFromAmount('zł12', PLN)).toBe(1200);
    expect(centsFromAmount('12,50 €', PLN)).toBeUndefined();
    expect(centsFromAmount('12,50 €', EUR)).toBe(1250);
  });

  it('counts the decimals of the money: none in yen, three in dinars', () => {
    expect(centsFromAmount('1250', JPY)).toBe(1250);
    expect(centsFromAmount('1.250', JPY)).toBe(1250);
    expect(centsFromAmount('¥1,250', JPY)).toBe(1250);
    expect(centsFromAmount('12,5', JPY)).toBeUndefined();
    expect(centsFromAmount('12,5', KWD)).toBe(12500);
    expect(centsFromAmount('0,125', KWD)).toBe(125);
    expect(centsFromAmount('1.000,125', KWD)).toBe(1000125);
  });

  it('reads two decimals and no symbol while the money is unknown', () => {
    expect(centsFromAmount('12,5')).toBe(1250);
    expect(centsFromAmount('1.000')).toBe(100000);
    expect(centsFromAmount('12,50 €')).toBeUndefined();
  });

  it('gives no bound for blank', () => {
    expect(centsFromAmount('', PLN)).toBeUndefined();
    expect(centsFromAmount('   ', PLN)).toBeUndefined();
    expect(centsFromAmount(null, PLN)).toBeUndefined();
    expect(centsFromAmount(undefined, PLN)).toBeUndefined();
  });

  it('gives no bound for what is not an amount', () => {
    expect(centsFromAmount('abc', PLN)).toBeUndefined();
    expect(centsFromAmount('-5', PLN)).toBeUndefined();
    expect(centsFromAmount('1.2.3', PLN)).toBeUndefined();
    expect(centsFromAmount('1.0000', PLN)).toBeUndefined();
    expect(centsFromAmount('1,234', KWD)).toBe(1234000);
  });
});

describe('readAmount', () => {
  it('tells blank, an amount and what it cannot read apart', () => {
    expect(readAmount('  ', PLN)).toEqual({ kind: 'blank' });
    expect(readAmount('1.000,5', PLN)).toEqual({ kind: 'amount', cents: 100050 });
    expect(readAmount('mil', PLN)).toEqual({ kind: 'invalid' });
    expect(readAmount('12,5', JPY)).toEqual({ kind: 'invalid' });
  });
});

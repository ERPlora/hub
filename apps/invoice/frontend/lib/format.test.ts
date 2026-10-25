// How the invoice screens paint numbers and days (WORKBOOK «Para quien lo mantiene»: money travels in
// signed cents, quantities and rates as decimal strings, days as `YYYY-MM-DD`). One place turns them into
// text in the page's language with `Intl`, and the amounts a person types into cents: no page formats by
// hand.
import { describe, expect, it } from 'vitest';

import { centsFromAmount, formatDate, formatMoney, formatPercent, formatQuantity, formatUnitPrice, plain, typedRate } from './format';

// An invoice's money: its currency and the decimals the server counts it in (`currency_decimals`).
const EUR = { currency: 'EUR', decimals: 2 };
const PLN = { currency: 'PLN', decimals: 2 };
const JPY = { currency: 'JPY', decimals: 0 };
const HUF = { currency: 'HUF', decimals: 2 };

/** Intl puts a narrow no-break space before «€» and «%» in Spanish: compared as a plain space. */
const spaced = (text: string) => plain(text);

describe('formatUnitPrice', () => {
  it('writes a unit price (cents with two decimals) with two decimals, up to four when it has them', () => {
    expect(plain(formatUnitPrice('1000.00', 'en', EUR))).toBe('€10.00');
    expect(plain(formatUnitPrice('82.64', 'en', EUR))).toBe('€0.8264');
    expect(plain(formatUnitPrice('41.30', 'es', EUR))).toBe('0,413 €');
    expect(plain(formatUnitPrice(1250, 'es', EUR))).toBe('12,50 €');
    expect(formatUnitPrice(null, 'en', EUR)).toBe('—');
  });

  it('groups the thousands from four digits on, in Spanish too (hub#1090)', () => {
    expect(plain(formatUnitPrice('123456.00', 'es', EUR))).toBe('1.234,56 €');
    expect(plain(formatUnitPrice('123456.78', 'es', EUR))).toBe('1.234,5678 €');
    expect(plain(formatUnitPrice('1234567.00', 'es', EUR))).toBe('12.345,67 €');
    expect(plain(formatUnitPrice('123456.78', 'en', EUR))).toBe('€1,234.5678');
  });
});

describe('formatMoney', () => {
  it('paints cents as euros in the page language, a rectifying amount with its sign', () => {
    expect(formatMoney(123456, 'en', EUR)).toBe('€1,234.56');
    expect(formatMoney(0, 'en', EUR)).toBe('€0.00');
    expect(formatMoney(-350, 'en', EUR)).toBe('-€3.50');
    expect(spaced(formatMoney(-1210, 'es', EUR))).toBe('-12,10 €');
  });

  it('groups the thousands from four digits on, in Spanish too (hub#1090)', () => {
    // Spanish CLDR only groups from five digits on (minimumGroupingDigits 2): «1234,56 €» beside
    // «12.345,67 €», and unlike Carts, Price lists and Payments, which paint «1.234,56 €».
    expect(spaced(formatMoney(123456, 'es', EUR))).toBe('1.234,56 €');
    expect(spaced(formatMoney(1234567, 'es', EUR))).toBe('12.345,67 €');
    expect(spaced(formatMoney(-123456, 'es', EUR))).toBe('-1.234,56 €');
    expect(formatMoney(1234567, 'en', EUR)).toBe('€12,345.67');
  });

  it('a missing amount is a dash, never «NaN», and a broken language falls back to English', () => {
    expect(formatMoney(null, 'en', EUR)).toBe('—');
    expect(formatMoney(undefined, 'es', EUR)).toBe('—');
    expect(formatMoney(100, 'not a tag!', EUR)).toBe('€1.00');
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

describe('typedRate', () => {
  it('is a rate of the server as a person types it in the page’s language; none is blank', () => {
    expect(typedRate('21.00', 'en')).toBe('21');
    expect(typedRate('7.00', 'es')).toBe('7');
    expect(typedRate('9.50', 'es')).toBe('9,5');
    expect(typedRate('9.50', 'en')).toBe('9.5');
    expect(typedRate(null, 'es')).toBe('');
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

describe('centsFromAmount', () => {
  it('reads what a person types, with a comma or a dot, into whole cents', () => {
    expect(centsFromAmount('12,5')).toBe(1250);
    expect(centsFromAmount(' 12.50 ')).toBe(1250);
    expect(centsFromAmount('0,01')).toBe(1);
    expect(centsFromAmount(7)).toBe(700);
  });

  it('empty, negative or not an amount is nothing', () => {
    expect(centsFromAmount('')).toBeUndefined();
    expect(centsFromAmount(null)).toBeUndefined();
    expect(centsFromAmount('12,345')).toBeUndefined();
    expect(centsFromAmount('-3')).toBeUndefined();
    expect(centsFromAmount('abc')).toBeUndefined();
  });
});

describe('money of the invoice’s currency (flow business-currency)', () => {
  it('writes an invoice of a business in Poland in zlotys, and the yen without decimals', () => {
    expect(plain(formatMoney(12100, 'en', PLN))).toBe('zł 121.00');
    expect(plain(formatMoney(12100, 'pl', PLN))).toBe('121,00 zł');
    expect(plain(formatMoney(12100, 'en', JPY))).toBe('¥12,100');
    expect(plain(formatUnitPrice('82.64', 'en', PLN))).toBe('zł 0.8264');
    // The forint keeps the two decimals the server counts it in (the browser's Intl gives it none).
    expect(plain(formatMoney(123450, 'en', HUF))).toBe('Ft 1,234.50');
    expect(plain(formatUnitPrice('5000.00', 'en', JPY))).toBe('¥5,000');
  });

  it('without a currency a figure has no symbol, never the euro', () => {
    expect(plain(formatMoney(12100, 'es'))).toBe('121,00');
    expect(plain(formatMoney(123456, 'en'))).toBe('1,234.56');
    expect(plain(formatUnitPrice('82.64', 'en'))).toBe('0.8264');
  });
});

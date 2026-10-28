// How the service screens paint money, rates and dates, with the page language's own format (Intl): minor
// units in the business's currency (flow service-business-currency: its country's, with the decimals the
// server counts it in, never the browser's Intl; a figure without a symbol until it answers, never the euro by
// default), a discount in basis points as the language writes a percentage, and a day.
import { describe, expect, it } from 'vitest';

import { decimalMark, formatDate, formatMoney, formatPercentBp, type Money, moneyDecimals, percentFieldText, readPercentBp } from './format';

const plain = (text: string) => text.replace(/[  ]/g, ' ');

const EUR: Money = { currency: 'EUR', decimals: 2 };
const PLN: Money = { currency: 'PLN', decimals: 2 };
/** The yen, without minor units on the server. */
const JPY: Money = { currency: 'JPY', decimals: 0 };
/** The forint: two decimals on the server, none in the browser's Intl. */
const HUF: Money = { currency: 'HUF', decimals: 2 };

describe('formatMoney', () => {
  it('paints whole cents as euros in the page language', () => {
    expect(plain(formatMoney(2250, 'es', EUR))).toBe('22,50 €');
    expect(formatMoney(123456, 'es', EUR)).toMatch(/^1\.?234,56\s€$/);
    expect(formatMoney(2250, 'en', EUR)).toBe('€22.50');
    expect(formatMoney(0, 'en', EUR)).toBe('€0.00');
  });

  it('paints minor units in the business currency it is given', () => {
    expect(plain(formatMoney(2250, 'es', PLN))).toBe('22,50 zł');
    expect(plain(formatMoney(2250, 'en', PLN))).toBe('zł 22.50');
    expect(formatMoney(1500, 'en', JPY)).toBe('¥1,500');
  });

  it('counts the minor units with the decimals the server gives, never Intl’s', () => {
    expect(plain(formatMoney(1350, 'es', HUF))).toBe('13,50 Ft');
  });

  it('is a figure without a symbol until the business answers: never a euro by default', () => {
    expect(formatMoney(2250, 'es')).toBe('22,50');
    expect(formatMoney(2250, 'en')).toBe('22.50');
  });
});

describe('moneyDecimals', () => {
  it('is the business currency’s, two while it is unknown', () => {
    expect([moneyDecimals(PLN), moneyDecimals(JPY), moneyDecimals(undefined)]).toEqual([2, 0, 2]);
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

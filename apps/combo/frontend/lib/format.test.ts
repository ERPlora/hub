// How the combo screens paint money (pages never format by hand): the business's currency (its country's, with the
// decimals the server counts it in, never the browser's Intl) in the page language, and a supplement with its sign
// (+2,00 zł, −0,50 zł), as the till shows it. Until the business answers, only a dash: never the euro
// by default.
import { describe, expect, it } from 'vitest';

import { formatDelta, formatMoney, type Money, moneyDecimals } from './format';

const plain = (text: string) => text.replace(/[\u00a0\u202f]/g, ' ');

const EUR: Money = { currency: 'EUR', decimals: 2 };
const PLN: Money = { currency: 'PLN', decimals: 2 };
/** The yen, without minor units on the server. */
const JPY: Money = { currency: 'JPY', decimals: 0 };
/** The forint: two decimals on the server, none in the browser's Intl. */
const HUF: Money = { currency: 'HUF', decimals: 2 };

describe('formatMoney', () => {
  it('paints minor units in the business currency, in the page language', () => {
    expect(plain(formatMoney(1350, 'es', EUR))).toBe('13,50 €');
    expect(formatMoney(1350, 'en', EUR)).toBe('€13.50');
    expect(plain(formatMoney(1350, 'es', PLN))).toBe('13,50 zł');
    expect(plain(formatMoney(1350, 'en', PLN))).toBe('zł 13.50');
  });

  it('counts the minor units with the decimals the server gives, never Intl’s', () => {
    expect(formatMoney(1350, 'en', JPY)).toBe('¥1,350');
    expect(plain(formatMoney(1350, 'es', HUF))).toBe('13,50 Ft');
  });

  it('is a dash until the business answers: never a euro by default', () => {
    expect(formatMoney(1350, 'es')).toBe('—');
    expect(formatMoney(1350, 'en')).toBe('—');
  });

  // hub#654: Spanish CLDR waits for five digits; every screen of the Hub groups from four on.
  it('groups the thousands from four digits on, in every language, with or without the currency', () => {
    expect(plain(formatMoney(123456, 'es', EUR))).toBe('1.234,56 €');
    expect(plain(formatMoney(123456789, 'es', EUR))).toBe('1.234.567,89 €');
    expect(formatMoney(123456, 'en', EUR)).toBe('€1,234.56');
    expect(plain(formatMoney(1500, 'es', JPY))).toBe('1.500 ¥');
    expect(formatMoney(123456, 'es')).toBe('—');
    expect(plain(formatMoney(99999, 'es', EUR))).toBe('999,99 €');
  });
});

describe('formatDelta', () => {
  it('paints a supplement with its sign in the business currency, and nothing for none', () => {
    expect(plain(formatDelta(200, 'es', PLN))).toBe('+2,00 zł');
    expect(plain(formatDelta(-50, 'en', PLN))).toBe('-zł 0.50');
    expect(formatDelta(200, 'en', JPY)).toBe('+¥200');
    expect(formatDelta(0, 'en', PLN)).toBe('');
  });

  it('groups the thousands of a supplement like any other amount (hub#654)', () => {
    expect(plain(formatDelta(123456, 'es', EUR))).toBe('+1.234,56 €');
    expect(plain(formatDelta(-123456, 'es', EUR))).toBe('-1.234,56 €');
    expect(formatDelta(123456, 'es')).toBe('—');
    expect(plain(formatDelta(-123456, 'en', PLN))).toBe('-zł 1,234.56');
  });

  it('is only a dash without a sign until the business answers', () => {
    expect(formatDelta(200, 'es')).toBe('—');
    expect(formatDelta(-50, 'en')).toBe('—');
  });
});

describe('moneyDecimals', () => {
  it('is the business currency’s, two while it is unknown', () => {
    expect(moneyDecimals(PLN)).toBe(2);
    expect(moneyDecimals(JPY)).toBe(0);
    expect(moneyDecimals(undefined)).toBe(2);
  });
});

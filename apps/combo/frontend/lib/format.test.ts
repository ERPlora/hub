// How the combo screens paint money (pages never format by hand): the business's currency (its country's, with the
// decimals the server counts it in, never the browser's Intl) in the page language, and a supplement with its sign
// (+2,00 zł, −0,50 zł), as the till shows it. Until the business answers, a figure without a symbol: never the euro
// by default.
import { describe, expect, it } from 'vitest';

import { decimalMark, formatDelta, formatMoney, type Money, moneyDecimals } from './format';

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

  it('is a figure without a symbol until the business answers: never a euro by default', () => {
    expect(formatMoney(1350, 'es')).toBe('13,50');
    expect(formatMoney(1350, 'en')).toBe('13.50');
  });
});

describe('formatDelta', () => {
  it('paints a supplement with its sign in the business currency, and nothing for none', () => {
    expect(plain(formatDelta(200, 'es', PLN))).toBe('+2,00 zł');
    expect(plain(formatDelta(-50, 'en', PLN))).toBe('-zł 0.50');
    expect(formatDelta(200, 'en', JPY)).toBe('+¥200');
    expect(formatDelta(0, 'en', PLN)).toBe('');
  });

  it('carries its sign and no symbol until the business answers', () => {
    expect(formatDelta(200, 'es')).toBe('+2,00');
    expect(formatDelta(-50, 'en')).toBe('-0.50');
  });
});

describe('moneyDecimals', () => {
  it('is the business currency’s, two while it is unknown', () => {
    expect([moneyDecimals(PLN), moneyDecimals(JPY), moneyDecimals(undefined)]).toEqual([2, 0, 2]);
  });
});

describe('decimalMark', () => {
  it('is the comma in Spanish and the point in English', () => {
    expect([decimalMark('es'), decimalMark('en')]).toEqual([',', '.']);
  });
});

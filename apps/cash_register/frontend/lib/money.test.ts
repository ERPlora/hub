// Money of the drawer screens: the server keeps whole cents; a person reads money in the page's language. What is
// typed in a window or in the list's amount filters is read by the platform (`MoneyInput`, `parseMoney`; hub#1160,
// hub#1196, money-fields.test.ts). Money is in the business's currency (flow business-currency): the one the screen
// passes, and until it is known only a dash, never the euro.
import { describe, expect, it } from 'vitest';

import { formatFace, formatMoney, formatSignedMoney, plain } from './money';

// The business's money as `base.business.get` says it: the currency and the decimals the server counts it in.
const EUR = { currency: 'EUR', decimals: 2 };
const PLN = { currency: 'PLN', decimals: 2 };
const JPY = { currency: 'JPY', decimals: 0 };
const KWD = { currency: 'KWD', decimals: 3 };
const HUF = { currency: 'HUF', decimals: 2 };

describe('formatMoney', () => {
  it('writes cents as money of the business in the reader’s language; nothing is «—»', () => {
    expect(plain(formatMoney(15050, 'es', EUR))).toBe('150,50 €');
    expect(plain(formatMoney(15050, 'en', EUR))).toBe('€150.50');
    expect(plain(formatMoney(-450, 'es', EUR))).toBe('-4,50 €');
    expect(formatMoney(null, 'es')).toBe('—');
    expect(formatMoney(undefined, 'es')).toBe('—');
  });

  // hub#653: Spanish CLDR waits for five digits; every screen of the Hub groups from four on.
  it('groups the thousands from four digits on, in every language, with or without the currency', () => {
    expect(plain(formatMoney(123456, 'es', EUR))).toBe('1.234,56 €');
    expect(plain(formatMoney(123456789, 'es', EUR))).toBe('1.234.567,89 €');
    expect(plain(formatMoney(123456, 'en', EUR))).toBe('€1,234.56');
    expect(plain(formatMoney(-123456, 'es', EUR))).toBe('-1.234,56 €');
    expect(plain(formatMoney(123456, 'es'))).toBe('—');
    expect(plain(formatMoney(99999, 'es', EUR))).toBe('999,99 €');
    expect(plain(formatSignedMoney(123456, 'es', EUR))).toBe('+1.234,56 €');
  });

  it('a difference carries its sign: a surplus «+», a shortage «-», zero none', () => {
    expect(plain(formatSignedMoney(510, 'es', EUR))).toBe('+5,10 €');
    expect(plain(formatSignedMoney(-490, 'es', EUR))).toBe('-4,90 €');
    expect(plain(formatSignedMoney(0, 'es', EUR))).toBe('0,00 €');
    expect(formatSignedMoney(null, 'es')).toBe('—');
  });
});

describe('formatFace', () => {
  // The old count printed «500 €», not «500,00 €» (Square and Lightspeed: «$100», «20 KWD»): a note or coin
  // of whole units prints without decimals, a coin of cents with them; in the currency of the business.
  it('a whole face value prints without decimals, a coin of cents with them', () => {
    expect(plain(formatFace('500', 'es', EUR))).toBe('500 €');
    expect(plain(formatFace('2', 'en', EUR))).toBe('€2');
    expect(plain(formatFace('0.50', 'es', EUR))).toBe('0,50 €');
    expect(plain(formatFace('0.05', 'en', EUR))).toBe('€0.05');
    expect(plain(formatFace('10000', 'en', JPY))).toBe('¥10,000');
    expect(plain(formatFace('0.005', 'en', KWD))).toBe('KWD 0.005');
  });

  // hub#653: a note of four digits (the forint's and the yen's) reads like any other amount of the screen.
  it('groups the thousands of a note from four digits on', () => {
    expect(plain(formatFace('5000', 'es', HUF))).toBe('5.000 Ft');
    expect(plain(formatFace('1000', 'es', JPY))).toBe('1.000 ¥');
    expect(plain(formatFace('5000', 'es'))).toBe('5.000');
  });
});

describe('money of other currencies', () => {
  it('writes minor units with the decimals of their currency', () => {
    expect(plain(formatMoney(5003, 'en', JPY))).toBe('¥5,003');
    expect(plain(formatMoney(515, 'en', KWD))).toBe('KWD 0.515');
    expect(plain(formatMoney(10015, 'es', EUR))).toBe('100,15 €');
  });
});

describe('money of the business (flow business-currency)', () => {
  it('writes money in the currency it is given, with the symbol a till there writes: zlotys in Poland, yen without decimals', () => {
    expect(plain(formatMoney(15050, 'es', PLN))).toBe('150,50 zł');
    expect(plain(formatMoney(15050, 'pl', PLN))).toBe('150,50 zł');
    expect(plain(formatSignedMoney(-490, 'en', PLN))).toBe('-zł 4.90');
    expect(plain(formatFace('5', 'pl', PLN))).toBe('5 zł');
    expect(plain(formatMoney(5003, 'es', JPY))).toBe('5.003 ¥');
  });

  it('takes the decimals the server counts the money in, not the browser’s: the forint keeps its two', () => {
    // Intl gives the forint no decimals; the server (CLDR, Babel) two: 123450 is 1,234.50 Ft, never 123,450 Ft.
    expect(plain(formatMoney(123450, 'en', HUF))).toBe('Ft 1,234.50');
    expect(plain(formatMoney(123450, 'hu', HUF))).toBe('1 234,50 Ft');
  });

  it('until the business’s currency is known money and its sign are only a dash, never the euro', () => {
    expect(plain(formatMoney(15050, 'es'))).toBe('—');
    expect(plain(formatMoney(15050, 'en'))).toBe('—');
    expect(plain(formatSignedMoney(510, 'es'))).toBe('—');
    expect(plain(formatSignedMoney(-490, 'en'))).toBe('—');
    expect(plain(formatFace('500', 'es'))).toBe('500');
    expect(plain(formatFace('0.50', 'en'))).toBe('0.50');
  });
});

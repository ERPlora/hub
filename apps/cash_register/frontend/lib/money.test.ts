// Money of the drawer screens: the server keeps whole cents; a person reads money in the page's language and
// types it as she reads it («150,50», «1.250,50»). One gate reads every money field: empty, an amount,
// or why it is not one (garbage, negative, or «1.250», which reads two ways). Money is in the business's currency
// (flow business-currency): the one the screen passes, and until it is known a figure without a symbol, never the euro.
import { describe, expect, it } from 'vitest';

import { formatFace, formatMoney, formatSignedMoney, moneyFieldText, moneyRefusal, plain, readMoney } from './money';

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

  it('a difference carries its sign: a surplus «+», a shortage «-», zero none', () => {
    expect(plain(formatSignedMoney(510, 'es', EUR))).toBe('+5,10 €');
    expect(plain(formatSignedMoney(-490, 'es', EUR))).toBe('-4,90 €');
    expect(plain(formatSignedMoney(0, 'es', EUR))).toBe('0,00 €');
    expect(formatSignedMoney(null, 'es')).toBe('—');
  });

  it('prefills a field ungrouped, with the reader’s decimal sign', () => {
    expect(moneyFieldText(125050, 'es')).toBe('1250,50');
    expect(moneyFieldText(125050, 'en')).toBe('1250.50');
    expect(moneyFieldText(700, 'es')).toBe('7,00');
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
});

describe('readMoney', () => {
  it('empty is no amount', () => {
    expect(readMoney('  ')).toEqual({ ok: true, cents: null });
  });

  it('reads whole and decimal amounts with a comma or a point', () => {
    expect(readMoney('150')).toEqual({ ok: true, cents: 15000 });
    expect(readMoney('150,5')).toEqual({ ok: true, cents: 15050 });
    expect(readMoney('150.50')).toEqual({ ok: true, cents: 15050 });
    expect(readMoney(' 0,05 € ', 2, 'EUR')).toEqual({ ok: true, cents: 5 });
  });

  it('reads money as this very screen writes it: grouped thousands with their decimals', () => {
    expect(readMoney('1.250,50')).toEqual({ ok: true, cents: 125050 });
    expect(readMoney('1,250.50')).toEqual({ ok: true, cents: 125050 });
    expect(readMoney('1.250.000')).toEqual({ ok: true, cents: 125000000 });
  });

  it('«1.250» reads two ways: it asks which one', () => {
    expect(readMoney('1.250')).toEqual({ ok: false, reason: 'ambiguous', typed: '1.250', grouped: 125000, decimal: 125 });
    expect(readMoney('12,345')).toEqual({ ok: false, reason: 'ambiguous', typed: '12,345', grouped: 1234500, decimal: 1235 });
  });

  it('refuses a negative amount and anything that is no amount', () => {
    expect(readMoney('-12')).toEqual({ ok: false, reason: 'negative' });
    for (const garbage of ['abc', '1..2', '12€50', '1,2,3', '12.5.0']) {
      expect(readMoney(garbage), garbage).toEqual({ ok: false, reason: 'notAnAmount' });
    }
  });
});

describe('moneyRefusal', () => {
  const t = (key: string, named?: Record<string, unknown>) => (named ? `${key} ${JSON.stringify(named)}` : key);

  it('says why a field is not an amount, in the app’s words; an amount or empty says nothing', () => {
    expect(moneyRefusal(readMoney('12'), t, 'es')).toBeNull();
    expect(moneyRefusal(readMoney(''), t, 'es')).toBeNull();
    expect(moneyRefusal(readMoney('abc'), t, 'es')).toBe('cash_register.money.notAnAmount');
    expect(moneyRefusal(readMoney('-1'), t, 'es')).toBe('cash_register.money.negative');
    expect(plain(moneyRefusal(readMoney('1.250'), t, 'es', EUR) ?? '')).toBe(
      'cash_register.money.ambiguous {"typed":"1.250","grouped":"1250,00 €","decimal":"1,25 €"}',
    );
  });
});

describe('money of other currencies', () => {
  it('writes minor units with the decimals of their currency', () => {
    expect(plain(formatMoney(5003, 'en', JPY))).toBe('¥5,003');
    expect(plain(formatMoney(515, 'en', KWD))).toBe('KWD 0.515');
    expect(plain(formatMoney(10015, 'es', EUR))).toBe('100,15 €');
  });

  it('reads what is typed with the decimals of the currency', () => {
    expect(readMoney('5003', 0)).toEqual({ ok: true, cents: 5003 });
    expect(readMoney('1.250', 0)).toEqual({ ok: true, cents: 1250 });
    expect(readMoney('12,5', 0)).toEqual({ ok: false, reason: 'notAnAmount' });
    expect(readMoney('0,515', 3)).toEqual({ ok: true, cents: 515 });
    expect(moneyFieldText(5003, 'en', 0)).toBe('5003');
  });
});

describe('money of the business (flow business-currency)', () => {
  it('writes money in the currency it is given, with the symbol a till there writes: zlotys in Poland, yen without decimals', () => {
    expect(plain(formatMoney(15050, 'es', PLN))).toBe('150,50 zł');
    expect(plain(formatMoney(15050, 'pl', PLN))).toBe('150,50 zł');
    expect(plain(formatSignedMoney(-490, 'en', PLN))).toBe('-zł 4.90');
    expect(plain(formatFace('5', 'pl', PLN))).toBe('5 zł');
    expect(plain(formatMoney(5003, 'es', JPY))).toBe('5003 ¥');
  });

  it('takes the decimals the server counts the money in, not the browser’s: the forint keeps its two', () => {
    // Intl gives the forint no decimals; the server (CLDR, Babel) two: 123450 is 1,234.50 Ft, never 123,450 Ft.
    expect(plain(formatMoney(123450, 'en', HUF))).toBe('Ft 1,234.50');
    expect(plain(formatMoney(123450, 'hu', HUF))).toBe('1234,50 Ft');
  });

  it('until the business’s currency is known a figure has no symbol, never the euro', () => {
    expect(plain(formatMoney(15050, 'es'))).toBe('150,50');
    expect(plain(formatMoney(15050, 'en'))).toBe('150.50');
    expect(plain(formatSignedMoney(510, 'es'))).toBe('+5,10');
    expect(plain(formatFace('500', 'es'))).toBe('500');
    expect(plain(formatFace('0.50', 'en'))).toBe('0.50');
  });

  it('reads an amount typed with the business’s currency around it, and not with another one', () => {
    expect(readMoney('150,50 zł', 2, 'PLN')).toEqual({ ok: true, cents: 15050 });
    expect(readMoney('PLN 7', 2, 'PLN')).toEqual({ ok: true, cents: 700 });
    expect(readMoney('150 €', 2, 'PLN')).toEqual({ ok: false, reason: 'notAnAmount' });
    expect(readMoney('150 €')).toEqual({ ok: false, reason: 'notAnAmount' });
  });
});

// A money field of the service forms (price, closed price, a professional's own price) reads what a
// person types or pastes (WORKBOOK SERVICE-F01): «2,20», «1.234,56», or the screen's own «2,20 €» or
// «2,20 zł», into whole minor units of the business's currency (flow service-business-currency: «1500» is
// 1500 yen in Japan and 1500,00 € in Spain), with the server's rules (with both marks the rightmost one is
// the decimal one; never more than the currency's decimals; never negative). The business's code or symbol
// is noise, another currency's is not, nor the euro while the business is unknown. «1.250» can be read two
// ways and says so; anything else that is not an amount says it is not. On leaving the field it is
// rewritten in the page's format, ungrouped, with the currency's decimals.
import { describe, expect, it } from 'vitest';

import type { Money } from './format';
import { moneyFieldText, normaliseMoneyText, parseMoney } from './money';

const EUR: Money = { currency: 'EUR', decimals: 2 };
const PLN: Money = { currency: 'PLN', decimals: 2 };
/** The yen, without minor units on the server. */
const JPY: Money = { currency: 'JPY', decimals: 0 };
/** The Kuwaiti dinar, with three. */
const KWD: Money = { currency: 'KWD', decimals: 3 };

describe('parseMoney', () => {
  it('reads the decimal comma and the decimal point', () => {
    expect(parseMoney('2,20', EUR)).toEqual({ ok: true, cents: 220 });
    expect(parseMoney('2.2', EUR)).toEqual({ ok: true, cents: 220 });
    expect(parseMoney('12', EUR)).toEqual({ ok: true, cents: 1200 });
    expect(parseMoney('0,05', EUR)).toEqual({ ok: true, cents: 5 });
  });

  // flow service-business-currency: the same «1500» is the minor units of each business's currency.
  it('reads a figure in the minor units of the business currency: 1500 yen, 1500,00 € or zł', () => {
    expect(parseMoney('1500', JPY)).toEqual({ ok: true, cents: 1500 });
    expect(parseMoney('1500', EUR)).toEqual({ ok: true, cents: 150000 });
    expect(parseMoney('1500', PLN)).toEqual({ ok: true, cents: 150000 });
    expect(parseMoney('1,5', KWD)).toEqual({ ok: true, cents: 1500 });
  });

  it('reads at most the currency’s decimals, as the server counts them', () => {
    expect(parseMoney('12,5', JPY)).toEqual({ ok: false, reason: 'not_amount' });
    expect(parseMoney('1.250', JPY)).toEqual({ ok: true, cents: 1250 });
    expect(parseMoney('1,250', KWD)).toEqual({ ok: true, cents: 1250 });
    expect(parseMoney('0,505', PLN)).toEqual({ ok: false, reason: 'not_amount' });
  });

  it('with both marks the rightmost one is the decimal one', () => {
    expect(parseMoney('1.234,56', EUR)).toEqual({ ok: true, cents: 123456 });
    expect(parseMoney('1,234.56', EUR)).toEqual({ ok: true, cents: 123456 });
    expect(parseMoney('12.345.678,90', EUR)).toEqual({ ok: true, cents: 1234567890 });
  });

  it('reads what is pasted from the screen: the business currency’s sign or code and the spaces around', () => {
    expect(parseMoney('2,20 €', EUR)).toEqual({ ok: true, cents: 220 });
    expect(parseMoney('€2.20', EUR)).toEqual({ ok: true, cents: 220 });
    expect(parseMoney(' 1.234,56 € ', EUR)).toEqual({ ok: true, cents: 123456 });
    expect(parseMoney('3 EUR', EUR)).toEqual({ ok: true, cents: 300 });
    expect(parseMoney('22,50 zł', PLN)).toEqual({ ok: true, cents: 2250 });
    expect(parseMoney('PLN 22.50', PLN)).toEqual({ ok: true, cents: 2250 });
    expect(parseMoney('¥1,500', JPY)).toEqual({ ok: true, cents: 1500 });
  });

  it('does not take another currency’s sign as noise, nor the euro while the business is unknown', () => {
    expect(parseMoney('22,50 €', PLN)).toEqual({ ok: false, reason: 'not_amount' });
    expect(parseMoney('22,50 €')).toEqual({ ok: false, reason: 'not_amount' });
    expect(parseMoney('22,50')).toEqual({ ok: true, cents: 2250 });
  });

  it('a repeated single mark groups thousands', () => {
    expect(parseMoney('1.234.567', EUR)).toEqual({ ok: true, cents: 123456700 });
    expect(parseMoney('1,234,567', EUR)).toEqual({ ok: true, cents: 123456700 });
    expect(parseMoney('1.234.567', JPY)).toEqual({ ok: true, cents: 1234567 });
  });

  it('an empty field is no amount at all, not zero', () => {
    expect(parseMoney('', EUR)).toEqual({ ok: true, cents: null });
    expect(parseMoney('   ', EUR)).toEqual({ ok: true, cents: null });
    expect(parseMoney(' zł ', PLN)).toEqual({ ok: true, cents: null });
  });

  it('«1.250» can be read as 1.250 € or 1,25 €: says so with both readings', () => {
    expect(parseMoney('1.250', EUR)).toEqual({ ok: false, reason: 'ambiguous', grouped: 125000, decimal: 125 });
    expect(parseMoney('1,250', PLN)).toEqual({ ok: false, reason: 'ambiguous', grouped: 125000, decimal: 125 });
  });

  it('three decimals that a price cannot have are thousands', () => {
    expect(parseMoney('1.234', EUR)).toEqual({ ok: true, cents: 123400 });
  });

  it('what is not an amount says so: letters, more decimals than the currency’s, broken groups, too many digits', () => {
    for (const text of ['abc', '2,2,2', '2.2345', '1.23.4', '12a', '2,', '-', '1234567890123456']) {
      expect(parseMoney(text, EUR), text).toEqual({ ok: false, reason: 'not_amount' });
    }
  });

  it('a negative amount says it cannot be negative (the old screen’s own message)', () => {
    expect(parseMoney('-2', EUR)).toEqual({ ok: false, reason: 'negative' });
    expect(parseMoney(' -12,50 €', EUR)).toEqual({ ok: false, reason: 'negative' });
    expect(parseMoney('-1500', JPY)).toEqual({ ok: false, reason: 'negative' });
    expect(parseMoney('-x', EUR)).toEqual({ ok: false, reason: 'not_amount' });
  });
});

describe('moneyFieldText', () => {
  it('writes minor units for the field in the page format and the currency’s decimals, ungrouped', () => {
    expect(moneyFieldText(123456, 'es', EUR)).toBe('1234,56');
    expect(moneyFieldText(123456, 'en', PLN)).toBe('1234.56');
    expect(moneyFieldText(5, 'es', EUR)).toBe('0,05');
    expect(moneyFieldText(0, 'es', EUR)).toBe('0,00');
    expect(moneyFieldText(1500, 'es', JPY)).toBe('1500');
    expect(moneyFieldText(1250, 'es', KWD)).toBe('1,250');
    expect(moneyFieldText(null, 'es', EUR)).toBe('');
  });

  it('writes two decimals while the business is unknown', () => {
    expect(moneyFieldText(2250, 'es')).toBe('22,50');
  });
});

describe('normaliseMoneyText', () => {
  it('rewrites a readable amount in the page format and leaves anything else as typed', () => {
    expect(normaliseMoneyText('2.2', 'es', EUR)).toBe('2,20');
    expect(normaliseMoneyText('1.234,5 €', 'en', EUR)).toBe('1234.50');
    expect(normaliseMoneyText('22,5 zł', 'en', PLN)).toBe('22.50');
    expect(normaliseMoneyText('1500', 'en', JPY)).toBe('1500');
    expect(normaliseMoneyText('1.250', 'es', EUR)).toBe('1.250');
    expect(normaliseMoneyText('abc', 'es', EUR)).toBe('abc');
    expect(normaliseMoneyText('', 'es', EUR)).toBe('');
  });
});

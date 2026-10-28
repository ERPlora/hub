// The amount of a payment (and the amount filter of the list) reads what a
// person types or pastes (WORKBOOK PAYMENT-F02; the old pm#521): «2,20», «1.234,56»,
// «€2.20» or the screen's own «2,20 €», into whole minor units of the business's money, with the server's rules
// (with both marks the rightmost one is the decimal one; never more decimals than the currency's; never negative).
// Only that currency's code or symbol is noise around the figure: «13,50 €» in Poland is not an amount; while the
// business is unknown, a figure without a symbol with two decimals. «1.250» can be read two ways and says so;
// anything else that is not an amount says it is not. On leaving the field it is rewritten in the page's format,
// ungrouped.
import { describe, expect, it } from 'vitest';

import { moneyFieldText, normaliseMoneyText, parseMoney } from './money';

const EUR = { currency: 'EUR', decimals: 2 };
const PLN = { currency: 'PLN', decimals: 2 };
const JPY = { currency: 'JPY', decimals: 0 };
const KWD = { currency: 'KWD', decimals: 3 };

describe('parseMoney', () => {
  it('reads the decimal comma and the decimal point', () => {
    expect(parseMoney('2,20')).toEqual({ ok: true, cents: 220 });
    expect(parseMoney('2.2')).toEqual({ ok: true, cents: 220 });
    expect(parseMoney('12')).toEqual({ ok: true, cents: 1200 });
    expect(parseMoney('0,05')).toEqual({ ok: true, cents: 5 });
  });

  it('with both marks the rightmost one is the decimal one', () => {
    expect(parseMoney('1.234,56')).toEqual({ ok: true, cents: 123456 });
    expect(parseMoney('1,234.56')).toEqual({ ok: true, cents: 123456 });
    expect(parseMoney('12.345.678,90')).toEqual({ ok: true, cents: 1234567890 });
  });

  it('in a business in Poland, the złoty’s code or symbol is noise and the euro’s is not an amount', () => {
    expect(parseMoney('12,50 zł', PLN)).toEqual({ ok: true, cents: 1250 });
    expect(parseMoney('PLN 1.234,56', PLN)).toEqual({ ok: true, cents: 123456 });
    expect(parseMoney('13,50 €', PLN)).toEqual({ ok: false, reason: 'not_amount' });
    expect(parseMoney('3 EUR', PLN)).toEqual({ ok: false, reason: 'not_amount' });
  });

  it('reads with the decimals of the business’s currency: none in yen, three in Kuwaiti dinars', () => {
    expect(parseMoney('150', JPY)).toEqual({ ok: true, cents: 150 });
    expect(parseMoney('1.250', JPY)).toEqual({ ok: true, cents: 1250 });
    expect(parseMoney('1,5', JPY)).toEqual({ ok: false, reason: 'not_amount' });
    expect(parseMoney('1,5', KWD)).toEqual({ ok: true, cents: 1500 });
    expect(parseMoney('2.125', KWD)).toEqual({ ok: true, cents: 2125 });
  });

  it('while the business is unknown, a figure without a symbol, with two decimals; never a euro', () => {
    expect(parseMoney('12,50')).toEqual({ ok: true, cents: 1250 });
    expect(parseMoney('12,50 €')).toEqual({ ok: false, reason: 'not_amount' });
    expect(parseMoney('€12.50')).toEqual({ ok: false, reason: 'not_amount' });
  });

  it('reads what is pasted from the screen: the euro sign or code and the spaces around, in a business in euros', () => {
    expect(parseMoney('2,20 €', EUR)).toEqual({ ok: true, cents: 220 });
    expect(parseMoney('€2.20', EUR)).toEqual({ ok: true, cents: 220 });
    expect(parseMoney(' 1.234,56 € ', EUR)).toEqual({ ok: true, cents: 123456 });
    expect(parseMoney('3 EUR', EUR)).toEqual({ ok: true, cents: 300 });
  });

  it('a repeated single mark groups thousands', () => {
    expect(parseMoney('1.234.567')).toEqual({ ok: true, cents: 123456700 });
    expect(parseMoney('1,234,567')).toEqual({ ok: true, cents: 123456700 });
  });

  it('an empty field is no amount at all, not zero', () => {
    expect(parseMoney('')).toEqual({ ok: true, cents: null });
    expect(parseMoney('   ')).toEqual({ ok: true, cents: null });
  });

  it('«1.250» can be read as 1.250 € or 1,25 €: says so with both readings', () => {
    expect(parseMoney('1.250')).toEqual({ ok: false, reason: 'ambiguous', grouped: 125000, decimal: 125 });
    expect(parseMoney('1,250')).toEqual({ ok: false, reason: 'ambiguous', grouped: 125000, decimal: 125 });
  });

  it('three decimals that a price cannot have are thousands', () => {
    expect(parseMoney('1.234')).toEqual({ ok: true, cents: 123400 });
  });

  it('what is not an amount says so: letters, more than two decimals, broken groups', () => {
    for (const text of ['abc', '2,2,2', '2.2345', '1.23.4', '12a', '2,', '-']) {
      expect(parseMoney(text), text).toEqual({ ok: false, reason: 'not_amount' });
    }
  });

  it('a negative amount says it cannot be negative (the old screen’s own message)', () => {
    expect(parseMoney('-2')).toEqual({ ok: false, reason: 'negative' });
    expect(parseMoney(' -12,50 €', EUR)).toEqual({ ok: false, reason: 'negative' });
    expect(parseMoney('-12,50 zł', PLN)).toEqual({ ok: false, reason: 'negative' });
  });
});

describe('moneyFieldText', () => {
  it('writes cents for the field in the page format, ungrouped', () => {
    expect(moneyFieldText(123456, 'es')).toBe('1234,56');
    expect(moneyFieldText(123456, 'en')).toBe('1234.56');
    expect(moneyFieldText(5, 'es')).toBe('0,05');
    expect(moneyFieldText(0, 'es')).toBe('0,00');
    expect(moneyFieldText(null, 'es')).toBe('');
  });

  it('with the decimals of the business’s currency', () => {
    expect(moneyFieldText(150, 'es', JPY)).toBe('150');
    expect(moneyFieldText(1250, 'es', KWD)).toBe('1,250');
    expect(moneyFieldText(1250, 'en', PLN)).toBe('12.50');
  });
});

describe('normaliseMoneyText', () => {
  it('rewrites a readable amount in the page format and leaves anything else as typed', () => {
    expect(normaliseMoneyText('2.2', 'es')).toBe('2,20');
    expect(normaliseMoneyText('1.234,5 €', 'en', EUR)).toBe('1234.50');
    expect(normaliseMoneyText('12,5 zł', 'en', PLN)).toBe('12.50');
    expect(normaliseMoneyText('150', 'es', JPY)).toBe('150');
    expect(normaliseMoneyText('13,50 €', 'es', PLN)).toBe('13,50 €');
    expect(normaliseMoneyText('1.250', 'es')).toBe('1.250');
    expect(normaliseMoneyText('abc', 'es')).toBe('abc');
    expect(normaliseMoneyText('', 'es')).toBe('');
  });
});

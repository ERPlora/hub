// The supplement field of the option form (MODIFIER-F04) reads what a person types or pastes: «1,50»,
// «1.234,56», «zł1.50» or the screen's own «+1,50 zł», into whole minor units of the business's currency
// with their sign (a supplement may be a discount: «-0,50»), with the server's rules (with both marks the
// rightmost one is the decimal one; never more decimals than the currency has: none in yen). «1.250» can
// be read two ways and says so; anything else that is not an amount says it is not. While the currency
// is unknown, two decimals and no symbol to take away (never a euro by default). On leaving the field it
// is rewritten in the page's format, ungrouped.
import { describe, expect, it } from 'vitest';

import type { Money } from './format';
import { moneyFieldText, normaliseMoneyText, parseMoney } from './money';

const EUR: Money = { currency: 'EUR', decimals: 2 };
const PLN: Money = { currency: 'PLN', decimals: 2 };
const JPY: Money = { currency: 'JPY', decimals: 0 };

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

  it('reads what is pasted from the screen: the business’s currency sign or code and the spaces around', () => {
    expect(parseMoney('2,20 €', EUR)).toEqual({ ok: true, cents: 220 });
    expect(parseMoney('€2.20', EUR)).toEqual({ ok: true, cents: 220 });
    expect(parseMoney(' 1.234,56 € ', EUR)).toEqual({ ok: true, cents: 123456 });
    expect(parseMoney('3 EUR', EUR)).toEqual({ ok: true, cents: 300 });
    expect(parseMoney('1,50 zł', PLN)).toEqual({ ok: true, cents: 150 });
    expect(parseMoney('zł 1.50', PLN)).toEqual({ ok: true, cents: 150 });
    expect(parseMoney('+1,00 PLN', PLN)).toEqual({ ok: true, cents: 100 });
    expect(parseMoney('-0,50 zł', PLN)).toEqual({ ok: true, cents: -50 });
  });

  it('another currency’s sign is not an amount of the business’s: a euro one in Poland, a symbol before it is known', () => {
    expect(parseMoney('1,50 €', PLN)).toEqual({ ok: false, reason: 'not_amount' });
    expect(parseMoney('3 EUR', PLN)).toEqual({ ok: false, reason: 'not_amount' });
    expect(parseMoney('1,50 €')).toEqual({ ok: false, reason: 'not_amount' });
    expect(parseMoney('1,50')).toEqual({ ok: true, cents: 150 });
  });

  it('with the currency’s decimals, the server’s: in yen «150» is 150 yen and «1,5» is not an amount', () => {
    expect(parseMoney('150', JPY)).toEqual({ ok: true, cents: 150 });
    expect(parseMoney('¥150', JPY)).toEqual({ ok: true, cents: 150 });
    expect(parseMoney('-20', JPY)).toEqual({ ok: true, cents: -20 });
    expect(parseMoney('1.250', JPY)).toEqual({ ok: true, cents: 1250 });
    for (const text of ['1,5', '1,50', '0.5']) {
      expect(parseMoney(text, JPY), text).toEqual({ ok: false, reason: 'not_amount' });
    }
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

  it('a supplement may be a discount: a leading minus (or the screen\'s plus) carries its sign', () => {
    expect(parseMoney('-2')).toEqual({ ok: true, cents: -200 });
    expect(parseMoney(' -12,50 €', EUR)).toEqual({ ok: true, cents: -1250 });
    expect(parseMoney('−0,50')).toEqual({ ok: true, cents: -50 });
    expect(parseMoney('+1,00 €', EUR)).toEqual({ ok: true, cents: 100 });
    expect(parseMoney('-1.250')).toEqual({ ok: false, reason: 'ambiguous', grouped: -125000, decimal: -125 });
    expect(parseMoney('--2')).toEqual({ ok: false, reason: 'not_amount' });
  });
});

describe('moneyFieldText', () => {
  it('writes cents for the field in the page format, ungrouped', () => {
    expect(moneyFieldText(123456, 'es')).toBe('1234,56');
    expect(moneyFieldText(123456, 'en')).toBe('1234.56');
    expect(moneyFieldText(5, 'es')).toBe('0,05');
    expect(moneyFieldText(0, 'es')).toBe('0,00');
    expect(moneyFieldText(-50, 'es')).toBe('-0,50');
    expect(moneyFieldText(-1234, 'en')).toBe('-12.34');
    expect(moneyFieldText(null, 'es')).toBe('');
  });

  it('with the decimals of the business’s currency: none in yen', () => {
    expect(moneyFieldText(150, 'es', JPY)).toBe('150');
    expect(moneyFieldText(-20, 'en', JPY)).toBe('-20');
    expect(moneyFieldText(250, 'es', PLN)).toBe('2,50');
  });
});

describe('normaliseMoneyText', () => {
  it('rewrites a readable amount in the page format and leaves anything else as typed', () => {
    expect(normaliseMoneyText('2.2', 'es')).toBe('2,20');
    expect(normaliseMoneyText('1.234,5 €', 'en', EUR)).toBe('1234.50');
    expect(normaliseMoneyText('+1,00 zł', 'es', PLN)).toBe('1,00');
    expect(normaliseMoneyText('1.250', 'es', JPY)).toBe('1250');
    expect(normaliseMoneyText('1.250', 'es')).toBe('1.250');
    expect(normaliseMoneyText('abc', 'es')).toBe('abc');
    expect(normaliseMoneyText('-0.5', 'es')).toBe('-0,50');
    expect(normaliseMoneyText('', 'es')).toBe('');
  });
});

// The supplement field of the option form (MODIFIER-F04) reads what a person types or pastes: «1,50»,
// «1.234,56», «€1.50» or the screen's own «+1,50 €», into whole cents with their sign (a supplement may
// be a discount: «-0,50»), with the server's rules (with both marks the rightmost one is the decimal
// one; never more than two decimals). «1.250» can be read two ways and says so; anything else that is
// not an amount says it is not. On leaving the field it is rewritten in the page's format, ungrouped.
import { describe, expect, it } from 'vitest';

import { moneyFieldText, normaliseMoneyText, parseMoney } from './money';

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

  it('reads what is pasted from the screen: the euro sign or code and the spaces around', () => {
    expect(parseMoney('2,20 €')).toEqual({ ok: true, cents: 220 });
    expect(parseMoney('€2.20')).toEqual({ ok: true, cents: 220 });
    expect(parseMoney(' 1.234,56 € ')).toEqual({ ok: true, cents: 123456 });
    expect(parseMoney('3 EUR')).toEqual({ ok: true, cents: 300 });
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
    expect(parseMoney(' -12,50 €')).toEqual({ ok: true, cents: -1250 });
    expect(parseMoney('−0,50')).toEqual({ ok: true, cents: -50 });
    expect(parseMoney('+1,00 €')).toEqual({ ok: true, cents: 100 });
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
});

describe('normaliseMoneyText', () => {
  it('rewrites a readable amount in the page format and leaves anything else as typed', () => {
    expect(normaliseMoneyText('2.2', 'es')).toBe('2,20');
    expect(normaliseMoneyText('1.234,5 €', 'en')).toBe('1234.50');
    expect(normaliseMoneyText('1.250', 'es')).toBe('1.250');
    expect(normaliseMoneyText('abc', 'es')).toBe('abc');
    expect(normaliseMoneyText('-0.5', 'es')).toBe('-0,50');
    expect(normaliseMoneyText('', 'es')).toBe('');
  });
});

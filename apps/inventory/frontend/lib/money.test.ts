// A money field reads what a person types or pastes (WORKBOOK INVENTORY-F01): «2,20», «1.234,56»,
// «€2.20» or the screen's own «2,20 €», into whole cents, with the server's rules (with both marks the
// rightmost one is the decimal one; never more than two decimals; never negative). «1.250» can be
// read two ways and says so; anything else that is not an amount says it is not. On leaving the
// field it is rewritten in the page's format, ungrouped.
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
    expect(parseMoney('2,20 €', 'EUR')).toEqual({ ok: true, cents: 220 });
    expect(parseMoney('€2.20', 'EUR')).toEqual({ ok: true, cents: 220 });
    expect(parseMoney(' 1.234,56 € ', 'EUR')).toEqual({ ok: true, cents: 123456 });
    expect(parseMoney('3 EUR', 'EUR')).toEqual({ ok: true, cents: 300 });
  });

  // flow business-currency: the business's currency around the figure is noise; another one is not.
  it('reads the zloty a business in Poland pastes, and not the euro', () => {
    expect(parseMoney('12,50 zł', 'PLN')).toEqual({ ok: true, cents: 1250 });
    expect(parseMoney('PLN 12.50', 'PLN')).toEqual({ ok: true, cents: 1250 });
    expect(parseMoney('12,50 €', 'PLN')).toEqual({ ok: false, reason: 'not_amount' });
    expect(parseMoney('12,50 €')).toEqual({ ok: false, reason: 'not_amount' });
  });

  it('reads the yen without decimals: a mark only groups', () => {
    expect(parseMoney('1.250', 'JPY')).toEqual({ ok: true, cents: 1250 });
    expect(parseMoney('¥1,210', 'JPY')).toEqual({ ok: true, cents: 1210 });
    expect(parseMoney('12,5', 'JPY')).toEqual({ ok: false, reason: 'not_amount' });
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

  it('what is not an amount says so: letters, negatives, more than two decimals, broken groups', () => {
    for (const text of ['abc', '-2', '2,2,2', '2.2345', '1.23.4', '12a', '2,']) {
      expect(parseMoney(text), text).toEqual({ ok: false, reason: 'not_amount' });
    }
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
});

describe('normaliseMoneyText', () => {
  it('rewrites a readable amount in the page format and leaves anything else as typed', () => {
    expect(normaliseMoneyText('2.2', 'es', 'EUR')).toBe('2,20');
    expect(normaliseMoneyText('1.234,5 €', 'en', 'EUR')).toBe('1234.50');
    expect(normaliseMoneyText('1.250', 'es', 'EUR')).toBe('1.250');
    expect(normaliseMoneyText('abc', 'es', 'EUR')).toBe('abc');
    expect(normaliseMoneyText('', 'es', 'EUR')).toBe('');
  });
});

describe('moneyFieldText of other currencies', () => {
  it('writes the decimals of the business’s currency, none for the yen', () => {
    expect(moneyFieldText(1250, 'es', 'PLN')).toBe('12,50');
    expect(moneyFieldText(1210, 'en', 'JPY')).toBe('1210');
    expect(normaliseMoneyText('1.210', 'en', 'JPY')).toBe('1210');
  });
});

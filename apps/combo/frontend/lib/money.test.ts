// A money field of the combo forms (a menu's closed price, a choice's supplement): what a person types
// or pastes, read into whole minor units of the business's currency. Its code or its sign and the spaces are
// noise, another currency's are not; with both marks the rightmost one is the decimal one; at most the
// currency's decimals; «1.250» can be 1.250 zł or 1,25 zł, and is not guessed. A price is never negative; a
// supplement may be (a cheaper substitution).
import { describe, expect, it } from 'vitest';

import type { Money } from './format';
import { moneyFieldText, normaliseMoneyText, parseMoney } from './money';

const EUR: Money = { currency: 'EUR', decimals: 2 };
const PLN: Money = { currency: 'PLN', decimals: 2 };
const JPY: Money = { currency: 'JPY', decimals: 0 };
const KWD: Money = { currency: 'KWD', decimals: 3 };

describe('parseMoney', () => {
  it('reads either decimal mark and the business currency’s code or sign', () => {
    expect(parseMoney('13,50', { money: PLN })).toEqual({ ok: true, cents: 1350 });
    expect(parseMoney('13,50 zł', { money: PLN })).toEqual({ ok: true, cents: 1350 });
    expect(parseMoney('PLN 13.5', { money: PLN })).toEqual({ ok: true, cents: 1350 });
    expect(parseMoney('13.5 €', { money: EUR })).toEqual({ ok: true, cents: 1350 });
    expect(parseMoney('1.234,56', { money: PLN })).toEqual({ ok: true, cents: 123456 });
    expect(parseMoney('12', { money: PLN })).toEqual({ ok: true, cents: 1200 });
  });

  it('does not take another currency’s sign as noise, nor the euro while the business is unknown', () => {
    expect(parseMoney('13,50 €', { money: PLN })).toEqual({ ok: false, reason: 'not_amount' });
    expect(parseMoney('13,50 €')).toEqual({ ok: false, reason: 'not_amount' });
    expect(parseMoney('13,50')).toEqual({ ok: true, cents: 1350 });
  });

  it('reads at most the currency’s decimals, as the server counts them', () => {
    expect(parseMoney('1350', { money: JPY })).toEqual({ ok: true, cents: 1350 });
    expect(parseMoney('13,5', { money: JPY })).toEqual({ ok: false, reason: 'not_amount' });
    expect(parseMoney('1.250', { money: JPY })).toEqual({ ok: true, cents: 1250 });
    expect(parseMoney('1,250', { money: KWD })).toEqual({ ok: true, cents: 1250 });
    expect(parseMoney('0,505', { money: PLN })).toEqual({ ok: false, reason: 'not_amount' });
  });

  it('reads an empty field as nothing', () => {
    expect(parseMoney('  ', { money: PLN })).toEqual({ ok: true, cents: null });
  });

  it('says when a text is not an amount', () => {
    expect(parseMoney('12a', { money: PLN })).toEqual({ ok: false, reason: 'not_amount' });
    expect(parseMoney('1,2,3', { money: PLN })).toEqual({ ok: false, reason: 'not_amount' });
    // More digits than a double keeps exact (16): not an amount, never a rounded one.
    expect(parseMoney('1234567890123456', { money: PLN })).toEqual({ ok: false, reason: 'not_amount' });
  });

  it('does not guess «1.250»: it gives both readings', () => {
    expect(parseMoney('1.250', { money: PLN })).toEqual({ ok: false, reason: 'ambiguous', grouped: 125000, decimal: 125 });
  });

  it('refuses a negative price, but reads a negative supplement', () => {
    expect(parseMoney('-1', { money: PLN })).toEqual({ ok: false, reason: 'negative' });
    expect(parseMoney('-0,50 zł', { signed: true, money: PLN })).toEqual({ ok: true, cents: -50 });
    expect(parseMoney('-50', { signed: true, money: JPY })).toEqual({ ok: true, cents: -50 });
    expect(parseMoney('-x', { signed: true, money: PLN })).toEqual({ ok: false, reason: 'not_amount' });
  });
});

describe('moneyFieldText and normaliseMoneyText', () => {
  it('writes minor units back in the page format and the currency’s decimals, ungrouped, with the sign', () => {
    expect(moneyFieldText(123456, 'es', PLN)).toBe('1234,56');
    expect(moneyFieldText(-50, 'en', PLN)).toBe('-0.50');
    expect(moneyFieldText(1350, 'es', JPY)).toBe('1350');
    expect(moneyFieldText(-50, 'en', JPY)).toBe('-50');
    expect(moneyFieldText(1250, 'es', KWD)).toBe('1,250');
    expect(moneyFieldText(null, 'es', PLN)).toBe('');
  });

  it('rewrites a readable field on leaving it and leaves the rest as typed', () => {
    expect(normaliseMoneyText('13.5', 'es', { money: PLN })).toBe('13,50');
    expect(normaliseMoneyText('13,50 zł', 'en', { money: PLN })).toBe('13.50');
    expect(normaliseMoneyText('-0.5', 'es', { signed: true, money: PLN })).toBe('-0,50');
    expect(normaliseMoneyText('150', 'en', { money: JPY })).toBe('150');
    expect(normaliseMoneyText('1.250', 'es', { money: PLN })).toBe('1.250');
  });
});

// A money field of the combo forms (a menu's closed price, a choice's supplement): what a person types
// or pastes, read into whole cents. The euro sign and spaces are noise; with both marks the rightmost
// one is the decimal one; «1.250» can be 1.250 € or 1,25 €, and is not guessed. A price is never
// negative; a supplement may be (a cheaper substitution).
import { describe, expect, it } from 'vitest';

import { moneyFieldText, normaliseMoneyText, parseMoney } from './money';

describe('parseMoney', () => {
  it('reads either decimal mark and the euro sign', () => {
    expect(parseMoney('13,50')).toEqual({ ok: true, cents: 1350 });
    expect(parseMoney('13.5 €')).toEqual({ ok: true, cents: 1350 });
    expect(parseMoney('1.234,56')).toEqual({ ok: true, cents: 123456 });
    expect(parseMoney('12')).toEqual({ ok: true, cents: 1200 });
  });

  it('reads an empty field as nothing', () => {
    expect(parseMoney('  ')).toEqual({ ok: true, cents: null });
  });

  it('says when a text is not an amount', () => {
    expect(parseMoney('12a')).toEqual({ ok: false, reason: 'not_amount' });
    expect(parseMoney('1,2,3')).toEqual({ ok: false, reason: 'not_amount' });
  });

  it('does not guess «1.250»: it gives both readings', () => {
    expect(parseMoney('1.250')).toEqual({ ok: false, reason: 'ambiguous', grouped: 125000, decimal: 125 });
  });

  it('refuses a negative price, but reads a negative supplement', () => {
    expect(parseMoney('-1')).toEqual({ ok: false, reason: 'negative' });
    expect(parseMoney('-0,50', { signed: true })).toEqual({ ok: true, cents: -50 });
    expect(parseMoney('-x', { signed: true })).toEqual({ ok: false, reason: 'not_amount' });
  });
});

describe('moneyFieldText and normaliseMoneyText', () => {
  it('writes cents back in the page format, ungrouped, with the sign', () => {
    expect(moneyFieldText(123456, 'es')).toBe('1234,56');
    expect(moneyFieldText(-50, 'en')).toBe('-0.50');
    expect(moneyFieldText(null, 'es')).toBe('');
  });

  it('rewrites a readable field on leaving it and leaves the rest as typed', () => {
    expect(normaliseMoneyText('13.5', 'es')).toBe('13,50');
    expect(normaliseMoneyText('-0.5', 'es', { signed: true })).toBe('-0,50');
    expect(normaliseMoneyText('1.250', 'es')).toBe('1.250');
  });
});

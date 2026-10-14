// The arithmetic of the charge sheet's tender (SALE-F01, F02, F03): what the keypad types, what is left
// to cover, the change and the `payments` the charge sends. Only what the person types is worked out
// here; the amount to charge is always the server's preview, and the server re-checks every leg.
import { describe, expect, it } from 'vitest';

import {
  centsToTyped,
  changeDue,
  type Leg,
  needsTendered,
  paymentsIn,
  planLeg,
  pushKey,
  remainingCents,
  type TenderMethod,
  typedCents,
} from './tender';

const CASH: TenderMethod = { id: 'm-cash', display_name: 'Cash', type: 'cash', requires_change: true };
const CARD: TenderMethod = { id: 'm-card', display_name: 'Card', type: 'card', requires_change: false };

const leg = (method: TenderMethod, amount: number, tendered = amount, id = `${method.id}-${amount}`): Leg => ({ id, method, amount, tendered });

describe('the keypad', () => {
  it('appends digits and clears with C', () => {
    expect(['1', '2', '5'].reduce(pushKey, '')).toBe('125');
    expect(pushKey('125', 'C')).toBe('');
  });

  it('takes one separator and two decimals at most (euros)', () => {
    expect(['1', '2', '.', '5', '0', '7'].reduce(pushKey, '')).toBe('12.50');
    expect(['1', '.', '.', '5'].reduce(pushKey, '')).toBe('1.5');
    expect(pushKey('', '.')).toBe('0.');
  });

  it('stops at nine characters', () => {
    expect(['1', '2', '3', '4', '5', '6', '7', '8', '9', '1'].reduce(pushKey, '')).toBe('123456789');
  });

  it('reads what it typed as cents, without float rounding', () => {
    expect(typedCents('')).toBe(0);
    expect(typedCents('12')).toBe(1200);
    expect(typedCents('12.5')).toBe(1250);
    expect(typedCents('12.05')).toBe(1205);
    expect(typedCents('0.')).toBe(0);
    expect(typedCents('19.99')).toBe(1999);
  });

  it('writes cents back as the text it reads (a leg brought back to the keypad)', () => {
    expect(centsToTyped(1250)).toBe('12.50');
    expect(centsToTyped(5)).toBe('0.05');
    expect(typedCents(centsToTyped(123456))).toBe(123456);
  });
});

describe('the legs of a split payment', () => {
  it('cash asks what was handed over; other methods charge the exact amount', () => {
    expect([needsTendered(CASH), needsTendered(CARD), needsTendered(undefined)]).toEqual([true, false, false]);
  });

  it('what is left is the total minus the legs, never below 0', () => {
    expect(remainingCents(5000, [])).toBe(5000);
    expect(remainingCents(5000, [leg(CARD, 2000), leg(CASH, 1000, 2000)])).toBe(2000);
    expect(remainingCents(5000, [leg(CARD, 6000)])).toBe(0);
  });

  it('a leg with nothing typed covers all that is left', () => {
    expect(planLeg(CARD, 0, 3000)).toEqual({ amount: 3000, tendered: 3000 });
  });

  it('a leg takes what was typed, up to what is left', () => {
    expect(planLeg(CARD, 1000, 3000)).toEqual({ amount: 1000, tendered: 1000 });
    expect(planLeg(CARD, 5000, 3000)).toEqual({ amount: 3000, tendered: 3000 });
  });

  it('cash handed over beyond what is left pays what is left and gives change', () => {
    expect(planLeg(CASH, 5000, 3000)).toEqual({ amount: 3000, tendered: 5000 });
  });

  it('nothing to take without a method or with nothing left', () => {
    expect(planLeg(undefined, 1000, 3000)).toBeUndefined();
    expect(planLeg(CASH, 1000, 0)).toBeUndefined();
  });

  it('the change comes only out of cash, never shared out', () => {
    expect(changeDue([leg(CARD, 2000), leg(CASH, 3000, 5000)])).toBe(2000);
    expect(changeDue([leg(CARD, 2000, 2500)])).toBe(0);
  });
});

describe('the payments the charge sends', () => {
  const single = { total: 4250, legs: [] as Leg[], splitting: false };

  it('cash: the method and what was handed over; the server works out the amount', () => {
    expect(paymentsIn({ ...single, method: CASH, typed: 5000 })).toEqual([{ method_id: 'm-cash', tendered: 5000 }]);
  });

  it('another method: just the method, for the exact amount', () => {
    expect(paymentsIn({ ...single, method: CARD, typed: 0 })).toEqual([{ method_id: 'm-card' }]);
  });

  it('split: one payment per leg with its amount, and what cash was handed over only when it gave change', () => {
    const legs = [leg(CARD, 2000), leg(CASH, 1250, 1250), leg(CASH, 1000, 2000)];
    expect(paymentsIn({ total: 4250, legs, splitting: true, method: CASH, typed: 0 })).toEqual([
      { method_id: 'm-card', amount: 2000 },
      { method_id: 'm-cash', amount: 1250 },
      { method_id: 'm-cash', amount: 1000, tendered: 2000 },
    ]);
  });

  it('a check worth nothing (all comps) is charged with no payment', () => {
    expect(paymentsIn({ ...single, total: 0, method: CASH, typed: 0 })).toEqual([]);
  });
});

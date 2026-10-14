// The arithmetic of the Refund window (SALE-F31), outside the component so it is tested without a DOM.
// None of it is the authority: what each tender charged, gave back and has left, and each line's units,
// come from `sale.refund.options`, and `sale.sale.refund` decides it all again. This is the PROPOSAL the
// person edits and the reason the button says «not yet» while they type:
//   - a marked line proposes its share, `round(total·min(prev+q, qty)/qty) − round(total·prev/qty)`, so
//     the refunds of a line add up to its total without drift;
//   - the amount is split across tenders by what each has left (largest remainder, ties to the earlier
//     tender), so the proposal never invents nor loses a cent;
//   - nothing marked proposes all that is left.
import { describe, expect, it } from 'vitest';

import type { LineOption, TenderOption } from '../../operations';
import {
  allocations,
  amountInput,
  attemptKey,
  lineShare,
  milli,
  parseAmount,
  pickedAmount,
  proposal,
  refundableTotal,
  refundBlock,
  refundLines,
  splitByRemaining,
  wholeLeft,
} from './refund';

const tender = (id: string, over: Partial<TenderOption> = {}): TenderOption => ({
  payment_id: id,
  position: 1,
  method_id: `m-${id}`,
  method_name: 'Cash',
  method_type: 'cash',
  charged: 1000,
  refunded: 0,
  remaining: 1000,
  refundable: true,
  reason: '',
  ...over,
});

const line = (id: string, over: Partial<LineOption> = {}): LineOption => ({
  line_id: id,
  name: 'Coffee',
  unit: 'ud',
  quantity: '1.000',
  returned: '0.000',
  left: '1.000',
  line_total: 1000,
  is_gift: false,
  ...over,
});

describe('quantities', () => {
  it('travel as decimal strings; the window counts thousandths of a unit', () => {
    expect([milli('2.000'), milli('0.532'), milli('1'), milli(3)]).toEqual([2000, 532, 1000, 3000]);
  });

  it('a stepper walks the whole units left; a weighed rest goes back whole', () => {
    expect(wholeLeft(line('a', { quantity: '3.000', returned: '1.000', left: '2.000' }))).toBe(2);
    expect(wholeLeft(line('a', { quantity: '0.532', left: '0.532' }))).toBe(0);
    expect(wholeLeft(line('a', { left: '0.000', returned: '1.000' }))).toBe(0);
  });
});

describe('lineShare', () => {
  it('prorates a line by units, rounding from its total so its refunds add up to it', () => {
    const coffee = line('a', { quantity: '3.000', left: '3.000', line_total: 1000 });
    expect(lineShare(coffee, 1000)).toBe(333);
    const rest = line('a', { quantity: '3.000', returned: '1.000', left: '2.000', line_total: 1000 });
    expect(lineShare(rest, 2000)).toBe(667);
    expect(333 + 667).toBe(1000);
  });

  it('never goes past what the line cost, and a line of nothing proposes nothing', () => {
    expect(lineShare(line('a'), 5000)).toBe(1000);
    expect(lineShare(line('a', { is_gift: true, line_total: 0 }), 1000)).toBe(0);
  });

  it('a weighed line goes back by its weight', () => {
    expect(lineShare(line('a', { quantity: '0.500', left: '0.500', line_total: 799 }), 500)).toBe(799);
  });
});

describe('splitByRemaining', () => {
  it('splits by what each tender has left, by largest remainder: no cent invented nor lost', () => {
    const split = splitByRemaining(1000, [tender('cash', { remaining: 1000 }), tender('card', { remaining: 500 })]);
    expect(split).toEqual({ cash: 667, card: 333 });
  });

  it('a tie of remainders goes to the earlier tender', () => {
    expect(splitByRemaining(3, [tender('a', { remaining: 100 }), tender('b', { remaining: 100 })])).toEqual({ a: 2, b: 1 });
  });

  it('never proposes more than is left, and nothing to a tender with nothing left', () => {
    const split = splitByRemaining(9999, [tender('a', { remaining: 700 }), tender('b', { remaining: 0, refundable: false, reason: 'already_refunded' })]);
    expect(split).toEqual({ a: 700, b: 0 });
  });

  it('a tender that cannot go back its own way still takes its share (it asks for a destination)', () => {
    const split = splitByRemaining(1000, [tender('a', { remaining: 500 }), tender('b', { remaining: 500, refundable: false, reason: 'method_unavailable' })]);
    expect(split).toEqual({ a: 500, b: 500 });
  });
});

describe('proposal', () => {
  const tenders = [tender('cash', { remaining: 600 }), tender('card', { remaining: 400 })];
  const lines = [line('a', { line_total: 400 }), line('b', { quantity: '2.000', left: '2.000', line_total: 600 })];

  it('nothing marked proposes everything that is left', () => {
    expect(refundableTotal(tenders)).toBe(1000);
    expect(proposal(tenders, lines, {})).toEqual({ cash: 600, card: 400 });
  });

  it('marked lines propose their share, split across tenders', () => {
    expect(pickedAmount(lines, { b: 1000 })).toBe(300);
    expect(proposal(tenders, lines, { b: 1000 })).toEqual({ cash: 180, card: 120 });
  });

  it('never marks more of a line than is left of it', () => {
    expect(pickedAmount(lines, { a: 5000 })).toBe(400);
    expect(pickedAmount(lines, { zzz: 1000 })).toBe(0);
  });
});

describe('amounts as typed', () => {
  it('are written with the reader’s decimal separator and no grouping, and read back the same', () => {
    expect(amountInput(123456, 'es')).toBe('1234,56');
    expect(amountInput(5, 'en')).toBe('0.05');
    expect(parseAmount('1234,56')).toBe(123456);
    expect(parseAmount('12.5')).toBe(1250);
  });

  it('blank is nothing; anything that is not an amount is not one', () => {
    expect(parseAmount('  ')).toBe(0);
    expect(Number.isNaN(parseAmount('12,5,0'))).toBe(true);
    expect(Number.isNaN(parseAmount('-3'))).toBe(true);
  });
});

describe('refundBlock', () => {
  const cash = tender('cash', { remaining: 600, method_name: 'Cash' });
  const gone = tender('gift', { position: 2, remaining: 400, method_name: 'Gift card', refundable: false, reason: 'method_unavailable' });

  it('nothing to give back', () => {
    expect(refundBlock([cash], { cash: 0 }, {}, 'x')).toEqual({ kind: 'nothing' });
  });

  it('a typed amount that is not one names its tender', () => {
    expect(refundBlock([cash], { cash: Number.NaN }, {}, 'x')).toEqual({ kind: 'invalid', tender: cash });
  });

  it('over what a tender has left: before asking where it goes', () => {
    expect(refundBlock([cash, gone], { cash: 700, gift: 100 }, {}, 'x')).toEqual({ kind: 'overCap', tender: cash, amount: 700 });
  });

  it('money on a tender that cannot go back its own way needs a destination', () => {
    expect(refundBlock([cash, gone], { cash: 100, gift: 100 }, {}, 'x')).toEqual({ kind: 'needsDestination', tender: gone });
    expect(refundBlock([cash, gone], { cash: 100, gift: 0 }, {}, 'x')).toBeNull();
    expect(refundBlock([cash, gone], { cash: 100, gift: 100 }, { gift: 'm-card' }, 'x')).toBeNull();
  });

  it('a reason is needed last', () => {
    expect(refundBlock([cash], { cash: 100 }, {}, '   ')).toEqual({ kind: 'reason' });
  });
});

describe('what travels to sale.sale.refund', () => {
  const cash = tender('cash', { position: 1, remaining: 600 });
  const gone = tender('gift', { position: 2, remaining: 400, refundable: false, reason: 'method_unavailable' });

  it('the tenders with money, in the ticket’s order, with the destination of the ones that need it', () => {
    expect(allocations([gone, cash], { cash: 250, gift: 100 }, { gift: 'm-card' })).toEqual([
      { payment_id: 'cash', amount: 250 },
      { payment_id: 'gift', amount: 100, to_method_id: 'm-card' },
    ]);
    expect(allocations([cash, gone], { cash: 250, gift: 0 }, { gift: 'm-card' })).toEqual([{ payment_id: 'cash', amount: 250 }]);
  });

  it('the marked lines with their units (never more than is left)', () => {
    const lines = [line('a'), line('b', { quantity: '3.000', returned: '1.000', left: '2.000' }), line('c')];
    expect(refundLines(lines, { b: 1000, a: 1000 })).toEqual([
      { line_id: 'a', quantity: '1.000' },
      { line_id: 'b', quantity: '1.000' },
    ]);
    expect(refundLines(lines, { b: 9000 })).toEqual([{ line_id: 'b', quantity: '2.000' }]);
  });

  it('an attempt key the server accepts, new for every attempt', () => {
    const key = attemptKey('0192f0aa-0000-7000-8000-000000000001');
    expect(key).toMatch(/^refund-0192f0aa-0000-7000-8000-000000000001-[A-Za-z0-9-]+$/);
    expect(key.length).toBeLessThanOrEqual(128);
    expect(attemptKey('s1')).not.toBe(attemptKey('s1'));
  });
});

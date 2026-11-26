// What «Record tip» and «Adjust» send: the amount as typed is read in the business's money, and only what the server
// takes travels; an amount that cannot be read stays on screen, said under its field.
import { describe, expect, it } from 'vitest';

import type { TipOut } from '../operations';
import { adjustInput, recordInput } from './tipInput';

const EURO = { currency: 'EUR', decimals: 2 };
const TIP = { id: 't1', amount: 250, member_id: 'm-bea' } as TipOut;

describe('recordInput', () => {
  it('of a sale: its number as typed without spaces, its payment method and the amount in cents', () => {
    expect(recordInput({ target: 'sale', sale: ' 20261125-0007 ', methodId: 'm-card', amount: '2,50' }, EURO)).toEqual({
      input: { sale: '20261125-0007', method_id: 'm-card', amount: 250 },
    });
  });

  it('to the pool: only the amount, which the server takes as cash', () => {
    expect(recordInput({ target: 'pool', sale: '20261125-0007', methodId: 'm-card', amount: '5' }, EURO)).toEqual({
      input: { pool: true, amount: 500 },
    });
  });

  it('leaves out a sale or a method not written, for the server to say which is missing', () => {
    expect(recordInput({ target: 'sale', sale: '  ', methodId: '', amount: '1' }, EURO)).toEqual({ input: { amount: 100 } });
  });

  it.each(['', 'abc', '-2', '0'])('an amount that is not a tip (%j) is said under its field and nothing is sent', (amount) => {
    expect(recordInput({ target: 'pool', sale: '', methodId: '', amount }, EURO)).toEqual({ errors: { amount: 'tip.form.amountInvalid' } });
  });
});

describe('adjustInput', () => {
  it('sends only the amount that changed, with the reason as typed', () => {
    expect(adjustInput(TIP, { amount: '3,00', memberId: 'm-bea', reason: ' wrong amount ' }, EURO)).toEqual({
      input: { id: 't1', amount: 300, reason: ' wrong amount ' },
    });
  });

  it('sends only the person who changed', () => {
    expect(adjustInput(TIP, { amount: '2,50', memberId: 'm-carla', reason: 'her table' }, EURO)).toEqual({
      input: { id: 't1', member_id: 'm-carla', reason: 'her table' },
    });
  });

  it('with nothing changed sends only the reason, for the server to ask what changes', () => {
    expect(adjustInput(TIP, { amount: '2,50', memberId: null, reason: 'x' }, EURO)).toEqual({ input: { id: 't1', reason: 'x' } });
  });

  it('an amount that cannot be read is said under its field', () => {
    expect(adjustInput(TIP, { amount: 'dos', memberId: null, reason: 'x' }, EURO)).toEqual({ errors: { amount: 'tip.form.amountInvalid' } });
  });
});

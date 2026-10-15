// Why «Charge» cannot charge yet (SALE-F01, F03, F04, F05), one reason at a time and in the old screen's
// order: the customer the business requires, the invoice recipient, cash over the legal limit, what a
// split still has to cover, cash with nothing tendered, cash short. The server refuses the same cases
// whatever the screen says; this only spares the trip and says it before the tap.
import { describe, expect, it } from 'vitest';

import { type BlockState, chargeBlock } from './blocks';
import type { Leg, TenderMethod } from './tender';

const CASH: TenderMethod = { id: 'm-cash', display_name: 'Cash', type: 'cash', requires_change: true };
const CARD: TenderMethod = { id: 'm-card', display_name: 'Card', type: 'card', requires_change: false };

const READY: BlockState = {
  requireCustomer: false,
  hasCustomer: false,
  documentType: 'ticket',
  recipientComplete: false,
  total: 4250,
  cashLimit: 100000,
  method: CASH,
  typed: 5000,
  splitting: false,
  legs: [],
};

const leg = (method: TenderMethod, amount: number, tendered = amount): Leg => ({ id: `${method.id}-${amount}`, method, amount, tendered });

describe('chargeBlock', () => {
  it('nothing blocks a ticket paid in cash with enough handed over, or by card', () => {
    expect(chargeBlock(READY)).toBeNull();
    expect(chargeBlock({ ...READY, method: CARD, typed: 0 })).toBeNull();
  });

  it('cash: nothing typed asks for the amount tendered; short says it does not cover the total', () => {
    expect(chargeBlock({ ...READY, typed: 0 })).toEqual({ kind: 'tenderedMissing' });
    expect(chargeBlock({ ...READY, typed: 4000 })).toEqual({ kind: 'tenderedShort' });
    expect(chargeBlock({ ...READY, typed: 4250 })).toBeNull();
  });

  it('a check worth nothing asks for no cash', () => {
    expect(chargeBlock({ ...READY, total: 0, typed: 0 })).toBeNull();
  });

  it('split: what is left to cover blocks, with its amount, until it reaches 0', () => {
    expect(chargeBlock({ ...READY, splitting: true, typed: 0 })).toEqual({ kind: 'remaining', amount: 4250 });
    expect(chargeBlock({ ...READY, splitting: true, legs: [leg(CARD, 2000)] })).toEqual({ kind: 'remaining', amount: 2250 });
    expect(chargeBlock({ ...READY, splitting: true, legs: [leg(CARD, 2000), leg(CASH, 2250, 3000)] })).toBeNull();
  });

  it('over the cash limit, cash blocks: the method chosen or any cash leg', () => {
    const big = { ...READY, total: 120000, typed: 120000 };
    expect(chargeBlock(big)).toEqual({ kind: 'cashLimit', limit: 100000 });
    expect(chargeBlock({ ...big, method: CARD })).toBeNull();
    expect(chargeBlock({ ...big, method: CARD, splitting: true, legs: [leg(CARD, 20000), leg(CASH, 100000)] })).toEqual({ kind: 'cashLimit', limit: 100000 });
    expect(chargeBlock({ ...big, cashLimit: null })).toBeNull();
  });

  it('the limit looks at the whole operation: a part under it of a check over it blocks cash', () => {
    expect(chargeBlock({ ...READY, total: 4250, operationTotal: 120000 })).toEqual({ kind: 'cashLimit', limit: 100000 });
    expect(chargeBlock({ ...READY, total: 4250, operationTotal: 120000, method: CARD })).toBeNull();
    expect(chargeBlock({ ...READY, total: 4250, operationTotal: 9000 })).toBeNull();
  });

  it('an invoice without its three details blocks, before any tender reason', () => {
    expect(chargeBlock({ ...READY, documentType: 'invoice', typed: 0 })).toEqual({ kind: 'recipient' });
    expect(chargeBlock({ ...READY, documentType: 'invoice', recipientComplete: true })).toBeNull();
  });

  it('an invoice whose tax ID does not check, or a foreign one without its kind of document, blocks too', () => {
    const invoice = { ...READY, documentType: 'invoice' as const, recipientComplete: true };
    expect(chargeBlock({ ...invoice, recipientIssue: 'taxIdInvalid' })).toEqual({ kind: 'taxIdInvalid' });
    expect(chargeBlock({ ...invoice, recipientIssue: 'idTypeRequired' })).toEqual({ kind: 'idTypeRequired' });
    // A ticket declares no recipient: nothing to check.
    expect(chargeBlock({ ...READY, recipientIssue: 'taxIdInvalid' })).toBeNull();
  });

  it('a business that requires a customer blocks without one, before anything else', () => {
    expect(chargeBlock({ ...READY, requireCustomer: true, documentType: 'invoice', typed: 0 })).toEqual({ kind: 'customerRequired' });
    expect(chargeBlock({ ...READY, requireCustomer: true, hasCustomer: true })).toBeNull();
  });
});

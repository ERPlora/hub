// The lines of a manual invoice as the form keeps them (what is typed) and as `invoice.invoice.create`
// takes them: the quantity as a decimal with a dot, the price (VAT not included) in cents, the VAT %.
// A line is ready with a description, a quantity above zero, a price and a rate; a price that is not an amount
// is said with its line number before anything is sent.
import { describe, expect, it } from 'vitest';

import { blankLine, type DraftLine, linePayload, linesReady, unreadablePrice } from './lines';

const line = (over: Partial<DraftLine> = {}): DraftLine => ({ ...blankLine(1, '21'), description: 'Course', price: '12,50', ...over });

describe('manual invoice lines', () => {
  it('a blank line is one unit at the rate it is given (the territory’s general one), with nothing written', () => {
    expect(blankLine(3, '7')).toEqual({ uid: 3, description: '', quantity: '1', price: '', taxRate: '7' });
    expect(blankLine(3)).toEqual({ uid: 3, description: '', quantity: '1', price: '', taxRate: '' });
  });

  it('is ready with a description, a quantity above zero, a price and a rate', () => {
    expect(linesReady([line()])).toBe(true);
    expect(linesReady([line({ description: ' ' })])).toBe(false);
    expect(linesReady([line({ quantity: '0' })])).toBe(false);
    expect(linesReady([line({ quantity: 'x' })])).toBe(false);
    expect(linesReady([line({ price: '' })])).toBe(false);
    expect(linesReady([line({ taxRate: ' ' })])).toBe(false);
    expect(linesReady([])).toBe(false);
  });

  it('travels with the quantity as a dotted decimal, the price in cents and the rate', () => {
    expect(linePayload(line({ quantity: '1,5', taxRate: '10' }))).toEqual({ description: 'Course', quantity: '1.5', unit_price: 1250, tax_rate: '10' });
  });

  it('names the first line whose price is not an amount', () => {
    expect(unreadablePrice([line(), line({ price: '12,345' }), line({ price: 'abc' })])).toBe(2);
    expect(unreadablePrice([line()])).toBeNull();
  });
});

// A quantity field (stock, threshold, received, counted) reads «2,5», «0.532» or «3» into the exact
// decimal the API takes, with the server's rules: at most three decimals, never negative, with both
// marks the rightmost one is the decimal one. Whether it fits the unit's step is the server's to
// say (409 with its field). The count's «Difference» is exact too: counted − current, no floats.
import { describe, expect, it } from 'vitest';

import { quantityDifference, readQuantity } from './quantity';

describe('readQuantity', () => {
  it('reads the decimal comma or point into the API decimal', () => {
    expect(readQuantity('2,5')).toEqual({ ok: true, value: '2.5' });
    expect(readQuantity('0.532')).toEqual({ ok: true, value: '0.532' });
    expect(readQuantity(' 3 ')).toEqual({ ok: true, value: '3' });
    expect(readQuantity('1.234,5')).toEqual({ ok: true, value: '1234.5' });
  });

  it('an empty field is no quantity', () => {
    expect(readQuantity('')).toEqual({ ok: true, value: null });
  });

  it('what is not a quantity says so: negative, four decimals, letters, two commas', () => {
    for (const text of ['-1', '0,0001', 'x', '1,2,3']) expect(readQuantity(text), text).toEqual({ ok: false });
  });
});

describe('quantityDifference', () => {
  it('is counted − current, exact and signed', () => {
    expect(quantityDifference('7', '5.000')).toBe('2');
    expect(quantityDifference('4.5', '5.000')).toBe('-0.5');
    expect(quantityDifference('0.1', '0.200')).toBe('-0.1');
    expect(quantityDifference('3', '3.000')).toBe('0');
    expect(quantityDifference('10', '-2.250')).toBe('12.25');
  });
});

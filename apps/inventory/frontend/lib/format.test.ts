// How the inventory screens paint money, counts, quantities and tax rates, all with the page
// language's own number format (Intl): euros from cents, counts grouped as the language groups them,
// quantities exact and ungrouped without trailing zeros (as the server's CSV writes them: 2,5 · 3 ·
// 0,532), a movement's quantity with its sign, and a rate as the language writes a percentage.
import { describe, expect, it } from 'vitest';

import { formatCount, formatMoney, formatPercent, formatQuantity, formatSignedQuantity } from './format';

describe('formatMoney', () => {
  it('paints whole cents as euros in the page language', () => {
    expect(formatMoney(220, 'es')).toMatch(/^2,20\s€$/);
    expect(formatMoney(123456, 'es')).toMatch(/^1\.?234,56\s€$/);
    expect(formatMoney(220, 'en')).toBe('€2.20');
    expect(formatMoney(0, 'en')).toBe('€0.00');
  });
});

describe('formatQuantity', () => {
  it('is exact: no trailing zeros, the language decimal mark, never grouped', () => {
    expect(formatQuantity('2.500', 'es')).toBe('2,5');
    expect(formatQuantity('2.500', 'en')).toBe('2.5');
    expect(formatQuantity('3.000', 'es')).toBe('3');
    expect(formatQuantity('0.532', 'es')).toBe('0,532');
    expect(formatQuantity('12345.000', 'es')).toBe('12345');
    expect(formatQuantity('-4.250', 'es')).toBe('-4,25');
    expect(formatQuantity(7, 'en')).toBe('7');
  });

  it('never invents a figure from what is not one', () => {
    expect(formatQuantity('abc', 'es')).toBe('abc');
    expect(formatQuantity('', 'es')).toBe('');
  });
});

describe('formatSignedQuantity', () => {
  it('puts a plus on what came in and keeps the minus of what went out', () => {
    expect(formatSignedQuantity('2.000', 'es')).toBe('+2');
    expect(formatSignedQuantity('-1.500', 'es')).toBe('-1,5');
    expect(formatSignedQuantity('0.000', 'es')).toBe('0');
  });
});

describe('formatPercent', () => {
  it('paints a rate as the language writes a percentage', () => {
    expect(formatPercent('21.00', 'es')).toMatch(/^21\s%$/);
    expect(formatPercent('5.20', 'es')).toMatch(/^5,2\s%$/);
    expect(formatPercent('10', 'en')).toBe('10%');
  });
});

describe('formatCount', () => {
  it('groups a count as the language does', () => {
    expect(formatCount(12345, 'es')).toBe('12.345');
    expect(formatCount(12345, 'en')).toBe('12,345');
    expect(formatCount(3, 'es')).toBe('3');
  });
});

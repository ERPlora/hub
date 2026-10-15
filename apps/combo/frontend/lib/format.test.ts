// How the combo screens paint money (pages never format by hand): euros in the page language, and a
// supplement with its sign (+2,00 €, −0,50 €), as the till shows it.
import { describe, expect, it } from 'vitest';

import { decimalMark, formatDelta, formatMoney } from './format';

const plain = (text: string) => text.replace(/[  ]/g, ' ');

describe('formatMoney', () => {
  it('paints whole cents as euros in the page language', () => {
    expect(plain(formatMoney(1350, 'es'))).toBe('13,50 €');
    expect(formatMoney(1350, 'en')).toBe('€13.50');
  });
});

describe('formatDelta', () => {
  it('paints a supplement with its sign, and nothing for none', () => {
    expect(plain(formatDelta(200, 'es'))).toBe('+2,00 €');
    expect(formatDelta(-50, 'en')).toBe('-€0.50');
    expect(formatDelta(0, 'en')).toBe('');
  });
});

describe('decimalMark', () => {
  it('is the comma in Spanish and the point in English', () => {
    expect([decimalMark('es'), decimalMark('en')]).toEqual([',', '.']);
  });
});

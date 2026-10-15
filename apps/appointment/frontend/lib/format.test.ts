// Money in the reader's language: whole cents of euros (the Hub invoices in euros).
import { describe, expect, it } from 'vitest';

import { formatMoney } from './format';

describe('formatMoney', () => {
  it('paints cents as euros in the page language', () => {
    expect(formatMoney(2250, 'es')).toMatch(/^22,50\s€$/); // a no-break space
    expect(formatMoney(2250, 'en')).toBe('€22.50');
    expect(formatMoney(0, 'es')).toMatch(/^0,00\s€$/);
  });
});

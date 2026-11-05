// The diary's money: whole cents of euros (hub#577 follows the business's currency), written with the platform's
// `formatMoney`, its thousands grouped like every other screen (hub#632).
import { formatMoney } from '@erplora/ui/components';
import { describe, expect, it } from 'vitest';

import { APPOINTMENT_MONEY } from './format';

describe('APPOINTMENT_MONEY', () => {
  it('paints cents as euros in the page language', () => {
    expect(formatMoney(2250, 'es', APPOINTMENT_MONEY)).toBe('22,50\u00a0€');
    expect(formatMoney(2250, 'en', APPOINTMENT_MONEY)).toBe('€22.50');
    expect(formatMoney(0, 'es', APPOINTMENT_MONEY)).toBe('0,00\u00a0€');
  });

  it('an amount of four figures groups its thousands, in both languages', () => {
    expect(formatMoney(123456, 'es', APPOINTMENT_MONEY)).toBe('1.234,56\u00a0€');
    expect(formatMoney(123456, 'en', APPOINTMENT_MONEY)).toBe('€1,234.56');
  });
});

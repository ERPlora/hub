// What an invoice says of its IRPF withholding (INVOICE-F17, F18): nothing without one, else its rate and its amount
// against the total.
import { describe, expect, it } from 'vitest';

import { plain } from './format';
import { WITHHOLDING_RATES, withholdingOf } from './withholding';

const t = (key: string, named?: Record<string, unknown>) => `${key}:${plain(String(named?.rate))}`;

describe('withholdingOf', () => {
  it('says the rate and takes the amount from the total', () => {
    expect(withholdingOf({ withholding_rate: '15.00', withholding_amount: 1500 }, t, 'en')).toEqual({ label: 'invoice.withholding.of:15%', amount: -1500 });
    expect(withholdingOf({ withholding_rate: '7.00', withholding_amount: 700 }, t, 'es')?.label).toBe('invoice.withholding.of:7 %');
  });

  it('gives it back on a rectifying invoice', () => {
    expect(withholdingOf({ withholding_rate: '15.00', withholding_amount: -1500 }, t, 'en')?.amount).toBe(1500);
  });

  it('of nothing is a plain zero', () => {
    expect(Object.is(withholdingOf({ withholding_rate: '15.00', withholding_amount: 0 }, t, 'en')?.amount, 0)).toBe(true);
  });

  it('is none without a rate', () => {
    expect(withholdingOf({ withholding_rate: null, withholding_amount: 0 }, t, 'en')).toBeNull();
  });
});

describe('WITHHOLDING_RATES', () => {
  it('are the server’s (apps/invoice/withholding.py), the general one first', () => {
    expect(WITHHOLDING_RATES).toEqual([15, 7, 1, 19]);
  });
});

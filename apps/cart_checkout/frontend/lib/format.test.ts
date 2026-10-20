// How the cart_checkout screens paint money, quantities and statuses, and how a range filter typed in
// the unit the column shows reaches the server (the old module's `lib/quantity.test.ts`,
// `money-display-guard.test.ts`, `range-filters.test.ts` and `total-amount-filter.test.ts`): an amount
// is whole minor units of ITS currency, painted with Intl, never divided by hand; a quantity carries no
// decorative zeros; «Total from 12» means twelve euros (1200 cents) and «Items from 2» two units.
import { describe, expect, it } from 'vitest';

import { CART_TONE, currencyDecimals, formatMoney, formatQuantity, ORDER_TONE, toMinor, toQuantity } from './format';

const nbsp = (text: string) => text.replace(/[  ]/g, ' ');

describe('formatMoney', () => {
  it('paints minor units in the page language, euros by default', () => {
    expect(nbsp(formatMoney(3150, 'es'))).toBe('31,50 €');
    expect(formatMoney(3150, 'en')).toBe('€31.50');
  });

  it('uses the scale of the row’s own currency, not a hardcoded 2 decimals', () => {
    expect(formatMoney(1999, 'en', 'JPY')).toBe('¥1,999');
    expect(nbsp(formatMoney(1999, 'en', 'KWD'))).toBe('KWD 1.999');
    expect(formatMoney(1999, 'en', 'USD')).toBe('$19.99');
  });

  it('groups the thousands of a four-digit amount too, so a column of totals lines up (hub#1090)', () => {
    // Spanish CLDR leaves 1234,56 ungrouped (minimumGroupingDigits = 2); Odoo, Business Central and
    // the old hub's fix group it, as 12.345,60 is.
    expect(nbsp(formatMoney(123456, 'es'))).toBe('1.234,56 €');
    expect(nbsp(formatMoney(1234560, 'es'))).toBe('12.345,60 €');
    expect(formatMoney(123456, 'en')).toBe('€1,234.56');
  });
});

describe('formatQuantity', () => {
  it('paints a decimal without decorative zeros, in the page language', () => {
    expect(formatQuantity('2.000', 'en')).toBe('2');
    expect(formatQuantity('0.500', 'en')).toBe('0.5');
    expect(formatQuantity('0.500', 'es')).toBe('0,5');
    expect(formatQuantity('1234.250', 'es')).toBe('1234,25');
  });

  it('gives back what is not a number untouched', () => {
    expect(formatQuantity('soon', 'es')).toBe('soon');
  });
});

describe('toMinor: a money range filter in the unit the column shows', () => {
  it('«12» is 1200 cents, «12.1» and «12,1» 1210, never 1209', () => {
    expect(toMinor('12')).toBe(1200);
    expect(toMinor('12.1')).toBe(1210);
    expect(toMinor('12,1')).toBe(1210);
    expect(toMinor('0.29')).toBe(29);
    expect(toMinor(' 12,5 ')).toBe(1250);
  });

  it('uses the currency’s own scale: 0 decimals (JPY) as is, 3 (KWD) ×1000', () => {
    expect(currencyDecimals('JPY')).toBe(0);
    expect(toMinor('1999', 'JPY')).toBe(1999);
    expect(toMinor('1.5', 'KWD')).toBe(1500);
  });

  it('text that is not an amount, or nothing, filters nothing (never «from 0»)', () => {
    expect(toMinor('abc')).toBeUndefined();
    expect(toMinor('')).toBeUndefined();
    expect(toMinor(undefined)).toBeUndefined();
    expect(toMinor('-3')).toBeUndefined();
    expect(toMinor('1,2,3')).toBeUndefined();
    expect(toMinor('12,345')).toBe(1234500);
  });

  it('reads what a person pastes, thousands marks and currency sign included (pm#521)', () => {
    expect(toMinor('1.250,50')).toBe(125050);
    expect(toMinor('1,250.50')).toBe(125050);
    expect(toMinor(' 1.234,56 € ')).toBe(123456);
    expect(toMinor('1.234.567')).toBe(123456700);
    expect(toMinor('1.255')).toBe(125500);
    expect(toMinor('1 250,5')).toBe(125050);
  });

  it('a mark followed by three digits ending in 0 can be thousands or a third decimal: it is not guessed', () => {
    // «1.250» is 1.250 € or 1,25 €; the filter filters nothing rather than the wrong amount.
    expect(toMinor('1.250')).toBeUndefined();
    expect(toMinor('1,250')).toBeUndefined();
    // A currency with three decimals reads it as its decimals.
    expect(toMinor('1.250', 'KWD')).toBe(1250);
  });

  it('more decimals than the currency has, or groups that are not of three, filter nothing', () => {
    expect(toMinor('12,3456')).toBeUndefined();
    expect(toMinor('12.5', 'JPY')).toBeUndefined();
    expect(toMinor('1.23.456')).toBeUndefined();
    expect(toMinor('1.234,5.6')).toBeUndefined();
  });
});

describe('toQuantity: an items range filter in units', () => {
  it('«2» is two units and «0,5» half a unit, as the server reads a decimal', () => {
    expect(toQuantity('2')).toBe('2');
    expect(toQuantity('0,5')).toBe('0.5');
    expect(toQuantity('1.250')).toBe('1.250');
  });

  it('more than three decimals or no number filters nothing', () => {
    expect(toQuantity('0.0005')).toBeUndefined();
    expect(toQuantity('two')).toBeUndefined();
    expect(toQuantity(undefined)).toBeUndefined();
  });
});

describe('the tones of the statuses', () => {
  it('give every cart and order status its tone', () => {
    expect(CART_TONE).toEqual({ active: 'info', abandoned: 'warning', converted: 'success', expired: 'neutral' });
    expect(ORDER_TONE).toEqual({ initiated: 'neutral', paid: 'info', failed: 'danger', completed: 'success' });
  });
});

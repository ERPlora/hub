// How the cart_checkout screens paint money, quantities and statuses, and how a range filter typed in
// the unit the column shows reaches the server (the old module's `lib/quantity.test.ts`,
// `money-display-guard.test.ts`, `range-filters.test.ts` and `total-amount-filter.test.ts`): an amount
// is whole minor units of ITS currency, with the decimals the server counts it in (flow
// cart-checkout-business-currency: never the browser's Intl, which gives the forint none, nor a euro by
// default); a quantity carries no decorative zeros and «Items from 2» means two units. «Total» is read by the
// platform, as every amount filter of the Hub (hub#1196: `CartsPage.test.ts`, `OrdersPage.test.ts`).
import { describe, expect, it } from 'vitest';

import { CART_TONE, formatMoney, formatQuantity, ORDER_TONE, recordMoney, toQuantity } from './format';

const nbsp = (text: string) => text.replace(/[\u00a0\u202f]/g, ' ');

const EUR = { currency: 'EUR', decimals: 2 };
const PLN = { currency: 'PLN', decimals: 2 };
const JPY = { currency: 'JPY', decimals: 0 };
/** The server counts the forint in two decimals (ISO 4217, CLDR); the browser's Intl, in none. */
const HUF = { currency: 'HUF', decimals: 2 };
const KWD = { currency: 'KWD', decimals: 3 };

describe('formatMoney', () => {
  it('paints minor units in the currency it is given, in the page language', () => {
    expect(nbsp(formatMoney(3150, 'es', EUR))).toBe('31,50 €');
    expect(formatMoney(3150, 'en', EUR)).toBe('€31.50');
    expect(nbsp(formatMoney(4250, 'es', PLN))).toBe('42,50 zł');
    expect(nbsp(formatMoney(4250, 'en', PLN))).toBe('zł 42.50');
  });

  it('divides by the decimals the server counts, never by Intl’s: the yen has none, the forint two', () => {
    expect(formatMoney(1999, 'en', JPY)).toBe('¥1,999');
    expect(nbsp(formatMoney(125000, 'es', HUF))).toBe('1.250,00 Ft');
    expect(nbsp(formatMoney(1999, 'en', KWD))).toBe('KWD 1.999');
  });

  it('while the business has not answered, the amount is a dash, never in euros', () => {
    expect(formatMoney(3150, 'es')).toBe('—');
    expect(formatMoney(123456, 'en')).toBe('—');
  });

  it('groups the thousands of a four-digit amount too, so a column of totals lines up (hub#1090)', () => {
    // Spanish CLDR leaves 1234,56 ungrouped (minimumGroupingDigits = 2); Odoo, Business Central and
    // the old hub's fix group it, as 12.345,60 is.
    expect(nbsp(formatMoney(123456, 'es', EUR))).toBe('1.234,56 €');
    expect(nbsp(formatMoney(1234560, 'es', PLN))).toBe('12.345,60 zł');
    expect(formatMoney(123456, 'en', EUR)).toBe('€1,234.56');
    expect(formatMoney(123456, 'es')).toBe('—');
  });
});

describe('recordMoney', () => {
  it('a cart or an order is painted in its own currency, with the decimals the server says (a record is never rewritten)', () => {
    expect(recordMoney({ currency: 'JPY', currency_decimals: 0 })).toEqual(JPY);
    expect(recordMoney({ currency: 'HUF', currency_decimals: 2 })).toEqual(HUF);
  });
});

describe('formatQuantity', () => {
  it('paints a decimal without decorative zeros, in the page language', () => {
    expect(formatQuantity('2.000', 'en')).toBe('2');
    expect(formatQuantity('0.500', 'en')).toBe('0.5');
    expect(formatQuantity('0.500', 'es')).toBe('0,5');
  });

  // hub#974: a cart's items are counted as the till and the stock count them: thousands grouped from four digits on.
  it('groups the thousands from four digits on, in every language', () => {
    expect(formatQuantity('1234.250', 'es')).toBe('1.234,25');
    expect(formatQuantity('12500.000', 'es')).toBe('12.500');
    expect(formatQuantity(1500, 'en')).toBe('1,500');
  });

  it('gives back what is not a number untouched', () => {
    expect(formatQuantity('soon', 'es')).toBe('soon');
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

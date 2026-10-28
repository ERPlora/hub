// How the cart_checkout screens paint money, quantities and statuses, and how a range filter typed in
// the unit the column shows reaches the server (the old module's `lib/quantity.test.ts`,
// `money-display-guard.test.ts`, `range-filters.test.ts` and `total-amount-filter.test.ts`): an amount
// is whole minor units of ITS currency, with the decimals the server counts it in (flow
// cart-checkout-business-currency: never the browser's Intl, which gives the forint none, nor a euro by
// default); a quantity carries no decorative zeros; «Total from 12» means twelve units of the business's
// currency (1200 in złoty, 12 in yen) and «Items from 2» two units.
import { describe, expect, it } from 'vitest';

import {
  amountExample,
  CART_TONE,
  formatMoney,
  formatQuantity,
  ORDER_TONE,
  recordMoney,
  toMinor,
  toQuantity,
  unreadableTotals,
} from './format';

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

  it('while the business has not answered, the figure goes without a symbol, never in euros', () => {
    expect(formatMoney(3150, 'es')).toBe('31,50');
    expect(formatMoney(123456, 'en')).toBe('1,234.56');
  });

  it('groups the thousands of a four-digit amount too, so a column of totals lines up (hub#1090)', () => {
    // Spanish CLDR leaves 1234,56 ungrouped (minimumGroupingDigits = 2); Odoo, Business Central and
    // the old hub's fix group it, as 12.345,60 is.
    expect(nbsp(formatMoney(123456, 'es', EUR))).toBe('1.234,56 €');
    expect(nbsp(formatMoney(1234560, 'es', PLN))).toBe('12.345,60 zł');
    expect(formatMoney(123456, 'en', EUR)).toBe('€1,234.56');
    expect(formatMoney(123456, 'es')).toBe('1.234,56');
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
    expect(formatQuantity('1234.250', 'es')).toBe('1234,25');
  });

  it('gives back what is not a number untouched', () => {
    expect(formatQuantity('soon', 'es')).toBe('soon');
  });
});

describe('toMinor: a money range filter in the business’s currency', () => {
  it('«12» is 1200 in złoty, «12.1» and «12,1» 1210, never 1209', () => {
    expect(toMinor('12', PLN)).toBe(1200);
    expect(toMinor('12.1', PLN)).toBe(1210);
    expect(toMinor('12,1', PLN)).toBe(1210);
    expect(toMinor('0.29', PLN)).toBe(29);
    expect(toMinor(' 12,5 ', PLN)).toBe(1250);
  });

  it('uses the decimals the server counts: «12» is 12 in yen, «12,5» is 1250 in forints, «1.5» 1500 in dinars', () => {
    expect(toMinor('12', JPY)).toBe(12);
    expect(toMinor('1999', JPY)).toBe(1999);
    expect(toMinor('12,5', HUF)).toBe(1250);
    expect(toMinor('1.5', KWD)).toBe(1500);
  });

  it('while the business has not answered, two decimals and no symbol', () => {
    expect(toMinor('12')).toBe(1200);
    expect(toMinor('12,5')).toBe(1250);
    expect(toMinor('12,50 €')).toBeUndefined();
  });

  it('text that is not an amount, or nothing, filters nothing (never «from 0»)', () => {
    expect(toMinor('abc', EUR)).toBeUndefined();
    expect(toMinor('', EUR)).toBeUndefined();
    expect(toMinor(undefined, EUR)).toBeUndefined();
    expect(toMinor('-3', EUR)).toBeUndefined();
    expect(toMinor('1,2,3', EUR)).toBeUndefined();
    expect(toMinor('12,345', EUR)).toBe(1234500);
  });

  it('reads what a person pastes, thousands marks and its currency’s code or symbol included (pm#521)', () => {
    expect(toMinor('1.250,50', EUR)).toBe(125050);
    expect(toMinor('1,250.50', EUR)).toBe(125050);
    expect(toMinor(' 1.234,56 € ', EUR)).toBe(123456);
    expect(toMinor('1.234.567', EUR)).toBe(123456700);
    expect(toMinor('1.255', EUR)).toBe(125500);
    expect(toMinor('1 250,5', EUR)).toBe(125050);
    expect(toMinor('12,50 zł', PLN)).toBe(1250);
    expect(toMinor('PLN 12.50', PLN)).toBe(1250);
    expect(toMinor('¥1,999', JPY)).toBe(1999);
  });

  it('another currency’s symbol is not the business’s: it filters nothing', () => {
    expect(toMinor('12,50 €', PLN)).toBeUndefined();
    expect(toMinor('EUR 12', PLN)).toBeUndefined();
  });

  it('a mark followed by three digits ending in 0 can be thousands or a third decimal: it is not guessed', () => {
    // «1.250» is 1.250 zł or 1,25 zł; the filter filters nothing rather than the wrong amount.
    expect(toMinor('1.250', PLN)).toBeUndefined();
    expect(toMinor('1,250', PLN)).toBeUndefined();
    // A currency with three decimals reads it as its decimals; one without decimals, as thousands.
    expect(toMinor('1.250', KWD)).toBe(1250);
    expect(toMinor('1.500', JPY)).toBe(1500);
  });

  it('more decimals than the currency has, or groups that are not of three, filter nothing', () => {
    expect(toMinor('12,3456', EUR)).toBeUndefined();
    expect(toMinor('12.5', JPY)).toBeUndefined();
    expect(toMinor('1.23.456', EUR)).toBeUndefined();
    expect(toMinor('1.234,5.6', EUR)).toBeUndefined();
    // With both marks the thousands still go in groups of three.
    expect(toMinor('12.34,50', EUR)).toBeUndefined();
    expect(toMinor('1,2.50', EUR)).toBeUndefined();
  });
});

describe('unreadableTotals: the ends of the Total filter that are not an amount', () => {
  it('names the typed ends it cannot read, never an empty one or another filter', () => {
    expect(unreadableTotals({ total_amount_from: '1.250', total_amount_to: '12,5', total_items_from: 'two' }, PLN)).toEqual(['total_amount_from']);
    expect(unreadableTotals({ total_amount_from: ' ', total_amount_to: 'abc' }, PLN)).toEqual(['total_amount_to']);
    expect(unreadableTotals({}, PLN)).toEqual([]);
  });

  it('reads them in the business’s currency: «12,5» is no amount of yen', () => {
    expect(unreadableTotals({ total_amount_from: '12,5' }, JPY)).toEqual(['total_amount_from']);
    expect(unreadableTotals({ total_amount_from: '12,5' }, HUF)).toEqual([]);
  });
});

describe('amountExample: the amount the hint under an unreadable Total shows', () => {
  it('is written with the decimals of the business’s currency, in the page language', () => {
    expect(amountExample('en', EUR)).toBe('12.50');
    expect(amountExample('es', PLN)).toBe('12,50');
    expect(amountExample('en', JPY)).toBe('12');
    expect(amountExample('es', KWD)).toBe('12,500');
    expect(amountExample('es')).toBe('12,50');
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

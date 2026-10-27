// How the sale screens paint numbers (WORKBOOK «Para quien lo mantiene»: money travels in cents,
// quantities and percentages as decimal strings). One place turns them into text in the page's
// language with `Intl.NumberFormat`, and the amounts a person types into cents: no page formats by hand.
// Money is in the business's currency (flow business-currency), or a charged sale's own: the one the screen
// passes, with the decimals the server counts; until it is known, a figure without a symbol, never the euro.
import { describe, expect, it } from 'vitest';

import { centsFromAmount, currencySign, formatDay, formatMoney, formatPercent, formatQuantity, moneyOf, plain } from './format';

// The money as `base.business.get` (or a sale) says it: the currency and the decimals the server counts it in.
const EUR = { currency: 'EUR', decimals: 2 };
const PLN = { currency: 'PLN', decimals: 2 };
const JPY = { currency: 'JPY', decimals: 0 };
const HUF = { currency: 'HUF', decimals: 2 };

/** Intl puts a narrow no-break space before «€» and «%» in Spanish: compared as a plain space. */
const spaced = (text: string) => plain(text);

describe('formatMoney', () => {
  it('paints cents as euros in the page language', () => {
    expect(formatMoney(123456, 'en', EUR)).toBe('€1,234.56');
    expect(formatMoney(0, 'en', EUR)).toBe('€0.00');
    expect(formatMoney(-350, 'en', EUR)).toBe('-€3.50');
  });

  it('groups the thousands from four digits on, in Spanish too (hub#1090)', () => {
    // Spanish CLDR only groups from five digits on (minimumGroupingDigits 2): «1234,56 €» beside
    // «12.345,67 €», and unlike Carts, Price lists and Payments, which paint «1.234,56 €».
    expect(spaced(formatMoney(123456, 'es', EUR))).toBe('1.234,56 €');
    expect(spaced(formatMoney(1234567, 'es', EUR))).toBe('12.345,67 €');
    expect(spaced(formatMoney(-123456, 'es', EUR))).toBe('-1.234,56 €');
    expect(formatMoney(123456, 'en', EUR)).toBe('€1,234.56');
    expect(formatMoney(1234567, 'en', EUR)).toBe('€12,345.67');
  });

  it('a missing amount is a dash, never «NaN», and a broken language falls back to English', () => {
    expect(formatMoney(null, 'en', EUR)).toBe('—');
    expect(formatMoney(undefined, 'es', EUR)).toBe('—');
    expect(formatMoney(100, 'not a tag!', EUR)).toBe('€1.00');
  });
});

describe('money of the business (flow business-currency)', () => {
  it('paints the currency it is given, with the sign a till there writes: zlotys in Poland', () => {
    expect(spaced(formatMoney(123456, 'es', PLN))).toBe('1.234,56 zł');
    expect(spaced(formatMoney(15050, 'pl', PLN))).toBe('150,50 zł');
    expect(formatMoney(15050, 'es', PLN)).not.toContain('€');
  });

  it('takes the decimals the server counts, never the browser’s: the yen has none, the forint keeps its two', () => {
    expect(formatMoney(5003, 'en', JPY)).toBe('¥5,003');
    expect(spaced(formatMoney(5003, 'es', JPY))).toBe('5.003 ¥');
    // Intl gives the forint no decimals; the server (CLDR) two: 123450 is 1,234.50 Ft, never 123,450 Ft.
    expect(spaced(formatMoney(123450, 'en', HUF))).toBe('Ft 1,234.50');
  });

  it('until the money is known an amount is a figure without a sign, never the euro', () => {
    expect(spaced(formatMoney(123456, 'es'))).toBe('1.234,56');
    expect(formatMoney(15050, 'en')).toBe('150.50');
    expect(formatMoney(null, 'en')).toBe('—');
  });

  it('a charged sale is painted with its own currency and decimals, as the server sent them', () => {
    expect(moneyOf({ currency: 'PLN', currency_decimals: 2 })).toEqual(PLN);
    expect(moneyOf({ currency: 'JPY', currency_decimals: 0 })).toEqual(JPY);
    // A server that does not send it yet (a deploy half way): a figure without a sign, never a broken screen.
    expect(moneyOf({} as { currency: string; currency_decimals: number })).toBeUndefined();
    expect(formatMoney(150, 'en', moneyOf({} as { currency: string; currency_decimals: number }))).toBe('1.50');
  });

  it('the sign of the money alone, for the button that switches a discount to an amount (gh:sales#380)', () => {
    expect(currencySign('es', EUR)).toBe('€');
    expect(currencySign('es', PLN)).toBe('zł');
    expect(currencySign('en', JPY)).toBe('¥');
    expect(currencySign('es', undefined)).toBe('');
  });
});

describe('formatPercent', () => {
  it('paints a rate or a discount without trailing zeros', () => {
    expect(formatPercent('21.00', 'en')).toBe('21%');
    expect(spaced(formatPercent('12.50', 'es'))).toBe('12,5 %');
    expect(formatPercent('5.2', 'en')).toBe('5.2%');
    expect(formatPercent(null, 'en')).toBe('—');
  });
});

describe('formatQuantity', () => {
  it('paints a quantity with only the decimals it has, and its unit unless it is units', () => {
    expect(formatQuantity('2.000', 'ud', 'en')).toBe('2');
    expect(formatQuantity('0.532', 'kg', 'es')).toBe('0,532 kg');
    expect(formatQuantity('1.500', 'h', 'en')).toBe('1.5 h');
  });
});

describe('centsFromAmount', () => {
  it('reads what a person types, with a comma or a dot, into whole cents', () => {
    expect(centsFromAmount('12,5', EUR)).toBe(1250);
    expect(centsFromAmount(' 12.50 ', EUR)).toBe(1250);
    expect(centsFromAmount('0,01', EUR)).toBe(1);
    expect(centsFromAmount(7, EUR)).toBe(700);
  });

  it('empty or not an amount is nothing', () => {
    expect(centsFromAmount('', EUR)).toBeUndefined();
    expect(centsFromAmount(null, EUR)).toBeUndefined();
    expect(centsFromAmount('12,345', EUR)).toBeUndefined();
    expect(centsFromAmount('abc', EUR)).toBeUndefined();
  });

  it('reads the minor units of the business’s currency: a yen is a yen and has no decimals', () => {
    expect(centsFromAmount('1000', JPY)).toBe(1000);
    expect(centsFromAmount('10,5', JPY)).toBeUndefined();
    expect(centsFromAmount('12,50', PLN)).toBe(1250);
    // Until the money is known, two decimals: what nearly every currency of the SaaS counts.
    expect(centsFromAmount('12,50')).toBe(1250);
  });
});

describe('formatDay', () => {
  it('a day as the reader writes it (what «Expires on» shows)', () => {
    expect(formatDay('2026-11-14T10:00:00Z', 'es')).toBe('14/11/2026');
    expect(formatDay('2026-11-14T10:00:00Z', 'en')).toBe('11/14/2026');
    expect(formatDay(null, 'es')).toBe('—');
  });
});

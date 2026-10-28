// How the payment screens paint money, days and statuses (the old module's `lib/enums.test.ts` and
// money tests): an amount is whole minor units of ITS money (its currency and the decimals the server counts it
// in: 2 in EUR and in the forint, 0 in JPY, 3 in KWD), never the browser's Intl decimals (which give the forint
// none) and never a euro by default; a payment date is a calendar day, read in the page's language and never moved
// by the browser's time zone; every status has its tone.
import { describe, expect, it } from 'vitest';

import * as format from './format';
import { decimalMark, formatDay, formatMoney, localDay, paymentMoney, STATUS_TONE } from './format';

const nbsp = (text: string) => text.replace(/[\u00a0\u202f]/g, ' ');
const EUR = { currency: 'EUR', decimals: 2 };

describe('formatMoney', () => {
  it('paints minor units of a money in the page language', () => {
    expect(nbsp(formatMoney(25000, 'es', EUR))).toBe('250,00 €');
    expect(formatMoney(25000, 'en', EUR)).toBe('€250.00');
    expect(nbsp(formatMoney(1250, 'es', { currency: 'PLN', decimals: 2 }))).toBe('12,50 zł');
    expect(formatMoney(1250, 'en', { currency: 'PLN', decimals: 2 })).toBe('zł 12.50');
  });

  it('while the money is unknown, a figure without a symbol: never the euro by default', () => {
    expect(nbsp(formatMoney(25000, 'es'))).toBe('250,00');
    expect(formatMoney(123456, 'en')).toBe('1,234.56');
    expect('CURRENCY' in format).toBe(false);
  });

  it('groups the thousands from four digits on, in Spanish too (hub#1090, payments#20)', () => {
    // Spanish CLDR only groups from five digits on (minimumGroupingDigits 2): «1234,56 €» beside
    // «12.345,67 €», and unlike Carts and Price lists, which paint «1.234,56 €».
    expect(nbsp(formatMoney(123456, 'es', EUR))).toBe('1.234,56 €');
    expect(nbsp(formatMoney(1234567, 'es', EUR))).toBe('12.345,67 €');
    expect(formatMoney(123456, 'en', EUR)).toBe('€1,234.56');
    expect(nbsp(formatMoney(123456, 'es'))).toBe('1.234,56');
  });

  it('uses the decimals the server counts the currency in, never the browser’s', () => {
    expect(formatMoney(1999, 'en', { currency: 'JPY', decimals: 0 })).toBe('¥1,999');
    expect(nbsp(formatMoney(1999, 'en', { currency: 'KWD', decimals: 3 }))).toBe('KWD 1.999');
    expect(formatMoney(1999, 'en', { currency: 'USD', decimals: 2 })).toBe('$19.99');
    // The forint: 2 decimals on the server (CLDR), none in Intl; 125050 is 1.250,50 Ft, never 125.050 Ft.
    expect(nbsp(formatMoney(125050, 'en', { currency: 'HUF', decimals: 2 }))).toBe('Ft 1,250.50');
    expect(nbsp(formatMoney(125050, 'es', { currency: 'HUF', decimals: 2 }))).toBe('1.250,50 Ft');
  });
});

describe('paymentMoney', () => {
  it('is the currency a payment was recorded in, with the decimals the server says for it', () => {
    expect(paymentMoney({ currency: 'HUF', currency_decimals: 2 })).toEqual({ currency: 'HUF', decimals: 2 });
    expect(paymentMoney({ currency: 'JPY', currency_decimals: 0 })).toEqual({ currency: 'JPY', decimals: 0 });
  });
});

describe('formatDay', () => {
  it('reads a calendar day as the page language writes it', () => {
    expect(formatDay('2026-07-13', 'es')).toBe('13/07/2026');
    expect(formatDay('2026-07-13', 'en')).toBe('07/13/2026');
  });

  it('never slides the day west of Greenwich, and the date half of a moment is enough', () => {
    expect(formatDay('2026-01-01', 'es')).toBe('01/01/2026');
    expect(formatDay('2026-07-13T23:30:00Z', 'es')).toBe('13/07/2026');
  });

  it('gives back anything that is not a day untouched, instead of losing the row', () => {
    expect(formatDay('soon', 'es')).toBe('soon');
    expect(formatDay('', 'es')).toBe('');
  });
});

describe('localDay', () => {
  it('is the device’s own day as YYYY-MM-DD (what «New payment» starts with), never the UTC one', () => {
    expect(localDay(new Date(2026, 9, 14, 0, 30))).toBe('2026-10-14');
    expect(localDay(new Date(2026, 0, 5, 23, 59))).toBe('2026-01-05');
  });
});

describe('decimalMark', () => {
  it('is the page language’s', () => {
    expect([decimalMark('es'), decimalMark('en')]).toEqual([',', '.']);
  });
});

describe('STATUS_TONE', () => {
  it('gives each of the five statuses a tone: in progress, done or inert', () => {
    expect(STATUS_TONE).toEqual({
      draft: 'neutral',
      approved: 'info',
      sent: 'warning',
      completed: 'success',
      cancelled: 'danger',
    });
  });
});

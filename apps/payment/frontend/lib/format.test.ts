// How the payment screens paint money, days and statuses (the old module's `lib/enums.test.ts` and
// money tests): an amount is whole minor units of ITS currency (2 decimals in EUR, 0 in JPY, 3 in KWD),
// painted with Intl, never divided by hand; a payment date is a calendar day, read in the page's
// language and never moved by the browser's time zone; every status has its tone.
import { describe, expect, it } from 'vitest';

import { decimalMark, formatDay, formatMoney, localDay, STATUS_TONE } from './format';

const nbsp = (text: string) => text.replace(/[  ]/g, ' ');

describe('formatMoney', () => {
  it('paints minor units in the page language, euros by default', () => {
    expect(nbsp(formatMoney(25000, 'es'))).toBe('250,00 €');
    expect(formatMoney(25000, 'en')).toBe('€250.00');
    expect(nbsp(formatMoney(1250, 'es', 'EUR'))).toBe('12,50 €');
  });

  it('uses the scale of the payment’s own currency, not a hardcoded 2 decimals', () => {
    expect(formatMoney(1999, 'en', 'JPY')).toBe('¥1,999');
    expect(nbsp(formatMoney(1999, 'en', 'KWD'))).toBe('KWD 1.999');
    expect(formatMoney(1999, 'en', 'USD')).toBe('$19.99');
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

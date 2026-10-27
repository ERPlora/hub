// How the kitchen paints numbers and moments (WORKBOOK «Pantallas»): the card's clock (m:ss, h:mm:ss past
// the hour), its green-amber-red border, quantities as a cook reads them, money and the History's
// moments in the business's zone.
import { describe, expect, it } from 'vitest';

import { SETTINGS } from '../__tests__/kitchen';
import { formatDateTime, formatElapsed, formatMoney, formatQuantity, semaphore } from './format';

describe('formatElapsed', () => {
  it('is m:ss, then h:mm:ss past the hour, and never negative', () => {
    expect(formatElapsed(0)).toBe('0:00');
    expect(formatElapsed(65_000)).toBe('1:05');
    expect(formatElapsed(14 * 60_000 + 59_999)).toBe('14:59');
    expect(formatElapsed(3_723_000)).toBe('1:02:03');
    expect(formatElapsed(-5_000)).toBe('0:00');
  });
});

describe('semaphore', () => {
  it('is green, then amber at the amber minutes, then red at the red minutes', () => {
    expect(semaphore(14 * 60_000, SETTINGS)).toBe('ok');
    expect(semaphore(15 * 60_000, SETTINGS)).toBe('warning');
    expect(semaphore(30 * 60_000, SETTINGS)).toBe('critical');
  });

  it('is off without the colour semaphore', () => {
    expect(semaphore(40 * 60_000, { ...SETTINGS, color_coding: false })).toBe('off');
  });
});

describe('formatQuantity', () => {
  it('drops the zeros the server sends and keeps a fraction', () => {
    expect(formatQuantity('2.000', 'en')).toBe('2');
    expect(formatQuantity('0.500', 'es')).toBe('0,5');
    expect(formatQuantity('1.250', 'en')).toBe('1.25');
  });
});

describe('formatMoney', () => {
  const EUR = { currency: 'EUR', decimals: 2 };

  it('turns minor units into the business’s currency in the reader’s language', () => {
    expect(formatMoney(2450, 'en', EUR)).toBe('€24.50');
    expect(formatMoney(2450, 'es', EUR)).toBe('24,50\u00a0€');
  });

  it('a business in Poland reads zlotys, never euros', () => {
    expect(formatMoney(2450, 'es', { currency: 'PLN', decimals: 2 })).toBe('24,50\u00a0zł');
    expect(formatMoney(2450, 'en', { currency: 'PLN', decimals: 2 })).toBe('zł\u00a024.50');
  });

  it('the decimals are the server’s: the yen has none, the forint keeps its two (Intl gives it none)', () => {
    expect(formatMoney(2450, 'en', { currency: 'JPY', decimals: 0 })).toBe('¥2,450');
    expect(formatMoney(2450, 'en', { currency: 'HUF', decimals: 2 })).toBe('Ft\u00a024.50');
  });

  it('until the business answers, an amount is a figure without a symbol, never in euros', () => {
    expect(formatMoney(2450, 'es')).toBe('24,50');
    expect(formatMoney(2450, 'en', undefined)).toBe('24.50');
  });
});

describe('formatDateTime', () => {
  it('paints a moment in the business’s zone', () => {
    expect(formatDateTime('2026-10-14T11:00:00Z', 'es', 'Europe/Madrid')).toBe('14/10/26, 13:00');
    expect(formatDateTime(null, 'es', 'Europe/Madrid')).toBe('');
  });
});

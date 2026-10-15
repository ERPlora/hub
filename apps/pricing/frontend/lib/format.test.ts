// How the pricing screens paint money (in a list's currency), quantities, percents, days and a validity.
import { describe, expect, it } from 'vitest';

import { decimalMark, formatDate, formatMoney, formatPercent, formatQuantity, quantityFieldText, readDecimal, validityLabel } from './format';

const t = (key: string, named?: Record<string, unknown>) => `${key}${named ? JSON.stringify(named) : ''}`;

describe('format', () => {
  it('paints cents in the page language, in euros or in the list currency', () => {
    expect(formatMoney(1250, 'es')).toBe('12,50\u00a0€');
    expect(formatMoney(1250, 'en')).toBe('€12.50');
    expect(formatMoney(1250, 'en', 'USD')).toBe('$12.50');
  });

  it('knows the decimal mark of the page language', () => {
    expect([decimalMark('es'), decimalMark('en')]).toEqual([',', '.']);
  });

  it('paints a quantity without its trailing zeros', () => {
    expect(formatQuantity('10.000', 'es')).toBe('10');
    expect(formatQuantity('0.500', 'es')).toBe('0,5');
    expect(formatQuantity('1234.250', 'en')).toBe('1,234.25');
  });

  it('paints a percent with up to two decimals', () => {
    expect(formatPercent('12.50', 'es')).toBe('12,5\u00a0%');
    expect(formatPercent('10', 'en')).toBe('10%');
  });

  it('paints a calendar day as it is, whatever the time zone', () => {
    expect(formatDate('2026-07-01', 'en')).toBe('Jul 1, 2026');
    expect(formatDate('2026-07-01', 'es')).toBe('1 jul 2026');
    expect(formatDate(null, 'es')).toBe('');
  });

  it('says always, from, until or between', () => {
    expect(validityLabel(null, null, t, 'en')).toBe('pricing.validity.always');
    expect(validityLabel('2026-07-01', null, t, 'en')).toBe('pricing.validity.from{"from":"Jul 1, 2026"}');
    expect(validityLabel(null, '2026-08-31', t, 'en')).toBe('pricing.validity.until{"until":"Aug 31, 2026"}');
    expect(validityLabel('2026-07-01', '2026-08-31', t, 'en')).toBe('pricing.validity.between{"from":"Jul 1, 2026","until":"Aug 31, 2026"}');
  });

  it('reads a quantity or a percent typed with a comma or a point, up to its decimals', () => {
    expect(readDecimal('0,5', 3)).toBe('0.5');
    expect(readDecimal(' 12.25 ', 2)).toBe('12.25');
    expect(readDecimal('10', 3)).toBe('10');
    expect([readDecimal('', 3), readDecimal('1,2345', 3), readDecimal('abc', 3), readDecimal('-1', 3)]).toEqual([null, null, null, null]);
  });

  it('writes a quantity for its field in the page format, without trailing zeros', () => {
    expect(quantityFieldText('10.000', 'es')).toBe('10');
    expect(quantityFieldText('0.500', 'es')).toBe('0,5');
    expect(quantityFieldText('1234.250', 'en')).toBe('1234.25');
  });
});

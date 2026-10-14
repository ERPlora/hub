// How the tax screens show a rate and a day in the reader's language (TAX-F01, TAX-F03): «21,00 %» and
// «1 sept 2012» for a Spanish reader, «21.00%» and «Sep 1, 2012» for an English one. A day of a rule is
// a calendar date (`YYYY-MM-DD`), never moved by the device's time zone.
import { describe, expect, it } from 'vitest';

import { formatDate, formatPercent } from './format';

/** Intl separates with no-break spaces; the reader sees spaces. */
const plain = (text: string) => text.replace(/[  ]/g, ' ');

describe('formatPercent', () => {
  it('two decimals in the reader’s language', () => {
    expect(plain(formatPercent('21.00', 'es'))).toBe('21,00 %');
    expect(plain(formatPercent('5.2', 'es'))).toBe('5,20 %');
    expect(formatPercent('21', 'en')).toBe('21.00%');
    expect(formatPercent(0, 'en')).toBe('0.00%');
  });

  it('keeps a value that is not a number as it came', () => {
    expect(formatPercent('n/a', 'en')).toBe('n/a');
  });
});

describe('formatDate', () => {
  it('a calendar day in the reader’s language, whatever the time zone', () => {
    expect(formatDate('2012-09-01', 'en')).toBe('Sep 1, 2012');
    expect(formatDate('2012-09-01', 'es')).toBe('1 sept 2012');
    expect(formatDate('2026-12-31', 'en')).toBe('Dec 31, 2026');
  });

  it('nothing to show is empty; what is not a date stays as it came', () => {
    expect(formatDate(null, 'en')).toBe('');
    expect(formatDate('', 'en')).toBe('');
    expect(formatDate('soon', 'en')).toBe('soon');
  });
});

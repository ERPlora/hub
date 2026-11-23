// A day of the card (birthday, anniversary: `YYYY-MM-DD`, or `--MM-DD` without its year) in the page language, and
// the day, month and year a person types for it. A day has no time nor time zone, so it never shifts.
import { describe, expect, it } from 'vitest';

import { annualDate, annualDateOrder, annualDateParts, formatDay } from './dates';

describe('formatDay', () => {
  it('paints a day in the page language, the same day in any time zone', () => {
    expect(formatDay('1990-02-03', 'en')).toBe('Feb 3, 1990');
    expect(formatDay('1990-02-03', 'es')).toBe('3 feb 1990');
  });

  it('paints a day without its year by its day and its month, the 29th of February too', () => {
    expect(formatDay('--03-12', 'es')).toBe('12 de marzo');
    expect(formatDay('--03-12', 'en')).toBe('March 12');
    expect(formatDay('--02-29', 'es')).toBe('29 de febrero');
  });

  it('nothing to show is «—»; a text that is not a day is shown as it came', () => {
    expect(formatDay(null, 'en')).toBe('—');
    expect(formatDay('', 'en')).toBe('—');
    expect(formatDay('soon', 'en')).toBe('soon');
  });
});

describe('annualDate and annualDateParts', () => {
  it('a day and a month without the year are `--MM-DD`; with the year, the ISO day', () => {
    expect(annualDate({ day: '12', month: '3', year: '' })).toBe('--03-12');
    expect(annualDate({ day: ' 4 ', month: '11', year: ' 1990 ' })).toBe('1990-11-04');
  });

  it('nothing typed is no day; a part missing goes up as typed, for the server to refuse it under its field', () => {
    expect(annualDate({ day: ' ', month: '', year: '' })).toBe('');
    expect(annualDate({ day: '', month: '3', year: '' })).toBe('--03-');
    expect(annualDate({ day: '1a', month: '3', year: '90' })).toBe('90-03-1a');
  });

  it('reads back what the card keeps, and nothing from what is not a day', () => {
    expect(annualDateParts('--03-12')).toEqual({ day: '12', month: '3', year: '' });
    expect(annualDateParts('1990-11-04')).toEqual({ day: '4', month: '11', year: '1990' });
    for (const none of [null, undefined, '', 'soon']) expect(annualDateParts(none)).toEqual({ day: '', month: '', year: '' });
  });

  it('asks the parts in the order the page language writes a day', () => {
    expect(annualDateOrder('es')).toEqual(['day', 'month', 'year']);
    expect(annualDateOrder('en')).toEqual(['month', 'day', 'year']);
  });
});

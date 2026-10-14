// How the staff screens paint and read money, rates, calendar dates and wall-clock times (pages never
// format by hand). Money is whole cents of euros (the Hub has no currency setting yet); a calendar
// date (`YYYY-MM-DD`) is a day, not an instant, so it is painted in UTC and never moves a day; a time
// is the wall clock of the business (`HH:MM:SS` on the wire, `HH:MM` in a time field).
import { describe, expect, it } from 'vitest';

import {
  centsFromText,
  formatDate,
  formatMoney,
  formatPercent,
  formatTime,
  hoursSummary,
  moneyText,
  timeValue,
} from './format';

describe('formatMoney', () => {
  it('paints whole cents as euros in the reader’s language', () => {
    // Intl keeps the amount and the sign together with a no-break space.
    expect(formatMoney(1250, 'es')).toBe('12,50 €');
    expect(formatMoney(1250, 'en')).toBe('€12.50');
    expect(formatMoney(0, 'en')).toBe('€0.00');
  });
});

describe('moneyText and centsFromText (the hourly-rate field)', () => {
  it('shows cents as the figure a person types, in their decimal mark', () => {
    expect(moneyText(1250, 'es')).toBe('12,50');
    expect(moneyText(1250, 'en')).toBe('12.50');
    expect(moneyText(0, 'en')).toBe('0.00');
  });

  it('reads what a person types back into whole cents, with a comma or a point', () => {
    expect(centsFromText('12,50')).toBe(1250);
    expect(centsFromText('12.5')).toBe(1250);
    expect(centsFromText(' 9 ')).toBe(900);
    expect(centsFromText('0.015')).toBe(2);
  });

  it('an empty field is no rate (0); what is not a figure is null (the server would refuse it)', () => {
    expect(centsFromText('')).toBe(0);
    expect(centsFromText('  ')).toBe(0);
    expect(centsFromText('doce')).toBeNull();
    expect(centsFromText('1.250,50')).toBeNull();
  });

  it('keeps a negative figure negative, for the server to say why it refuses it under the field', () => {
    expect(centsFromText('-3')).toBe(-300);
  });
});

describe('formatPercent', () => {
  it('paints the commission without trailing zeros, in the reader’s decimal mark', () => {
    expect(formatPercent('12.50', 'es')).toBe('12,5 %');
    expect(formatPercent('10.00', 'en')).toBe('10 %');
    expect(formatPercent('0.00', 'en')).toBe('0 %');
  });
});

describe('formatDate', () => {
  it('paints a calendar day in the reader’s order, never a day off west of Greenwich', () => {
    expect(formatDate('2026-10-05', 'es')).toBe('05/10/2026');
    expect(formatDate('2026-10-05', 'en')).toBe('10/05/2026');
  });

  it('nothing to show is a dash; what is not a date comes back as it was', () => {
    expect(formatDate(null, 'en')).toBe('—');
    expect(formatDate('', 'en')).toBe('—');
    expect(formatDate('soon', 'en')).toBe('soon');
  });
});

describe('formatTime and timeValue', () => {
  it('paints a wall-clock time as HH:MM', () => {
    expect(formatTime('09:00:00')).toBe('09:00');
    expect(formatTime('13:30')).toBe('13:30');
    expect(formatTime(null)).toBe('');
  });

  it('timeValue: the HH:MM a time field holds, empty for none', () => {
    expect(timeValue('18:00:00')).toBe('18:00');
    expect(timeValue(null)).toBe('');
  });
});

describe('hoursSummary (the «Hours» column of Schedules)', () => {
  const short = (day: number) => ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][day];

  it('says the week at a glance, by weekday, with the break in brackets', () => {
    const days = [
      { weekday: 2, start_time: '10:00:00', end_time: '16:00:00', break_start: null, break_end: null },
      { weekday: 0, start_time: '09:00:00', end_time: '18:00:00', break_start: '13:00:00', break_end: '14:00:00' },
    ];
    expect(hoursSummary(days, short)).toBe('Mon 09:00–18:00 (13:00–14:00) · Wed 10:00–16:00');
  });

  it('a week without working days is a dash', () => {
    expect(hoursSummary([], short)).toBe('—');
  });
});

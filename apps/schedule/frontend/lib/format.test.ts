// How the schedule screens paint a wall-clock time and a calendar day in the reader's language: the
// clock of the language (24 hours in Spanish, AM/PM in English) and its day/month order, never moved
// by the device's time zone (a wall time and a calendar day name no instant). schedules#29, #50.
import { describe, expect, it } from 'vitest';

import { formatDate, formatSpan, formatTime, timeValue } from './format';

describe('formatTime', () => {
  it('paints the clock of the language', () => {
    expect(formatTime('14:30:00', 'es')).toBe('14:30');
    expect(formatTime('09:05', 'es')).toBe('09:05');
    expect(formatTime('14:30:00', 'en')).toBe('02:30 PM');
    expect(formatTime('00:00:00', 'en')).toBe('12:00 AM');
  });

  it('leaves what is not a time as it came', () => {
    expect(formatTime('', 'es')).toBe('');
    expect(formatTime('25:00', 'es')).toBe('25:00');
    expect(formatTime('later', 'en')).toBe('later');
  });
});

describe('formatSpan', () => {
  it('joins opening and closing with an en dash', () => {
    expect(formatSpan('10:00:00', '14:00:00', 'es')).toBe('10:00–14:00');
    expect(formatSpan('22:00:00', '02:00:00', 'en')).toBe('10:00 PM–02:00 AM');
  });
});

describe('formatDate', () => {
  it('paints a calendar day in the order of the language, never shifted a day', () => {
    expect(formatDate('2026-12-25', 'es')).toBe('25/12/2026');
    expect(formatDate('2026-12-25', 'en')).toBe('12/25/2026');
    expect(formatDate('2026-01-01', 'es')).toBe('01/01/2026');
  });

  it('a dash for none, and what is not a date as it came', () => {
    expect(formatDate(null, 'es')).toBe('—');
    expect(formatDate('', 'es')).toBe('—');
    expect(formatDate('soon', 'es')).toBe('soon');
  });
});

describe('timeValue', () => {
  it('is what a time field holds: HH:MM, or nothing', () => {
    expect(timeValue('09:00:00')).toBe('09:00');
    expect(timeValue('17:30')).toBe('17:30');
    expect(timeValue(null)).toBe('');
  });
});

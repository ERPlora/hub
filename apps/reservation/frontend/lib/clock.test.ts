// The book's clock is the business's, never the device's: a reservation keeps its day (`YYYY-MM-DD`) and
// its wall-clock time (`21:00:00`), read as text and painted in the reader's language; «today» is asked
// of the business's zone.
import { describe, expect, it } from 'vitest';

import { addDays, formatDay, formatShortDate, formatTime, hhmm, todayIn, wallNowIn, weekdayOf } from './clock';

// Wednesday 14 October 2026, 23:30 UTC = Thursday 15, 01:30 in Madrid.
const LATE = new Date('2026-10-14T23:30:00Z');

describe('the book’s clock', () => {
  it('asks today and now of the business’s zone, not the device’s', () => {
    expect(todayIn('Europe/Madrid', LATE)).toBe('2026-10-15');
    expect(todayIn('UTC', LATE)).toBe('2026-10-14');
    expect(wallNowIn('Europe/Madrid', LATE)).toBe('2026-10-15T01:30');
  });

  it('steps days on the calendar across months and the change of time', () => {
    expect(addDays('2026-10-31', 1)).toBe('2026-11-01');
    expect(addDays('2026-10-25', -1)).toBe('2026-10-24');
    expect(addDays('2026-03-29', 1)).toBe('2026-03-30');
  });

  it('knows the weekday of a day, Monday first', () => {
    expect(weekdayOf('2026-10-12')).toBe(0);
    expect(weekdayOf('2026-10-15')).toBe(3);
    expect(weekdayOf('2026-10-18')).toBe(6);
  });

  it('cuts a server time to hours and minutes', () => {
    expect(hhmm('21:00:00')).toBe('21:00');
    expect(hhmm('09:05')).toBe('09:05');
    expect(hhmm('')).toBe('');
  });

  it('paints days and times in the reader’s language', () => {
    expect(formatDay('2026-10-15', 'en')).toBe('Thursday, October 15');
    expect(formatDay('2026-10-15', 'es')).toBe('Jueves, 15 de octubre');
    expect(formatShortDate('2026-10-15', 'es')).toBe('15/10/2026');
    expect(formatShortDate('2026-10-15', 'en')).toBe('10/15/2026');
    expect(formatTime('21:00:00', 'es')).toBe('21:00');
    expect(formatTime('21:00:00', 'en')).toBe('9:00 PM');
  });
});

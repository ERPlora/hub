// The agenda's clock is the business's, never the device's (WORKBOOK «Antes de empezar»): the server sends
// every time on the business's clock with its offset (`2026-10-19T10:00:00+02:00`), so the wall clock is
// read straight from the text; «today» is asked of the business's zone; days step on the calendar.
import { describe, expect, it } from 'vitest';

import {
  addDays,
  dayOf,
  deviceZoneDiffers,
  formatDay,
  formatShortDate,
  formatShortDay,
  formatTime,
  minutesOf,
  timeOf,
  todayIn,
  wallInput,
  wallNowIn,
  weekDays,
  weekStart,
} from './clock';

describe('the business clock', () => {
  it('reads the wall clock straight from the server’s time, whatever the device’s zone', () => {
    const start = '2026-10-19T09:05:00+02:00';
    expect([dayOf(start), timeOf(start), minutesOf(start)]).toEqual(['2026-10-19', '09:05', 545]);
    expect(timeOf('2026-10-19T23:30:00-05:00')).toBe('23:30');
  });

  it('asks today of the business’s zone', () => {
    const lateInUtc = new Date('2026-10-18T23:30:00Z');
    expect(todayIn('Europe/Madrid', lateInUtc)).toBe('2026-10-19');
    expect(todayIn('America/New_York', lateInUtc)).toBe('2026-10-18');
  });

  it('says the business’s wall clock now', () => {
    expect(wallNowIn('Europe/Madrid', new Date('2026-10-18T23:30:00Z'))).toBe('2026-10-19T01:30');
  });

  it('steps days on the calendar, and a week starts on Monday', () => {
    expect(addDays('2026-10-31', 1)).toBe('2026-11-01');
    expect(addDays('2026-03-29', -1)).toBe('2026-03-28');
    expect(weekStart('2026-10-21')).toBe('2026-10-19');
    expect(weekStart('2026-10-25')).toBe('2026-10-19');
    expect(weekDays('2026-10-21')).toEqual([
      '2026-10-19',
      '2026-10-20',
      '2026-10-21',
      '2026-10-22',
      '2026-10-23',
      '2026-10-24',
      '2026-10-25',
    ]);
  });

  it('paints days and times in the reader’s language', () => {
    expect(formatDay('2026-10-19', 'en')).toBe('Monday, October 19, 2026');
    expect(formatDay('2026-10-19', 'es')).toBe('lunes, 19 de octubre de 2026');
    expect(formatShortDay('2026-10-19', 'es')).toBe('lun 19');
    expect(formatShortDate('2026-10-19', 'en')).toBe('Oct 19, 2026');
    expect(formatShortDate('2026-10-19', 'es')).toBe('19 oct 2026');
    expect(formatTime('09:05', 'es')).toBe('9:05');
    // appointments#214: a hub in Spanish never paints «p. m.».
    expect(formatTime('21:05', 'es')).toBe('21:05');
    expect(formatTime('21:05', 'en')).toBe('9:05 PM');
  });

  it('sends a day and a time as the business’s wall clock', () => {
    expect(wallInput('2026-10-19', '9:5')).toBe('2026-10-19T09:05');
    expect(wallInput('2026-10-19', '10:30')).toBe('2026-10-19T10:30');
  });

  it('knows when the device is somewhere else', () => {
    const here = Intl.DateTimeFormat().resolvedOptions().timeZone;
    expect(deviceZoneDiffers(here)).toBe(false);
    expect(deviceZoneDiffers(here === 'Pacific/Auckland' ? 'Europe/Madrid' : 'Pacific/Auckland')).toBe(true);
  });
});

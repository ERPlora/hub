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
  wallLength,
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

  it('measures what a booking takes on the wall clock, which the nights the clock changes is not its real length', () => {
    expect(wallLength('2026-10-19T10:00:00+02:00', '2026-10-19T11:30:00+02:00', 90)).toBe(90);
    expect(wallLength('2026-10-19T23:30:00+02:00', '2026-10-20T00:30:00+02:00', 60)).toBe(60);
    expect(wallLength('2027-03-28T01:30:00+01:00', '2027-03-28T03:30:00+02:00', 60)).toBe(120);
    expect(wallLength('2026-10-25T01:37:00+02:00', '2026-10-25T02:07:00+01:00', 90)).toBe(30);
    // The repeated hour: on the wall it takes nothing or less, so it keeps its real length and is still seen.
    expect(wallLength('2026-10-25T02:30:00+02:00', '2026-10-25T02:30:00+01:00', 60)).toBe(60);
    expect(wallLength('2026-10-25T02:45:00+02:00', '2026-10-25T02:15:00+01:00', 30)).toBe(30);
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
    // A hub in Spanish never paints «p. m.».
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

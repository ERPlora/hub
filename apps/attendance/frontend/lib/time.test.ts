// How the time clock paints instants, days and durations (the old module's duration.ts and zone.ts):
// every wall-clock time and calendar day is on the clock it is given, the BUSINESS's (hub#779), never a zone written
// here; durations come from the server in seconds as of `as_of` and run on from there.
import { describe, expect, it } from 'vitest';

import {
  formatDay,
  formatHm,
  formatHms,
  formatTime,
  liveSeconds,
  localDate,
  localDateTime,
  monthBounds,
  monthLabel,
  monthOf,
  recentMonths,
  timeOfDay,
  toLocalInput,
} from './time';

const MADRID = 'Europe/Madrid';
const CANARY = 'Atlantic/Canary';

describe("the business's zone (hub#779)", () => {
  // In the Canaries on UTC in November, Madrid an hour ahead: 23:30 there is already tomorrow in Madrid.
  const NIGHT = '2026-11-02T23:30:00Z';

  it('tells every hour and day on the clock it is given, whatever else the deployment or the device are on', () => {
    expect(formatTime(NIGHT, CANARY)).toBe('23:30');
    expect(formatTime(NIGHT, MADRID)).toBe('00:30');
    expect(localDate(NIGHT, CANARY)).toBe('2026-11-02');
    expect(localDateTime(NIGHT, CANARY)).toBe('2026-11-02 23:30');
    expect(toLocalInput(NIGHT, CANARY)).toBe('2026-11-02T23:30');
    expect(monthOf(Date.parse('2026-10-31T23:30:00Z'), CANARY)).toBe('2026-10');
    expect(monthOf(Date.parse('2026-10-31T23:30:00Z'), MADRID)).toBe('2026-11');
    expect(timeOfDay(NIGHT, '2026-11-02', 'en', CANARY)).toBe('23:30');
    // A night shift's day: 23:30 UTC of the 3rd is the 3rd in the Canaries, already the 4th in Madrid.
    expect(timeOfDay('2026-11-03T23:30:00Z', '2026-11-02', 'es', CANARY)).toBe('23:30 (3/11)');
  });

  it('until the business answers it is on the device, never a zone written by hand', () => {
    const device = new Intl.DateTimeFormat('en-US', { hourCycle: 'h23', hour: '2-digit', minute: '2-digit' });
    expect(formatTime(NIGHT, undefined)).toBe(device.format(new Date(NIGHT)));
  });
});

describe('formatTime', () => {
  it('is the business wall clock HH:MM, 24 h, whatever the locale', () => {
    // 07:02 UTC is 09:02 in Madrid in October (UTC+2) and 08:02 in January (UTC+1).
    expect(formatTime('2026-10-05T07:02:41Z', MADRID)).toBe('09:02');
    expect(formatTime('2026-01-05T07:02:41Z', MADRID)).toBe('08:02');
    expect(formatTime('2026-10-05T22:30:00Z', MADRID)).toBe('00:30');
  });

  it('is empty for a missing or unreadable instant', () => {
    expect(formatTime(null, MADRID)).toBe('');
    expect(formatTime('not a date', MADRID)).toBe('');
  });
});

describe('durations', () => {
  it('formatHm writes hours and minutes', () => {
    expect(formatHm(452 * 60)).toBe('7:32');
    expect(formatHm(59)).toBe('0:00');
    expect(formatHm(-10)).toBe('0:00');
  });

  it('formatHms writes the running clock', () => {
    expect(formatHms(3 * 3600 + 5 * 60 + 9)).toBe('3:05:09');
    expect(formatHms(Number.NaN)).toBe('0:00:00');
  });

  it('liveSeconds runs on from the server’s figure only while it grows', () => {
    const asOf = '2026-10-06T10:30:00Z';
    const now = Date.parse('2026-10-06T10:31:05Z');
    expect(liveSeconds(100, asOf, now, true)).toBe(165);
    expect(liveSeconds(100, asOf, now, false)).toBe(100);
    // A clock behind the server's never runs it backwards.
    expect(liveSeconds(100, asOf, Date.parse('2026-10-06T10:29:00Z'), true)).toBe(100);
  });
});

describe('days', () => {
  it('formatDay is a short date of the business day, never moved by the zone', () => {
    expect(formatDay('2026-10-06', 'en')).toBe('Tue, Oct 6');
    expect(formatDay('2026-10-06', 'es')).toBe('mar, 6 oct');
  });

  it('timeOfDay adds the day when it is not the day of the clock-in (a night shift)', () => {
    expect(timeOfDay('2026-10-05T20:00:00Z', '2026-10-05', 'en', MADRID)).toBe('22:00');
    expect(timeOfDay('2026-10-06T04:00:00Z', '2026-10-05', 'en', MADRID)).toBe('06:00 (10/06)');
    expect(timeOfDay('2026-10-06T04:00:00Z', '2026-10-05', 'es', MADRID)).toBe('06:00 (6/10)');
    expect(timeOfDay(null, '2026-10-05', 'en', MADRID)).toBe('—');
  });

  it('localDateTime is the history’s and the CSV’s form', () => {
    expect(localDateTime('2026-10-05T07:02:41Z', MADRID)).toBe('2026-10-05 09:02');
  });

  it('toLocalInput fills a datetime-local field in business time', () => {
    expect(toLocalInput('2026-10-05T22:30:00Z', MADRID)).toBe('2026-10-06T00:30');
  });
});

describe('months', () => {
  it('monthOf is the business month of an instant', () => {
    // 23:30 UTC on 31 October is already 1 November in Madrid.
    expect(monthOf(Date.parse('2026-10-31T23:30:00Z'), MADRID)).toBe('2026-11');
  });

  it('recentMonths offers the four years the law keeps, newest first', () => {
    const months = recentMonths('2026-10', 49);
    expect(months).toHaveLength(49);
    expect(months.slice(0, 3)).toEqual(['2026-10', '2026-09', '2026-08']);
    expect(months.at(-1)).toBe('2022-10');
  });

  it('monthBounds are its first and last business days', () => {
    expect(monthBounds('2026-02')).toEqual({ date_from: '2026-02-01', date_to: '2026-02-28' });
    expect(monthBounds('2028-02')).toEqual({ date_from: '2028-02-01', date_to: '2028-02-29' });
    expect(monthBounds('2026-12')).toEqual({ date_from: '2026-12-01', date_to: '2026-12-31' });
  });

  it('monthLabel names it in the reader’s language, capitalised', () => {
    expect(monthLabel('2026-10', 'en')).toBe('October 2026');
    expect(monthLabel('2026-10', 'es')).toBe('Octubre de 2026');
  });
});

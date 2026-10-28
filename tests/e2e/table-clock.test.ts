// The times of the reservations of table-flows.spec.ts (TABLE-F25…F28, F31), chosen from the clock of the run: the
// plan paints a reservation only on the business's today (`table_rows` in apps/table/queries.py) and Reserved only
// from `RESERVED_LEAD` before it starts, and the book refuses a time already gone. `madrid(30)` fell on tomorrow
// from 23:30 on (and the afternoon one with it), so TABLE-F25 failed in the last half hour of the day.
// flow: TABLE-F25
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { bookingDays, bookingTimes, MARGIN_MINUTES, RESERVED_LEAD_MINUTES, untilMidnight } from './table-clock';

const QUERIES = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', 'apps', 'table', 'queries.py');
const DAY = '2026-10-28';
const WEDNESDAY = 2;
const MINUTE = 60_000;

/** `clock` of 28 October 2026 in Madrid (CET, UTC+1). */
const at = (clock: string): Date => new Date(`${DAY}T${clock}:00+01:00`);
const minutes = (clock: string): number => Number(clock.slice(0, 2)) * 60 + Number(clock.slice(3, 5));

describe('bookingTimes', () => {
  it('mirrors the lead of the plan: a reservation paints its table Reserved from RESERVED_LEAD before it', () => {
    const lead = /^RESERVED_LEAD = dt\.timedelta\(minutes=(\d+)\)$/m.exec(readFileSync(QUERIES, 'utf8'));
    expect(lead?.[1]).toBe(String(RESERVED_LEAD_MINUTES));
  });

  for (const clock of ['06:00', '11:59', '12:00', '19:45', '23:29', '23:31', '23:45', '00:05']) {
    it(`at ${clock} both reservations fall today: one within the hour and one of the afternoon`, () => {
      const times = bookingTimes(at(clock));
      expect(times).not.toBeNull();
      const { soon, evening } = times!;
      expect([soon.date, evening.date]).toEqual([DAY, DAY]);
      expect([soon.weekday, evening.weekday]).toEqual([WEDNESDAY, WEDNESDAY]);
      expect(minutes(soon.time)).toBeGreaterThanOrEqual(minutes(clock) + MARGIN_MINUTES);
      expect(minutes(soon.time)).toBeLessThanOrEqual(minutes(clock) + RESERVED_LEAD_MINUTES);
      expect(evening.time >= '12:00').toBe(true);
      expect(minutes(evening.time)).toBeGreaterThanOrEqual(minutes(soon.time));
      // The e2e slot is 00:00–23:59 and takes its start, never its end.
      expect(evening.time < '23:59').toBe(true);
    });
  }

  it('at 23:59 no time of today is left: it says so, and after midnight the times fall on the new day', () => {
    const now = at('23:59');
    expect(bookingTimes(now)).toBeNull();
    expect(untilMidnight(now)).toBe(MINUTE);
    const times = bookingTimes(new Date(now.getTime() + untilMidnight(now)));
    expect(times?.soon).toEqual({ date: '2026-10-29', time: '00:05', weekday: WEDNESDAY + 1 });
    expect(times?.evening).toEqual({ date: '2026-10-29', time: '20:00', weekday: WEDNESDAY + 1 });
  });

  it('every minute of the day either books today or waits less than ten minutes for midnight', () => {
    for (let minute = 0; minute < 24 * 60; minute += 1) {
      const now = new Date(at('00:00').getTime() + minute * MINUTE + 30_000);
      const times = bookingTimes(now);
      if (times) {
        expect([times.soon.date, times.evening.date]).toEqual([DAY, DAY]);
        // The margin counts the seconds of the run too, and no time passes the slot's last start (never «24:00»).
        expect(minutes(times.soon.time) - (minute + 0.5)).toBeGreaterThanOrEqual(MARGIN_MINUTES);
        expect(times.evening.time < '23:59').toBe(true);
      } else expect(untilMidnight(now)).toBeLessThan(10 * MINUTE);
    }
  });

  it('reads the business clock in summer time as well (CEST, UTC+2)', () => {
    const times = bookingTimes(new Date('2026-07-15T23:45:00+02:00'));
    expect(times?.soon).toEqual({ date: '2026-07-15', time: '23:50', weekday: WEDNESDAY });
  });
});

describe('bookingDays', () => {
  it('opens today and tomorrow: a run that waits for midnight books on the new day', () => {
    expect(bookingDays(at('23:45'))).toEqual([
      { date: DAY, weekday: WEDNESDAY },
      { date: '2026-10-29', weekday: WEDNESDAY + 1 },
    ]);
    expect(bookingDays(new Date('2026-12-31T12:00:00+01:00')).map((day) => day.date)).toEqual(['2026-12-31', '2027-01-01']);
  });
});

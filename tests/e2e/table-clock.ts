// The times of the reservations of table-flows.spec.ts, chosen from the clock of the run (table-clock.test.ts): both
// on the business's today, as the plan paints only today's (`table_rows` in apps/table/queries.py); one within
// `RESERVED_LEAD`, so its table is Reserved, and one of the afternoon, whose hour reads differently in 12 h; never a
// time gone, which the book refuses. In the last minutes of the day no such time is left, and the test waits for
// midnight (`untilMidnight`), the days it books on being open beforehand (`bookingDays`).

/** A day of the business: its date and its weekday (0 = Monday, as the slots count). */
export interface BookingDay {
  date: string;
  weekday: number;
}

/** A wall-clock moment of the business, as a reservation keeps it. */
export interface WallTime extends BookingDay {
  time: string;
}

/** The reservation within the hour (Reserved on the plan) and one of the afternoon (its hour in 12 h in English). */
export interface BookingTimes {
  soon: WallTime;
  evening: WallTime;
}

/** How long before its start a reservation paints its table Reserved (`RESERVED_LEAD` of apps/table/queries.py). */
export const RESERVED_LEAD_MINUTES = 60;
/** The room between choosing the times and booking the last reservation of the test: the book refuses a time gone. */
export const MARGIN_MINUTES = 5;

const ZONE = 'Europe/Madrid';
const MINUTE = 60_000;
const DAY_MINUTES = 24 * 60;
/** The last start the spec's slot (00:00–23:59, its end excluded) takes on the book's 5-minute grid. */
const LAST_START = 23 * 60 + 55;
const NOON = 12 * 60;
const EVENING = 20 * 60;

const parts = new Intl.DateTimeFormat('en-CA', {
  timeZone: ZONE,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23',
});

const weekdayOf = (date: string): number => (new Date(`${date}T00:00:00Z`).getUTCDay() + 6) % 7;
const clock = (minutes: number): string => `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`;

/** The business's wall clock at `now` (Madrid in phase 1): its date and the minutes since its midnight. */
function wall(now: Date): { date: string; minutes: number } {
  const part = Object.fromEntries(parts.formatToParts(now).map((found) => [found.type, found.value]));
  const seconds = Number(part.second) + now.getUTCMilliseconds() / 1000;
  return { date: `${part.year}-${part.month}-${part.day}`, minutes: Number(part.hour) * 60 + Number(part.minute) + seconds / 60 };
}

/** The times of the test's reservations at `now`, both today; `null` when no time of today is left. */
export function bookingTimes(now: Date): BookingTimes | null {
  const { date, minutes } = wall(now);
  const soon = Math.ceil((minutes + MARGIN_MINUTES) / 5) * 5;
  if (soon > LAST_START) return null;
  const day = { date, weekday: weekdayOf(date) };
  return { soon: { ...day, time: clock(soon) }, evening: { ...day, time: clock(soon >= NOON ? soon : EVENING) } };
}

/** Milliseconds from `now` to the business's next midnight. */
export function untilMidnight(now: Date): number {
  return Math.round((DAY_MINUTES - wall(now).minutes) * MINUTE);
}

/** The days a run may book on: today and, once it waited for midnight, tomorrow. */
export function bookingDays(now: Date): BookingDay[] {
  const today = wall(now).date;
  const [year, month, day] = today.split('-').map(Number);
  const tomorrow = new Date(Date.UTC(year, month - 1, day + 1)).toISOString().slice(0, 10);
  return [today, tomorrow].map((date) => ({ date, weekday: weekdayOf(date) }));
}

// The opening hours of the website's contact section: one row per day, Monday first, each with up to three
// intervals (an empty day is closed). Pure functions: every change answers a new week, never edits the old one.
import type { Day, DayHours, Interval } from '../operations';

export const DAYS: readonly Day[] = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];
/** The most intervals a day takes (the server's bound too). */
export const MAX_INTERVALS = 3;
const USUAL: Interval = { opens: '09:00', closes: '18:00' };
const WEEKEND: readonly Day[] = ['sat', 'sun'];

/** A usual week: weekdays 09:00–18:00, the weekend closed. */
export function defaultHours(): DayHours[] {
  return DAYS.map((day) => ({ day, intervals: WEEKEND.includes(day) ? [] : [{ ...USUAL }] }));
}

function change(week: readonly DayHours[], day: Day, intervals: (now: Interval[]) => Interval[]): DayHours[] {
  return week.map((row) => (row.day === day ? { day, intervals: intervals(row.intervals.map((i) => ({ ...i }))) } : row));
}

/** Opens a day with the usual hours, or closes it. */
export function setOpen(week: readonly DayHours[], day: Day, open: boolean): DayHours[] {
  return change(week, day, (now) => (open ? (now.length ? now : [{ ...USUAL }]) : []));
}

/** Adds an interval after the day's last one (two hours from its closing time), up to three. */
export function addInterval(week: readonly DayHours[], day: Day): DayHours[] {
  return change(week, day, (now) => {
    if (now.length >= MAX_INTERVALS) return now;
    const last = now.at(-1);
    if (!last) return [{ ...USUAL }];
    const [hours, minutes] = last.closes.split(':').map(Number);
    const later = `${String(Math.min(hours + 2, 23)).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
    return [...now, { opens: last.closes, closes: later === last.closes ? '23:59' : later }];
  });
}

export function removeInterval(week: readonly DayHours[], day: Day, index: number): DayHours[] {
  return change(week, day, (now) => now.filter((_, position) => position !== index));
}

export function setTime(week: readonly DayHours[], day: Day, index: number, edge: keyof Interval, time: string): DayHours[] {
  return change(week, day, (now) => now.map((interval, position) => (position === index ? { ...interval, [edge]: time } : interval)));
}

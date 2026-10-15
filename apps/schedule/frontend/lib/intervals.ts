// The opening intervals as the forms edit them (one line per interval, `HH:MM` as a time field holds
// them) and as the tables paint them. The server judges overlaps, empty intervals and the 12-line cap
// (its 422 under `intervals`); here only what cannot be sent: a line half filled.
import type { IntervalIn, IntervalOut } from '../operations';
import { formatSpan, timeValue } from './format';

/** One line of the editor. */
export interface IntervalRow {
  open_time: string;
  close_time: string;
}

/** 00:00–00:00: open 24 hours. */
export const ALL_DAY: Readonly<IntervalRow> = Object.freeze({ open_time: '00:00', close_time: '00:00' });

/** A fresh editor: one blank line (the market never opens with zero). */
export function blankRows(): IntervalRow[] {
  return [{ open_time: '', close_time: '' }];
}

/** The lines of stored intervals, or one blank line. */
export function rowsOf(intervals: readonly IntervalOut[]): IntervalRow[] {
  const rows = intervals.map((i) => ({ open_time: timeValue(i.open_time), close_time: timeValue(i.close_time) }));
  return rows.length ? rows : blankRows();
}

/** Only 00:00–00:00: the day is open 24 hours. */
export function isAllDay(rows: readonly IntervalRow[]): boolean {
  return rows.length === 1 && rows[0].open_time === ALL_DAY.open_time && rows[0].close_time === ALL_DAY.close_time;
}

/** What a form sends: none when closed; every line when all are complete; `null` when one is not. */
export function payloadOf(closed: boolean, rows: readonly IntervalRow[]): IntervalIn[] | null {
  if (closed) return [];
  if (!rows.length || rows.some((row) => !row.open_time || !row.close_time)) return null;
  return rows.map((row) => ({ open_time: row.open_time, close_time: row.close_time }));
}

/** The hours of a day or an exception as a table paints them. */
export interface HoursLike {
  /** A weekday may be «not set»; a special day or an override always is. */
  is_set?: boolean;
  is_closed: boolean;
  intervals: readonly IntervalOut[];
}

/** «Closed», «Open 24 hours», «Not set» or «10:00–14:00 · 17:00–20:00». */
export function hoursSummary(day: HoursLike, t: (key: string) => string, locale: string): string {
  if (day.is_set === false) return t('schedule.notSet');
  if (day.is_closed) return t('schedule.closed');
  if (!day.intervals.length) return t('schedule.notSet');
  const rows = day.intervals.map((i) => ({ open_time: timeValue(i.open_time), close_time: timeValue(i.close_time) }));
  if (isAllDay(rows)) return t('schedule.open24h');
  return day.intervals.map((i) => formatSpan(i.open_time, i.close_time, locale)).join(' · ');
}

/** «Open», «Closed» or «—» (not set). */
export function statusOf(day: HoursLike, t: (key: string) => string): string {
  if (day.is_set === false) return '—';
  return day.is_closed ? t('schedule.closed') : t('schedule.open');
}

// Where «By professional · Day» opens, as the agendas of Google Calendar or Fresha: today, half an hour before the
// business's time now; another day, at the hour the business opens; with neither, at the start of the calendar.
import { type Ref, watch } from 'vue';

import { minutesOf, wallNowIn } from '../lib/clock';

export interface GridStart {
  day: string;
  zone: string;
  now: Date;
  /** The closed periods of the day (Schedules), `[from, to)` in minutes. */
  closed: Array<[number, number]>;
  /** The calendar's first minute. */
  windowStart: number;
}

/** The first minute of the day the business is open, or null when it is closed all day. */
function opening(closed: Array<[number, number]>): number | null {
  let minute = 0;
  for (const [from, to] of [...closed].sort((a, b) => a[0] - b[0])) if (from <= minute) minute = Math.max(minute, to);
  return minute < 24 * 60 ? minute : null;
}

/** The minute of the day the grid opens at. */
export function startMinute(at: GridStart): number {
  const wall = wallNowIn(at.zone, at.now);
  const target = wall.slice(0, 10) === at.day ? minutesOf(wall) - 30 : (opening(at.closed) ?? at.windowStart);
  return Math.max(at.windowStart, target);
}

/** Scrolls `scroller` there once it is on screen and when the day, the zone or the hours change: never as the clock
 *  ticks, which would take the person away from where they scrolled. */
export function useGridStart(scroller: Ref<HTMLElement | null>, at: () => GridStart, pxPerMinute: number): void {
  const key = (): string => {
    const { day, zone, closed, windowStart } = at();
    return `${day}|${zone}|${closed.join(';')}|${windowStart}`;
  };
  watch(
    [scroller, key],
    ([element]) => {
      if (element) element.scrollLeft = (startMinute(at()) - at().windowStart) * pxPerMinute;
    },
    { flush: 'post' },
  );
}

// The week of a schedule (STAFF-F13, F14): one row per weekday (Monday = 0) with «works», start, end
// and an optional break. A new schedule proposes Monday to Friday, 09:00 to 18:00. Only the working
// days travel, in weekday order (a weekday not sent is a day off). The server judges the hours; its
// 422 names a day by its position in what was sent (`days.<i>.<field>`), turned back into the weekday
// here so the message sits under that day's row.
import type { DayIn, ScheduleOut } from '../operations';
import { timeValue } from './format';
import { WEEKDAYS } from './enums';

export interface WeekRow {
  weekday: number;
  working: boolean;
  /** `HH:MM`. */
  start: string;
  end: string;
  /** `HH:MM`, or `''` for no break. */
  breakStart: string;
  breakEnd: string;
}

export interface ScheduleForm {
  name: string;
  /** `YYYY-MM-DD`, or `''`. */
  effective_from: string;
  effective_until: string;
  is_default: boolean;
  week: WeekRow[];
}

const DAY_START = '09:00';
const DAY_END = '18:00';

/** Monday to Friday from 09:00 to 18:00, no break, the weekend off. */
export function defaultWeek(): WeekRow[] {
  return WEEKDAYS.map((weekday) => ({ weekday, working: weekday < 5, start: DAY_START, end: DAY_END, breakStart: '', breakEnd: '' }));
}

/** A new schedule: «Default» only when the member has none (a second one — a summer one — taking it
 *  over would stop the usual one from governing its days). */
export function blankScheduleForm(options: { isDefault: boolean }): ScheduleForm {
  return { name: '', effective_from: '', effective_until: '', is_default: options.isDefault, week: defaultWeek() };
}

/** «Edit · {name}»: the schedule and its week; a weekday it does not have is off. */
export function scheduleFormFromRecord(schedule: ScheduleOut): ScheduleForm {
  const week = WEEKDAYS.map((weekday) => {
    const day = schedule.days.find((d) => d.weekday === weekday);
    return day
      ? {
          weekday,
          working: true,
          start: timeValue(day.start_time),
          end: timeValue(day.end_time),
          breakStart: timeValue(day.break_start),
          breakEnd: timeValue(day.break_end),
        }
      : { weekday, working: false, start: DAY_START, end: DAY_END, breakStart: '', breakEnd: '' };
  });
  return {
    name: schedule.name,
    effective_from: schedule.effective_from ?? '',
    effective_until: schedule.effective_until ?? '',
    is_default: schedule.is_default,
    week,
  };
}

/** The working days as the server takes them, in weekday order. */
export function daysPayload(week: readonly WeekRow[]): DayIn[] {
  return [...week]
    .filter((day) => day.working)
    .sort((a, b) => a.weekday - b.weekday)
    .map((day) => ({
      weekday: day.weekday,
      start_time: day.start,
      end_time: day.end,
      break_start: day.breakStart || null,
      break_end: day.breakEnd || null,
    }));
}

/** The 422's `days.<i>.<field>` messages by the weekday they belong to (the first one per day). */
export function dayErrors(fields: Readonly<Record<string, string>>, sent: readonly DayIn[]): Record<number, string> {
  const out: Record<number, string> = {};
  for (const [key, message] of Object.entries(fields)) {
    const match = /^days\.(\d+)\./.exec(key);
    if (!match) continue;
    const day = sent[Number(match[1])];
    if (day && out[day.weekday] === undefined) out[day.weekday] = message;
  }
  return out;
}

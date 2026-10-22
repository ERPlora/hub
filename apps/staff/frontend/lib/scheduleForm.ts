// The week of a schedule (STAFF-F13, F14): one row per weekday (Monday = 0) with «works», start, end
// and an optional break. A new schedule proposes Monday to Friday with the business's default working
// day (Staff › Settings, STAFF-F22), its break in the middle of the day; a day off proposes the same
// hours for when it is switched on. Only the working days travel, in weekday order (a weekday not sent
// is a day off). The server judges the hours; its 422 names a day by its position in what was sent
// (`days.<i>.<field>`), turned back into the weekday here so the message sits under that day's row.
import type { DayIn, ScheduleOut, SettingsOut } from '../operations';
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

/** The business's default working day: `HH:MM` start and end, and the break in minutes (0 = none). */
export interface Workday {
  start: string;
  end: string;
  breakMinutes: number;
}

/** The settings' own defaults (models.py), proposed until the saved ones arrive. */
export const DEFAULT_WORKDAY: Workday = { start: '09:00', end: '18:00', breakMinutes: 60 };

export function workdayFromSettings(settings: SettingsOut): Workday {
  return { start: settings.default_work_start, end: settings.default_work_end, breakMinutes: settings.default_break_duration };
}

const minutes = (hhmm: string): number => Number(hhmm.slice(0, 2)) * 60 + Number(hhmm.slice(3, 5));
const hhmm = (total: number): string => `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;

/** The break in the middle of the day, its start rounded down to the quarter hour; none for 0 minutes
 *  or in a day that cannot hold it (the server refuses such a day anyway). */
export function proposedBreak(workday: Workday): Pick<WeekRow, 'breakStart' | 'breakEnd'> {
  const start = minutes(workday.start);
  const length = minutes(workday.end) - start;
  if (workday.breakMinutes <= 0 || workday.breakMinutes >= length) return { breakStart: '', breakEnd: '' };
  const from = start + Math.floor((length - workday.breakMinutes) / 2 / 15) * 15;
  return { breakStart: hhmm(from), breakEnd: hhmm(from + workday.breakMinutes) };
}

/** The working day as a weekday's row. */
function proposedDay(weekday: number, working: boolean, workday: Workday): WeekRow {
  return { weekday, working, start: workday.start, end: workday.end, ...proposedBreak(workday) };
}

/** Monday to Friday with the working day, the weekend off. */
export function defaultWeek(workday: Workday = DEFAULT_WORKDAY): WeekRow[] {
  return WEEKDAYS.map((weekday) => proposedDay(weekday, weekday < 5, workday));
}

/** A new schedule: «Default» only when the member has none (a second one — a summer one — taking it
 *  over would stop the usual one from governing its days). */
export function blankScheduleForm(options: { isDefault: boolean; workday?: Workday }): ScheduleForm {
  return { name: '', effective_from: '', effective_until: '', is_default: options.isDefault, week: defaultWeek(options.workday) };
}

/** «Edit · {name}»: the schedule and its week; a weekday it does not have is off. */
export function scheduleFormFromRecord(schedule: ScheduleOut, workday: Workday = DEFAULT_WORKDAY): ScheduleForm {
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
      : proposedDay(weekday, false, workday);
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

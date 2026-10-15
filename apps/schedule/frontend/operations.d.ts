// Types of the schedule app's operations for the SDK (`useLive`, `useCommand`), from
// apps/schedule/schemas.py. Written by hand, as `frontend/sdk-types.d.ts` is for the PoC, until V3
// generates them from `/api/openapi.json`. Keep it in step with schemas.py and with
// `frontend/generated/operations.json`. One input per operation (ninja's parity): no path parameters.
// Times are `HH:MM:SS` on the way out (`HH:MM` is accepted in); dates are ISO `YYYY-MM-DD`; a span's
// date-times are the business's wall clock without offset (`2026-08-17T22:00:00`).
import type { Page } from '../../../frontend/sdk-types';

export type SortDir = 'asc' | 'desc';
export type Source = 'special_day' | 'override' | 'weekly' | 'none';
export type OpenCode =
  | 'exception_closed'
  | 'exception_hours'
  | 'open_interval'
  | 'closed_today'
  | 'overnight_open'
  | 'outside_hours'
  | 'no_hours';

interface PageIn {
  limit?: number;
  offset?: number;
}

export interface IntervalIn {
  open_time: string;
  close_time: string;
}

export interface IntervalOut {
  open_time: string;
  close_time: string;
}

export type NoParamsIn = Record<string, never>;

// ── The week ───────────────────────────────────────────────────────────────────────────────────

export interface WeekDayOut {
  /** 0 = Monday … 6 = Sunday. */
  weekday: number;
  name: string;
  id: string | null;
  is_set: boolean;
  is_closed: boolean;
  intervals: IntervalOut[];
}

export interface WeekOut {
  week_starts_on: number;
  confirmed: boolean;
  timezone: string;
  days: WeekDayOut[];
}

export interface SetDayIn {
  /** 0 = Monday … 6 = Sunday (or its name). */
  weekday: number | string;
  is_closed?: boolean;
  intervals?: IntervalIn[];
}

// ── Special days ───────────────────────────────────────────────────────────────────────────────

export interface SpecialDayOut {
  id: string;
  date: string;
  name: string;
  is_closed: boolean;
  recurring_yearly: boolean;
  notes: string;
  intervals: IntervalOut[];
}

export interface SpecialDayIn {
  date: string;
  name: string;
  is_closed?: boolean;
  intervals?: IntervalIn[];
  recurring_yearly?: boolean;
  notes?: string;
}

export interface SpecialDayRefIn {
  id?: string;
  special_day?: string;
}

export interface SpecialDayPatchIn extends SpecialDayRefIn {
  date?: string;
  name?: string;
  is_closed?: boolean;
  intervals?: IntervalIn[];
  recurring_yearly?: boolean;
  notes?: string;
}

export interface BulkSpecialDayIn {
  special_days: SpecialDayIn[];
}

export interface BulkCreatedOut {
  created: string[];
  skipped: { index: number; date: string; code: 'already_exists' | 'invalid_hours'; message: string }[];
}

export interface SpecialDayListIn extends PageIn {
  search?: string;
  date_from?: string;
  date_to?: string;
  name?: string;
  is_closed?: boolean;
  recurring_yearly?: boolean;
  sort?: 'date' | 'name' | 'is_closed' | 'recurring_yearly' | 'id';
  dir?: SortDir;
}

// ── Overrides (temporary changes) ──────────────────────────────────────────────────────────────

export interface OverrideOut {
  id: string;
  start_date: string;
  end_date: string;
  reason: string;
  is_closed: boolean;
  intervals: IntervalOut[];
}

export interface OverrideIn {
  start_date: string;
  end_date: string;
  reason: string;
  is_closed?: boolean;
  intervals?: IntervalIn[];
}

export interface OverrideRefIn {
  id?: string;
  override?: string;
}

export interface OverridePatchIn extends OverrideRefIn {
  start_date?: string;
  end_date?: string;
  reason?: string;
  is_closed?: boolean;
  intervals?: IntervalIn[];
}

export interface OverrideListIn extends PageIn {
  search?: string;
  start_from?: string;
  start_to?: string;
  end_from?: string;
  end_to?: string;
  reason?: string;
  is_closed?: boolean;
  sort?: 'start_date' | 'end_date' | 'reason' | 'is_closed' | 'id';
  dir?: SortDir;
}

export interface DeletedOut {
  id: string;
}

// ── Settings, is it open, hours of a range ─────────────────────────────────────────────────────

export interface SettingsOut {
  week_starts_on: number;
  hours_confirmed: boolean;
  timezone: string;
}

export interface SettingsIn {
  week_starts_on?: number;
}

export interface IsOpenIn {
  when?: string;
}

export interface IsOpenOut {
  is_open: boolean;
  code: OpenCode;
  source: Source;
  rule_id: string | null;
  intervals: string[];
  timezone: string;
  today: string;
  current_time: string;
  reason: string | null;
}

export interface HoursRangeIn {
  date_from: string;
  date_to?: string;
}

export interface DayHoursOut {
  date: string;
  source: Source;
  rule_id: string | null;
  name: string;
  is_closed: boolean;
  intervals: IntervalOut[];
  spans: { start: string; end: string }[];
}

export interface HoursRangeOut {
  timezone: string;
  days: DayHoursOut[];
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'schedule.week.get': { input: NoParamsIn; output: WeekOut };
    'schedule.week.set_day': { input: SetDayIn; output: WeekOut };
    'schedule.week.confirm': { input: NoParamsIn; output: WeekOut };
    'schedule.special_day.list': { input: SpecialDayListIn; output: Page<SpecialDayOut> };
    'schedule.special_day.create': { input: SpecialDayIn; output: SpecialDayOut };
    'schedule.special_day.bulk_create': { input: BulkSpecialDayIn; output: BulkCreatedOut };
    'schedule.special_day.update': { input: SpecialDayPatchIn; output: SpecialDayOut };
    'schedule.special_day.delete': { input: SpecialDayRefIn; output: DeletedOut };
    'schedule.override.list': { input: OverrideListIn; output: Page<OverrideOut> };
    'schedule.override.create': { input: OverrideIn; output: OverrideOut };
    'schedule.override.update': { input: OverridePatchIn; output: OverrideOut };
    'schedule.override.delete': { input: OverrideRefIn; output: DeletedOut };
    'schedule.settings.get': { input: NoParamsIn; output: SettingsOut };
    'schedule.settings.update': { input: SettingsIn; output: SettingsOut };
    'schedule.business.is_open': { input: IsOpenIn; output: IsOpenOut };
    'schedule.hours.for_range': { input: HoursRangeIn; output: HoursRangeOut };
  }
}

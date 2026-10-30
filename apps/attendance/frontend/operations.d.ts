// Types of the attendance app's operations for the SDK (`useLive`, `useCommand`, `client.api.call`), from
// apps/attendance/schemas.py. Written by hand, as the other apps', until V3 generates them from
// `/api/openapi.json`. Keep it in step with schemas.py and `frontend/generated/operations.json`.
// One input per operation (ninja's parity): no path parameters, an id travels in the input.
// On the wire: instants ISO 8601 with their offset, business dates `YYYY-MM-DD`, durations in seconds.
import type { Page } from '../../../frontend/sdk-types';

export type RecordStatus = 'open' | 'closed' | 'needs_review';
export type Source = 'shared' | 'personal';
export type Radius = 50 | 100 | 250 | 500 | 1000;

type NoInput = Record<string, never>;

interface PageIn {
  limit?: number;
  offset?: number;
}

/** A person by id or by name; neither = the caller. */
export interface MemberRefIn {
  member_id?: string | null;
  member?: string | null;
}

export interface PositionIn extends MemberRefIn {
  lat?: number | null;
  lng?: number | null;
  accuracy_m?: number | null;
}

/** No device mode: shared or personal is the server's to know (the session's device), never the payload's. */
export type ClockInIn = PositionIn;

export type ClockOutIn = PositionIn;
export type BreakIn = MemberRefIn;

export interface CorrectIn {
  record_id: string;
  clock_in_at: string;
  clock_out_at?: string | null;
  reason: string;
}

export interface SettingsIn {
  require_location?: boolean | null;
  geofence_radius_m?: Radius | null;
  workplace_lat?: number | null;
  workplace_lng?: number | null;
  auto_close_after_hours?: number | null;
}

export interface RecordListIn extends PageIn {
  search?: string;
  member_id?: string;
  member?: string;
  mine?: boolean;
  status?: RecordStatus;
  /** Business dates, `YYYY-MM-DD`. */
  date_from?: string;
  date_to?: string;
  /** A column, `-` first for descending. */
  sort?: string;
}

export type RecordExportIn = Omit<RecordListIn, 'limit' | 'offset'>;

export interface RecordRefIn {
  id: string;
}

export interface PersonRefIn {
  id: string;
}

export interface CorrectionListIn extends PageIn {
  record_id?: string;
}

export interface SearchListIn extends PageIn {
  search?: string;
}

export interface MemberBriefOut {
  id: string;
  name: string;
}

export interface RecordOut {
  id: string;
  member_id: string;
  member_name: string;
  work_date: string;
  clock_in_at: string;
  clock_out_at: string | null;
  status: RecordStatus;
  source: Source;
  in_distance_m: number | null;
  in_within_radius: boolean | null;
  out_distance_m: number | null;
  out_within_radius: boolean | null;
  note: string;
  break_count: number;
  /** As of `as_of`, the running break included. */
  break_seconds: number;
  /** As of `as_of`; `null` for a day waiting for review. */
  worked_seconds: number | null;
  break_started_at: string | null;
  correction_count: number;
  as_of: string;
}

export interface BreakOut {
  id: string;
  started_at: string;
  ended_at: string | null;
  seconds: number;
}

export interface RecordDetailOut extends RecordOut {
  /** The day as the screens name it, in the reader's language: «Ana López · 6 oct 2026». */
  name: string;
  in_lat: number | null;
  in_lng: number | null;
  in_accuracy_m: number | null;
  out_lat: number | null;
  out_lng: number | null;
  out_accuracy_m: number | null;
  created_by_name: string;
  created_at: string;
  updated_at: string;
  breaks: BreakOut[];
}

export interface TodayOut {
  date: string;
  worked_seconds: number;
  break_seconds: number;
  running: 'work' | 'break' | null;
}

export interface CurrentOut {
  member: MemberBriefOut | null;
  open: RecordOut | null;
  today: TodayOut;
  recent: RecordOut[];
  as_of: string;
}

export interface CorrectionOut {
  id: string;
  record_id: string;
  old_clock_in_at: string;
  old_clock_out_at: string | null;
  old_status: RecordStatus;
  new_clock_in_at: string;
  new_clock_out_at: string | null;
  new_status: RecordStatus;
  reason: string;
  is_system: boolean;
  created_by_name: string;
  created_at: string;
}

export interface PresenceOut {
  record_id: string;
  member_id: string;
  member_name: string;
  clock_in_at: string;
  break_started_at: string | null;
  source: Source;
}

/** How many are clocked in now: the Home's «Clocked in now» (ATTENDANCE-F11). */
export interface PresenceCountOut {
  count: number;
}

export interface PersonOut {
  id: string;
  name: string;
  status: string;
}

export interface ExportOut {
  filename: string;
  content_type: string;
  rows: number;
  csv: string;
}

export interface SettingsOut {
  require_location: boolean;
  geofence_radius_m: number;
  workplace_lat: number | null;
  workplace_lng: number | null;
  auto_close_after_hours: number;
  workplace_set: boolean;
  saved: boolean;
  updated_at: string | null;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'attendance.record.current': { input: NoInput; output: CurrentOut };
    'attendance.record.list': { input: RecordListIn; output: Page<RecordOut> };
    'attendance.record.detail': { input: RecordRefIn; output: RecordDetailOut };
    'attendance.record.export': { input: RecordExportIn; output: ExportOut };
    'attendance.record.correct': { input: CorrectIn; output: RecordOut };
    'attendance.record.clock_in': { input: ClockInIn; output: RecordOut };
    'attendance.record.clock_out': { input: ClockOutIn; output: RecordOut };
    'attendance.break.start': { input: BreakIn; output: RecordOut };
    'attendance.break.end': { input: BreakIn; output: RecordOut };
    'attendance.correction.list': { input: CorrectionListIn; output: Page<CorrectionOut> };
    'attendance.presence.list': { input: SearchListIn; output: Page<PresenceOut> };
    'attendance.presence.count': { input: NoInput; output: PresenceCountOut };
    'attendance.person.list': { input: SearchListIn; output: Page<PersonOut> };
    'attendance.person.detail': { input: PersonRefIn; output: PersonOut };
    'attendance.settings.get': { input: NoInput; output: SettingsOut };
    'attendance.settings.update': { input: SettingsIn; output: SettingsOut };
  }
}

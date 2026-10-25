// Types of the staff app's operations for the SDK (`useLive`, `useCommand`, `client.api.call`), from
// apps/staff/schemas.py. Written by hand, as the tax app's, until V3 generates them from
// `/api/openapi.json`. Keep it in step with schemas.py and `frontend/generated/operations.json`.
// One input per operation (ninja's parity): no path parameters, an id travels in the input.
// On the wire: dates `YYYY-MM-DD`, times `HH:MM:SS`, decimals (commission) as strings («12.50»),
// money in whole cents, a business user's id as a number.
import type { Page } from '../../../frontend/sdk-types';

export type MemberStatus = 'active' | 'inactive' | 'on_leave';
export type LeaveType = 'vacation' | 'sick' | 'personal' | 'training' | 'other';
export type TimeOffStatus = 'pending' | 'approved' | 'rejected' | 'cancelled';
/** A record's status as the commission report shows it: someone who left still earned what they sold. */
export type RecordStatus = MemberStatus | 'terminated';
export type CommissionPeriod = 'today' | 'yesterday' | 'this_week' | 'this_month';

interface PageIn {
  limit?: number;
  offset?: number;
}

/** A staff member by id or, for the assistant, by name. */
export interface MemberRefIn {
  id?: string | null;
  member?: string | null;
}

export interface ByIdIn {
  id: string;
}

// ── Members ────────────────────────────────────────────────────────────────────────────────────

export type MemberSortKey =
  | 'name'
  | 'first_name'
  | 'last_name'
  | 'email'
  | 'phone'
  | 'role_name'
  | 'status'
  | 'is_bookable'
  | 'hire_date'
  | 'color'
  | 'user_id'
  | 'id';

export interface MemberListIn extends PageIn {
  search?: string;
  first_name?: string;
  last_name?: string;
  email?: string;
  phone?: string;
  status?: MemberStatus;
  role_id?: string;
  role_name?: string;
  is_bookable?: boolean;
  hire_date_from?: string;
  hire_date_to?: string;
  color?: string;
  user_id?: number;
  /** A column, `-` first for descending. */
  sort?: string;
}

export interface MemberIn {
  first_name: string;
  last_name: string;
  email?: string;
  phone?: string;
  employee_number?: string;
  role_id?: string | null;
  role?: string | null;
  user_id?: number | null;
  hire_date?: string | null;
  status?: MemberStatus;
  is_bookable?: boolean;
  booking_buffer?: number;
  color?: string;
  specialties?: string;
  bio?: string;
  hourly_rate?: number;
  commission_rate?: string | number;
  notes?: string;
}

/** Only the fields sent change; `null` clears role_id, user_id and hire_date. */
export interface MemberPatchIn extends MemberRefIn {
  first_name?: string;
  last_name?: string;
  email?: string;
  phone?: string;
  employee_number?: string;
  role_id?: string | null;
  role?: string | null;
  user_id?: number | null;
  hire_date?: string | null;
  status?: MemberStatus;
  is_bookable?: boolean;
  booking_buffer?: number;
  color?: string;
  specialties?: string;
  bio?: string;
  hourly_rate?: number;
  commission_rate?: string | number;
  notes?: string;
}

export interface TerminateIn extends MemberRefIn {
  termination_date?: string | null;
  reason?: string;
}

export interface BulkMemberIn {
  first_name: string;
  last_name: string;
  email?: string;
  phone?: string;
  role_id?: string | null;
  role?: string | null;
  hire_date?: string | null;
  hourly_rate?: number;
  is_bookable?: boolean;
  bio?: string;
  specialties?: string;
}

export interface BulkCreateIn {
  members: BulkMemberIn[];
}

export interface BulkCreatedOut {
  created: string[];
  skipped: { index: number; reason: string }[];
}

/** The directory's filters, sort and pages (the pay of the very rows on screen), and one member by id. */
export interface CompensationListIn extends MemberListIn {
  id?: string;
}

export interface CommissionSummaryIn extends PageIn {
  search?: string;
}

export interface MemberOut {
  id: string;
  first_name: string;
  last_name: string;
  full_name: string;
  email: string;
  phone: string;
  employee_number: string;
  role_id: string | null;
  role_name: string | null;
  user_id: number | null;
  status: MemberStatus;
  is_bookable: boolean;
  hire_date: string | null;
  color: string;
}

export interface MemberDetailOut extends MemberOut {
  booking_buffer: number;
  specialties: string;
  bio: string;
  created_at: string;
  updated_at: string;
}

export interface MemberMineOut extends MemberDetailOut {
  hourly_rate: number;
  commission_rate: string;
}

export interface MineOut {
  member: MemberMineOut | null;
}

/** Who «Me» is at the till (SALE-F16): the id and name of the caller's own record, never the pay. */
export interface CurrentMemberOut {
  member: { id: string; full_name: string } | null;
}

export interface CompensationOut {
  id: string;
  user_id: number | null;
  full_name: string;
  role_id: string | null;
  role_name: string | null;
  status: MemberStatus;
  hourly_rate: number;
  commission_rate: string;
  notes: string;
}

export interface CommissionOut {
  id: string;
  user_id: number | null;
  full_name: string;
  role_id: string | null;
  role_name: string | null;
  commission_rate: string;
}

/** A period: one of the server's (today by default), or two days of one's own (both, in order). */
export interface CommissionReportIn {
  period?: CommissionPeriod;
  date_from?: string | null;
  date_to?: string | null;
}

export interface CommissionReportRow {
  member_id: string;
  full_name: string;
  role_name: string | null;
  status: RecordStatus;
  commission_rate: string;
  /** What they sold in the period, refunds taken off, in cents. */
  sold: number;
  /** sold × rate ÷ 100 in cents, rounded half up once. */
  commission: number;
}

export interface CommissionReportOut {
  date_from: string;
  date_to: string;
  /** False when the business has no Sales: nobody is listed. */
  sales_available: boolean;
  rows: CommissionReportRow[];
  total_sold: number;
  total_commission: number;
}

export interface MemberStatsOut {
  total: number;
  active: number;
  on_leave: number;
  inactive: number;
  absent_today: number;
  pending_time_off: number;
}

export interface TerminatedOut {
  id: string;
  termination_date: string;
}

// ── Accounts («Hub user») ──────────────────────────────────────────────────────────────────────

export interface AccountListIn extends PageIn {
  search?: string;
  /** Only this business user (to name the one a record hangs from). */
  user_id?: number;
}

export interface AccountOut {
  user_id: number;
  name: string;
}

// ── Roles ──────────────────────────────────────────────────────────────────────────────────────

export interface RoleListIn extends PageIn {
  search?: string;
  is_active?: boolean;
  color?: string;
  member_count_min?: number;
  member_count_max?: number;
  sort?: string;
}

export interface RoleIn {
  name: string;
  description?: string;
  color?: string;
  order?: number;
}

export interface RolePatchIn {
  id: string;
  name?: string;
  description?: string;
  color?: string;
  order?: number;
  is_active?: boolean;
}

export interface RoleOut {
  id: string;
  name: string;
  description: string;
  color: string;
  order: number;
  is_active: boolean;
  member_count: number;
}

// ── Schedules ──────────────────────────────────────────────────────────────────────────────────

/** One weekday (Monday = 0); a weekday not sent is a day off. */
export interface DayIn {
  weekday: number;
  start_time: string;
  end_time: string;
  break_start?: string | null;
  break_end?: string | null;
  is_working?: boolean;
}

export interface ScheduleIn {
  name?: string;
  is_default?: boolean;
  effective_from?: string | null;
  effective_until?: string | null;
  days: DayIn[];
  member_id?: string | null;
  member?: string | null;
}

export interface ScheduleUpdateIn {
  id: string;
  name?: string;
  is_default?: boolean;
  effective_from?: string | null;
  effective_until?: string | null;
  days: DayIn[];
}

export interface SetActiveIn {
  id: string;
  is_active: boolean;
}

export interface ScheduleListIn extends PageIn {
  member_id?: string | null;
  member?: string | null;
}

export interface DayOut {
  weekday: number;
  start_time: string;
  end_time: string;
  break_start: string | null;
  break_end: string | null;
}

export interface ScheduleOut {
  id: string;
  member_id: string;
  name: string;
  is_default: boolean;
  effective_from: string | null;
  effective_until: string | null;
  is_active: boolean;
  days: DayOut[];
}

export interface DeletedOut {
  id: string;
}

// ── Availability ───────────────────────────────────────────────────────────────────────────────

export interface AvailabilityIn {
  member_id?: string | null;
  member?: string | null;
  date_from: string;
  date_to: string;
}

export interface IntervalOut {
  start: string;
  end: string;
}

export interface AvailabilityDayOut {
  date: string;
  schedule_id: string | null;
  shifts: IntervalOut[];
  time_off: { is_full_day: boolean; start_time: string | null; end_time: string | null }[];
  available: IntervalOut[];
}

export interface AvailabilityOut {
  member_id: string;
  days: AvailabilityDayOut[];
}

// ── Time off ───────────────────────────────────────────────────────────────────────────────────

export interface TimeOffFieldsIn {
  leave_type?: LeaveType;
  start_date: string;
  end_date: string;
  is_full_day?: boolean;
  start_time?: string | null;
  end_time?: string | null;
  reason?: string;
  notes?: string;
}

export interface TimeOffIn extends TimeOffFieldsIn {
  member_id?: string | null;
  member?: string | null;
}

export type TimeOffRequestIn = TimeOffFieldsIn;

export interface TimeOffListIn extends PageIn {
  search?: string;
  member_id?: string;
  status?: TimeOffStatus;
  leave_type?: LeaveType;
  is_full_day?: boolean;
  approved_by_id?: number;
  date_from?: string;
  date_to?: string;
  start_date_from?: string;
  start_date_to?: string;
  end_date_from?: string;
  end_date_to?: string;
  sort?: string;
}

export type TodayIn = PageIn;
export type MyTimeOffIn = PageIn;

export interface TimeOffOut {
  id: string;
  member_id: string;
  member_name: string;
  leave_type: LeaveType;
  /** The type in the caller's language (the Home's «Today's time off»). */
  leave_type_label: string;
  start_date: string;
  end_date: string;
  is_full_day: boolean;
  start_time: string | null;
  end_time: string | null;
  status: TimeOffStatus;
  approved_by_id: number | null;
  approved_at: string | null;
}

export interface TimeOffDetailOut extends TimeOffOut {
  reason: string;
  notes: string;
  approved_by_name: string | null;
  created_at: string;
}

// ── Settings ───────────────────────────────────────────────────────────────────────────────────

/** The default working day that a new schedule proposes (STAFF-F22); any other field is refused. */
export interface SettingsIn {
  default_work_start?: string;
  default_work_end?: string;
  default_break_duration?: number;
}

export interface SettingsOut {
  default_work_start: string;
  default_work_end: string;
  default_break_duration: number;
}

type NoInput = Record<string, never>;

declare module '@erplora/ui/sdk' {
  interface Operations {
    'staff.member.list': { input: MemberListIn; output: Page<MemberOut> };
    'staff.member.detail': { input: MemberRefIn; output: MemberDetailOut };
    'staff.member.mine': { input: NoInput; output: MineOut };
    'staff.member.current': { input: NoInput; output: CurrentMemberOut };
    'staff.member.compensation': { input: CompensationListIn; output: Page<CompensationOut> };
    'staff.member.stats': { input: NoInput; output: MemberStatsOut };
    'staff.member.create': { input: MemberIn; output: MemberDetailOut };
    'staff.member.bulk_create': { input: BulkCreateIn; output: BulkCreatedOut };
    'staff.member.update': { input: MemberPatchIn; output: MemberDetailOut };
    'staff.member.deactivate': { input: MemberRefIn; output: MemberDetailOut };
    'staff.member.terminate': { input: TerminateIn; output: TerminatedOut };
    'staff.commission.summary': { input: CommissionSummaryIn; output: Page<CommissionOut> };
    'staff.commission.report': { input: CommissionReportIn; output: CommissionReportOut };
    'staff.account.list': { input: AccountListIn; output: Page<AccountOut> };
    'staff.role.list': { input: RoleListIn; output: Page<RoleOut> };
    'staff.role.create': { input: RoleIn; output: RoleOut };
    'staff.role.update': { input: RolePatchIn; output: RoleOut };
    'staff.schedule.list': { input: ScheduleListIn; output: Page<ScheduleOut> };
    'staff.schedule.detail': { input: ByIdIn; output: ScheduleOut };
    'staff.schedule.create': { input: ScheduleIn; output: ScheduleOut };
    'staff.schedule.update': { input: ScheduleUpdateIn; output: ScheduleOut };
    'staff.schedule.set_active': { input: SetActiveIn; output: ScheduleOut };
    'staff.schedule.delete': { input: ByIdIn; output: DeletedOut };
    'staff.availability.for_member': { input: AvailabilityIn; output: AvailabilityOut };
    'staff.time_off.list': { input: TimeOffListIn; output: Page<TimeOffOut> };
    'staff.time_off.detail': { input: ByIdIn; output: TimeOffDetailOut };
    'staff.time_off.today': { input: TodayIn; output: Page<TimeOffOut> };
    'staff.time_off.mine': { input: MyTimeOffIn; output: Page<TimeOffDetailOut> };
    'staff.time_off.create': { input: TimeOffIn; output: TimeOffDetailOut };
    'staff.time_off.request': { input: TimeOffRequestIn; output: TimeOffDetailOut };
    'staff.time_off.approve': { input: ByIdIn; output: TimeOffDetailOut };
    'staff.time_off.reject': { input: ByIdIn; output: TimeOffDetailOut };
    'staff.time_off.cancel': { input: ByIdIn; output: TimeOffDetailOut };
    'staff.settings.get': { input: NoInput; output: SettingsOut };
    'staff.settings.update': { input: SettingsIn; output: SettingsOut };
  }
}

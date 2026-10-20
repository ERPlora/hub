// Types of the appointment app's operations for the SDK (`useLive`, `useCommand`, `client.api.call`), from
// apps/appointment/schemas.py. Written by hand, as the other apps', until V3 generates them from
// `/api/openapi.json`. Keep it in step with schemas.py and `frontend/generated/operations.json`.
// One input per operation (ninja's parity): no path parameters, an id travels in the input.
// On the wire: money in whole cents, minutes as integers, days `YYYY-MM-DD`, times on the business's
// clock with its offset (`2026-10-19T10:00:00+02:00`); a time sent without offset is wall clock.
import type { Page } from '../../../frontend/sdk-types';

export type AppointmentStatus = 'pending' | 'confirmed' | 'in_progress' | 'completed' | 'cancelled' | 'no_show';
export type AppointmentSource = 'counter' | 'phone' | 'online' | 'whatsapp';
export type Frequency = 'daily' | 'weekly' | 'biweekly' | 'monthly';
export type BlockType = 'holiday' | 'vacation' | 'break' | 'maintenance' | 'other';
export type HistoryAction =
  | 'created'
  | 'confirmed'
  | 'started'
  | 'completed'
  | 'cancelled'
  | 'no_show'
  | 'rescheduled'
  | 'staff_changed'
  | 'service_changed'
  | 'unassigned'
  | 'charged'
  | 'uncharged'
  | 'deleted';

type NoInput = Record<string, never>;

interface PageIn {
  limit?: number;
  offset?: number;
}

export interface ServiceRefIn {
  service_id?: string | null;
  service?: string | null;
}

export interface AppointmentRefIn {
  id?: string | null;
  number?: string | null;
}

export interface LineOut {
  service_id: string;
  name: string;
  price: number;
  duration_minutes: number;
}

export interface AppointmentRow {
  id: string;
  number: string;
  customer_id: string;
  customer_name: string;
  staff_id: string | null;
  staff_name: string;
  start: string;
  end: string;
  duration_minutes: number;
  status: AppointmentStatus;
  source: AppointmentSource;
  services: LineOut[];
  service_names: string;
  total: number;
  booked_by_customer: boolean;
  sale_id: string | null;
  /** The check open in the till to charge it; `null` = none. */
  order_id: string | null;
  recurring_id: string | null;
  occurrence_date: string | null;
}

export interface AppointmentOut extends AppointmentRow {
  customer_phone: string;
  customer_email: string;
  notes: string;
  internal_notes: string;
  cancelled_at: string | null;
  cancellation_reason: string;
  cancelled_by_customer: boolean;
  charged_at: string | null;
  created_at: string;
  updated_at: string;
  /** Its day ready to say, in the caller's language («martes, 5 de marzo de 2030»). */
  start_date_label: string;
  /** Its hour ready to say, 24-hour on the business's clock («10:30»). */
  start_time_label: string;
}

/** What a customer did herself (G01): a booking or a cancellation, as the notice says it. */
export interface NoticeOut {
  kind: 'booked' | 'cancelled';
  at: string;
  id: string;
  number: string;
  /** Empty once the customer's data was erased. */
  customer_name: string;
  service_names: string;
  staff_name: string;
  start: string;
  start_date_label: string;
  start_time_label: string;
}

export interface AppointmentPage extends Page<AppointmentRow> {
  timezone: string;
}

export interface AppointmentListIn extends PageIn {
  date_from: string;
  date_to?: string | null;
  staff_id?: string | null;
  staff?: string | null;
  unassigned?: boolean | null;
  customer_id?: string | null;
  status?: AppointmentStatus | null;
  search?: string;
  sort?: string;
}

export interface AppointmentCreateIn {
  customer_id?: string | null;
  customer?: string | null;
  services: ServiceRefIn[];
  staff_id?: string | null;
  staff?: string | null;
  start: string;
  duration_minutes?: number | null;
  notes?: string;
  internal_notes?: string;
  source?: AppointmentSource;
  confirm_overlap?: boolean;
}

export interface BulkCreateIn extends Omit<AppointmentCreateIn, 'start' | 'source' | 'internal_notes'> {
  starts: string[];
}

export interface RescheduleIn extends AppointmentRefIn {
  start?: string | null;
  duration_minutes?: number | null;
  staff_id?: string | null;
  staff?: string | null;
  services?: ServiceRefIn[] | null;
  reason?: string;
  confirm_overlap?: boolean;
  on_behalf_of_customer?: boolean;
  customer_id?: string | null;
  customer?: string | null;
}

export interface UpdateIn extends AppointmentRefIn {
  notes?: string | null;
  internal_notes?: string | null;
  customer_phone?: string | null;
  customer_email?: string | null;
  start?: string | null;
  duration_minutes?: number | null;
  staff_id?: string | null;
  staff?: string | null;
  services?: ServiceRefIn[] | null;
  confirm_overlap?: boolean;
}

export interface CancelIn extends AppointmentRefIn {
  reason?: string;
  on_behalf_of_customer?: boolean;
  customer_id?: string | null;
  customer?: string | null;
}

export interface HistoryOut {
  id: string;
  action: HistoryAction;
  at: string;
  actor: string;
  by_customer: boolean;
  reason: string;
  old_value: Record<string, unknown>;
  new_value: Record<string, unknown>;
}

export interface HistoryIn extends AppointmentRefIn, PageIn {}

export interface VisitOut extends AppointmentRow {
  notes: string;
  internal_notes: string;
}

export interface ForCustomerIn extends PageIn {
  customer_id?: string | null;
  customer?: string | null;
}

export interface CountOut {
  count: number;
  earliest: string | null;
}

export interface LaneOut {
  staff_id: string;
  name: string;
  color: string;
  takes_bookings: boolean;
}

export interface LanesIn {
  date_from: string;
  date_to?: string | null;
}

export interface LanesOut {
  rows: LaneOut[];
  unassigned: number;
  own_staff_id: string | null;
  sees_everyone: boolean;
  timezone: string;
}

export interface SlotsIn {
  date: string;
  service_ids?: string[] | null;
  services?: string[] | null;
  duration_minutes?: number | null;
  staff_id?: string | null;
  staff?: string | null;
  exclude_id?: string | null;
  for_customer?: boolean;
}

export interface SlotOut {
  start: string;
  end: string;
  within_notice: boolean;
  staff_ids: string[];
}

export interface SlotsOut {
  date: string;
  timezone: string;
  duration_minutes: number;
  slots: SlotOut[];
}

export interface CheckIn extends Omit<SlotsIn, 'date'> {
  start: string;
}

export interface ConflictOut {
  id: string;
  number: string;
  customer_name: string;
  start: string;
  end: string;
}

export interface CheckOut {
  available: boolean;
  code: string | null;
  message: string;
  conflicts: ConflictOut[];
}

export interface ChargeOut {
  appointment_id: string;
  order_id: string;
  label: string;
}

export interface DeletedOut {
  id: string;
}

export interface BlockedTimeOut {
  id: string;
  title: string;
  block_type: BlockType;
  start: string;
  end: string;
  all_day: boolean;
  staff_id: string | null;
  staff_name: string;
  reason: string;
}

export interface BlockedTimeListIn extends PageIn {
  date_from: string;
  date_to?: string | null;
  staff_id?: string | null;
}

export interface BlockedTimeCreateIn {
  title: string;
  block_type?: BlockType;
  start: string;
  end: string;
  all_day?: boolean;
  staff_id?: string | null;
  staff?: string | null;
  reason?: string;
}

export interface RecurringLineOut {
  service_id: string;
  name: string;
}

export interface RecurringOut {
  id: string;
  customer_id: string;
  customer_name: string;
  staff_id: string | null;
  staff_name: string;
  services: RecurringLineOut[];
  service_names: string;
  frequency: Frequency;
  day_of_week: number | null;
  /** `HH:MM:SS`. */
  time: string;
  duration_minutes: number;
  start_date: string;
  end_date: string | null;
  max_occurrences: number | null;
  is_active: boolean;
  split_from_id: string | null;
  created_at: string;
}

export interface RecurringDetailOut extends RecurringOut {
  next_date: string | null;
  upcoming: number;
  charged: number;
}

export interface RecurringListIn extends PageIn {
  search?: string;
  is_active?: boolean | null;
  frequency?: Frequency | null;
  staff_id?: string | null;
  sort?: string;
}

export interface RecurringCreateIn {
  customer_id?: string | null;
  customer?: string | null;
  services: ServiceRefIn[];
  staff_id?: string | null;
  staff?: string | null;
  frequency: Frequency;
  day_of_week?: number | null;
  start_date: string;
  time: string;
  duration_minutes?: number | null;
  end_date?: string | null;
  max_occurrences?: number | null;
}

export interface RecurringUpdateIn {
  id: string;
  from_date: string;
  frequency?: Frequency | null;
  day_of_week?: number | null;
  time?: string | null;
  duration_minutes?: number | null;
  staff_id?: string | null;
  staff?: string | null;
  services?: ServiceRefIn[] | null;
  end_date?: string | null;
  max_occurrences?: number | null;
}

export interface SkippedOut {
  occurrence_date: string;
  code: string;
  message: string;
}

export interface MaterializeOut {
  recurring: RecurringOut;
  booked: number;
  already_booked: number;
  skipped: SkippedOut[];
  next_from: string | null;
  to: string;
  upcoming_date: string | null;
}

export interface RecurringUpdatedOut {
  recurring: RecurringOut;
  moved: number;
  cancelled: number;
  locked: number;
  skipped: SkippedOut[];
  booked: number;
}

export interface SettingsOut {
  default_duration: number;
  min_booking_notice: number;
  max_advance_booking: number;
  allow_overlapping: boolean;
  allow_customer_cancellation: boolean;
  cancellation_notice_hours: number;
  calendar_start_hour: number;
  calendar_end_hour: number;
  slot_interval: number;
  auto_confirm_online: boolean;
  timezone: string;
}

export type SettingsIn = Partial<Omit<SettingsOut, 'timezone'>>;

declare module '@erplora/ui/sdk' {
  interface Operations {
    'appointment.appointment.list': { input: AppointmentListIn; output: AppointmentPage };
    'appointment.appointment.get': { input: AppointmentRefIn; output: AppointmentOut };
    'appointment.appointment.history': { input: HistoryIn; output: Page<HistoryOut> };
    'appointment.appointment.list_for_customer': { input: ForCustomerIn; output: Page<VisitOut> };
    'appointment.appointment.count_active_for_service': { input: ServiceRefIn; output: CountOut };
    'appointment.appointment.count_to_confirm': { input: NoInput; output: CountOut };
    'appointment.appointment.notices': { input: { since?: string | null; limit?: number }; output: { rows: NoticeOut[] } };
    'appointment.appointment.create': { input: AppointmentCreateIn; output: AppointmentOut };
    'appointment.appointment.bulk_create': { input: BulkCreateIn; output: { rows: AppointmentOut[] } };
    'appointment.appointment.reschedule': { input: RescheduleIn; output: AppointmentOut };
    'appointment.appointment.update': { input: UpdateIn; output: AppointmentOut };
    'appointment.appointment.confirm': { input: AppointmentRefIn; output: AppointmentOut };
    'appointment.appointment.start': { input: AppointmentRefIn; output: AppointmentOut };
    'appointment.appointment.complete': { input: AppointmentRefIn; output: AppointmentOut };
    'appointment.appointment.mark_no_show': { input: AppointmentRefIn; output: AppointmentOut };
    'appointment.appointment.cancel': { input: CancelIn; output: AppointmentOut };
    'appointment.appointment.delete': { input: AppointmentRefIn; output: DeletedOut };
    'appointment.appointment.bulk_delete': { input: { ids: string[] }; output: { deleted: string[] } };
    'appointment.appointment.charge': { input: AppointmentRefIn; output: ChargeOut };
    'appointment.agenda.lanes': { input: LanesIn; output: LanesOut };
    'appointment.availability.slots': { input: SlotsIn; output: SlotsOut };
    'appointment.availability.check': { input: CheckIn; output: CheckOut };
    'appointment.blocked_time.list': { input: BlockedTimeListIn; output: Page<BlockedTimeOut> };
    'appointment.blocked_time.create': { input: BlockedTimeCreateIn; output: BlockedTimeOut };
    'appointment.blocked_time.delete': { input: { id: string }; output: DeletedOut };
    'appointment.recurring.list': { input: RecurringListIn; output: Page<RecurringOut> };
    'appointment.recurring.get': { input: { id: string; from_date?: string | null }; output: RecurringDetailOut };
    'appointment.recurring.create': { input: RecurringCreateIn; output: MaterializeOut };
    'appointment.recurring.materialize': {
      input: { id: string; from_date?: string | null; to_date?: string | null };
      output: MaterializeOut;
    };
    'appointment.recurring.update': { input: RecurringUpdateIn; output: RecurringUpdatedOut };
    'appointment.recurring.activate': { input: { id: string }; output: RecurringOut };
    'appointment.recurring.deactivate': { input: { id: string }; output: RecurringOut };
    'appointment.recurring.delete': { input: { id: string }; output: { id: string } };
    'appointment.settings.get': { input: NoInput; output: SettingsOut };
    'appointment.settings.update': { input: SettingsIn; output: SettingsOut };
  }
}

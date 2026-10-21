// Types of the reservation app's operations for the SDK (`useLive`, `useCommand`, `client.api.call`), from
// apps/reservation/schemas.py. Written by hand, as the other apps', until V3 generates them from
// `/api/openapi.json`. Keep it in step with schemas.py and `frontend/generated/operations.json`.
// One input per operation (ninja's parity): no path parameters, an id travels in the input.
// On the wire: a reservation's day `YYYY-MM-DD` and time `HH:MM:SS` on the business's wall clock;
// moments ISO 8601 with their zone.
import type { Page } from '../../../frontend/sdk-types';

export type ReservationStatus = 'pending' | 'confirmed' | 'seated' | 'completed' | 'cancelled' | 'no_show';
export type ReservationSource = 'phone' | 'in_person' | 'waitlist' | 'whatsapp' | 'online';
export type BookingSource = 'phone' | 'in_person' | 'whatsapp' | 'online';

interface PageIn {
  limit?: number;
  offset?: number;
}

type NoInput = Record<string, never>;

export interface DeletedOut {
  id: string;
}

// ── Reservations ─────────────────────────────────────────────────────────────────────────────────

export interface ReservationListIn extends PageIn {
  search?: string;
  date_from?: string;
  date_to?: string;
  status?: ReservationStatus;
  table_id?: string;
  customer_id?: string;
  guest_name?: string;
  guest_phone?: string;
  time?: string;
  party_size_from?: number;
  party_size_to?: number;
  /** A column, `-` first for descending (`starts_at` = day and time). */
  sort?: string;
}

export interface ReservationRefIn {
  id?: string | null;
  guest?: string | null;
  day?: string | null;
}

export interface ReservationIn {
  customer_id?: string | null;
  customer?: string | null;
  guest_name?: string;
  guest_phone?: string;
  guest_email?: string;
  date: string;
  time: string;
  party_size: number;
  duration_minutes?: number | null;
  table_id?: string | null;
  table?: string | null;
  zone?: string | null;
  source?: BookingSource;
  notes?: string;
  internal_notes?: string;
  overbook?: boolean;
}

export interface ReservationPatchIn extends ReservationRefIn {
  guest_name?: string;
  guest_phone?: string;
  guest_email?: string;
  date?: string;
  time?: string;
  party_size?: number;
  duration_minutes?: number;
  table_id?: string | null;
  table?: string | null;
  zone?: string | null;
  no_table?: boolean;
  notes?: string;
  internal_notes?: string;
  overbook?: boolean;
  on_behalf_of?: string | null;
}

export interface CancelIn extends ReservationRefIn {
  reason?: string;
  on_behalf_of?: string | null;
}

export interface ReservationOut {
  id: string;
  customer_id: string | null;
  /** Empty once the customer's data was erased («Deleted customer»). */
  guest_name: string;
  guest_phone: string;
  guest_email: string;
  date: string;
  time: string;
  end_time: string;
  duration_minutes: number;
  party_size: number;
  table_id: string | null;
  /** «5 (Terrace)»; empty without a table. */
  table_label: string;
  table_capacity: number | null;
  status: ReservationStatus;
  source: ReservationSource;
  notes: string;
  internal_notes: string;
  /** «unconfirmed» = released by the book. */
  cancellation_reason: string;
  confirmed_at: string | null;
  seated_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  no_show_at: string | null;
  table_session_id: string | null;
  waitlist_entry_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReleasedOut {
  released: number;
}

// ── Availability ─────────────────────────────────────────────────────────────────────────────────

export interface DayIn {
  date?: string | null;
}

export interface BlockedDateOut {
  id: string;
  date: string;
  reason: string;
  is_full_day: boolean;
  blocked_from: string | null;
  blocked_until: string | null;
}

export interface SpanOut {
  /** Wall clock, no zone (`2026-10-15T13:00:00`). */
  start: string;
  end: string;
}

export interface SlotLoadOut {
  id: string;
  start_time: string;
  end_time: string;
  max_reservations: number;
  max_covers: number | null;
  reserved: number;
  covers: number;
  available: number;
  full: boolean;
  in_hours: boolean;
}

export interface DayOut {
  date: string;
  today: string;
  timezone: string;
  closed: boolean;
  blocks: BlockedDateOut[];
  hours_restricted: boolean;
  spans: SpanOut[];
  slots: SlotLoadOut[];
  reservations: number;
  covers: number;
}

export interface TablesIn {
  date: string;
  time: string;
  duration_minutes?: number | null;
  party_size?: number | null;
  exclude_id?: string | null;
  search?: string;
}

export interface FreeTableOut {
  id: string;
  number: string;
  label: string;
  zone_name: string;
  capacity: number;
  fits: boolean;
  free: boolean;
  taken_from: string | null;
  taken_until: string | null;
}

export interface FreeTablesOut {
  rows: FreeTableOut[];
}

// ── Slots and blocked dates ──────────────────────────────────────────────────────────────────────

export interface TimeSlotListIn extends PageIn {
  day_of_week?: number;
  sort?: string;
}

export interface TimeSlotIn {
  day_of_week: number;
  start_time: string;
  end_time: string;
  max_reservations?: number;
  max_covers?: number | null;
}

export interface TimeSlotRefIn {
  id?: string | null;
  day_of_week?: number | null;
  start_time?: string | null;
}

export interface TimeSlotOut {
  id: string;
  day_of_week: number;
  start_time: string;
  end_time: string;
  max_reservations: number;
  max_covers: number | null;
}

export interface BlockedDateListIn extends PageIn {
  date_from?: string;
  date_to?: string;
  is_full_day?: boolean;
  sort?: string;
}

export interface BlockedDateIn {
  date: string;
  reason?: string;
  is_full_day?: boolean;
  blocked_from?: string | null;
  blocked_until?: string | null;
}

export interface BlockedDateRefIn {
  id?: string | null;
  date?: string | null;
}

// ── Waitlist ─────────────────────────────────────────────────────────────────────────────────────

export interface WaitlistListIn extends PageIn {
  search?: string;
  date_from?: string;
  date_to?: string;
  is_contacted?: boolean;
  is_converted?: boolean;
  guest_name?: string;
  guest_phone?: string;
  sort?: string;
}

export interface WaitlistIn {
  customer_id?: string | null;
  customer?: string | null;
  guest_name?: string;
  guest_phone?: string;
  guest_email?: string;
  date: string;
  preferred_time: string;
  party_size: number;
  notes?: string;
}

export interface WaitlistRefIn {
  id?: string | null;
  guest?: string | null;
  day?: string | null;
}

export interface WaitlistConvertIn extends WaitlistRefIn {
  overbook?: boolean;
}

export interface WaitlistPatchIn extends WaitlistRefIn {
  is_contacted?: boolean;
  notes?: string;
}

export interface WaitlistOut {
  id: string;
  customer_id: string | null;
  guest_name: string;
  guest_phone: string;
  guest_email: string;
  date: string;
  preferred_time: string;
  party_size: number;
  notes: string;
  is_contacted: boolean;
  contacted_at: string | null;
  is_converted: boolean;
  reservation_id: string | null;
  created_at: string;
}

export interface ConvertedOut {
  entry: WaitlistOut;
  reservation: ReservationOut;
}

// ── Settings ─────────────────────────────────────────────────────────────────────────────────────

export interface SettingsIn {
  min_party_size?: number;
  max_party_size?: number;
  min_advance_hours?: number;
  max_advance_days?: number;
  default_duration_minutes?: number;
  auto_confirm?: boolean;
  require_phone?: boolean;
  require_email?: boolean;
  no_show_window_minutes?: number;
}

export interface SettingsOut {
  min_party_size: number;
  max_party_size: number;
  min_advance_hours: number;
  max_advance_days: number;
  default_duration_minutes: number;
  auto_confirm: boolean;
  require_phone: boolean;
  require_email: boolean;
  no_show_window_minutes: number;
  timezone: string;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'reservation.reservation.list': { input: ReservationListIn; output: Page<ReservationOut> };
    'reservation.reservation.get': { input: ReservationRefIn; output: ReservationOut };
    'reservation.reservation.create': { input: ReservationIn; output: ReservationOut };
    'reservation.reservation.update': { input: ReservationPatchIn; output: ReservationOut };
    'reservation.reservation.confirm': { input: ReservationRefIn; output: ReservationOut };
    'reservation.reservation.seat': { input: ReservationRefIn; output: ReservationOut };
    'reservation.reservation.complete': { input: ReservationRefIn; output: ReservationOut };
    'reservation.reservation.cancel': { input: CancelIn; output: ReservationOut };
    'reservation.reservation.no_show': { input: ReservationRefIn; output: ReservationOut };
    'reservation.reservation.delete': { input: ReservationRefIn; output: DeletedOut };
    'reservation.reservation.release_unconfirmed': { input: NoInput; output: ReleasedOut };
    'reservation.availability.day': { input: DayIn; output: DayOut };
    'reservation.availability.tables': { input: TablesIn; output: FreeTablesOut };
    'reservation.time_slot.list': { input: TimeSlotListIn; output: Page<TimeSlotOut> };
    'reservation.time_slot.create': { input: TimeSlotIn; output: TimeSlotOut };
    'reservation.time_slot.delete': { input: TimeSlotRefIn; output: DeletedOut };
    'reservation.blocked_date.list': { input: BlockedDateListIn; output: Page<BlockedDateOut> };
    'reservation.blocked_date.create': { input: BlockedDateIn; output: BlockedDateOut };
    'reservation.blocked_date.delete': { input: BlockedDateRefIn; output: DeletedOut };
    'reservation.waitlist.list': { input: WaitlistListIn; output: Page<WaitlistOut> };
    'reservation.waitlist.create': { input: WaitlistIn; output: WaitlistOut };
    'reservation.waitlist.update': { input: WaitlistPatchIn; output: WaitlistOut };
    'reservation.waitlist.convert': { input: WaitlistConvertIn; output: ConvertedOut };
    'reservation.waitlist.delete': { input: WaitlistRefIn; output: DeletedOut };
    'reservation.settings.get': { input: NoInput; output: SettingsOut };
    'reservation.settings.update': { input: SettingsIn; output: SettingsOut };
  }
}

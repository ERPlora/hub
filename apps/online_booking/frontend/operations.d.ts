// Types of the online booking app's operations for the SDK (`useLive`, `useCommand`), from
// apps/online_booking/schemas.py. Written by hand, as `frontend/sdk-types.d.ts` is for the PoC, until V3
// generates them from `/api/openapi.json`. Keep it in step with schemas.py and with
// `frontend/generated/operations.json`. One input per operation (ninja's parity): no path parameters.
// Times come on the business's clock with their offset (`2030-03-05T10:00:00+01:00`); days are `YYYY-MM-DD`.
import type { Page } from '../../../frontend/sdk-types';

export type SortDir = 'asc' | 'desc';
export type BookingStatus = 'pending' | 'confirmed' | 'in_progress' | 'completed' | 'cancelled' | 'no_show';
export type BookingSort = 'booked_at' | 'start' | 'number' | 'customer_name' | 'staff_name' | 'status';

export interface NoIn {
  [key: string]: never;
}

// ── The inbox ──────────────────────────────────────────────────────────────────────────────────

export interface BookingListIn {
  limit?: number;
  offset?: number;
  search?: string;
  number?: string;
  customer_name?: string;
  service?: string;
  staff_name?: string;
  status?: BookingStatus;
  date_from?: string;
  date_to?: string;
  staff_id?: string;
  sort?: BookingSort;
  dir?: SortDir;
}

/** A booking by id, number, or the customer (name, phone or email) and the day. */
export interface BookingRefIn {
  id?: string;
  number?: string;
  customer?: string;
  date?: string;
}

export interface CancelIn extends BookingRefIn {
  reason?: string;
}

export interface LineOut {
  service_id: string;
  name: string;
  price: number;
  duration_minutes: number;
}

export interface BookingRow {
  id: string;
  number: string;
  customer_id: string;
  customer_name: string;
  customer_phone: string;
  customer_email: string;
  staff_id: string | null;
  staff_name: string;
  services: LineOut[];
  service_names: string;
  start: string;
  end: string;
  duration_minutes: number;
  status: BookingStatus;
  total: number;
  notes: string;
  booked_at: string;
  via_page: boolean;
  sale_id: string | null;
  order_id: string | null;
}

export interface BookingOut extends BookingRow {
  cancelled_at: string | null;
  cancellation_reason: string;
  cancelled_by_customer: boolean;
}

export interface DeletedOut {
  id: string;
  deleted: boolean;
}

// ── Settings ───────────────────────────────────────────────────────────────────────────────────

export interface SettingsOut {
  is_enabled: boolean;
  page_title: string;
  welcome_message: string;
  primary_color: string;
  logo_url: string;
  require_email: boolean;
  max_upcoming_per_customer: number;
  allow_staff_selection: boolean;
  allow_notes: boolean;
  confirmation_message: string;
  cancellation_policy: string;
  min_booking_notice: number;
  max_advance_booking: number;
  slot_interval: number;
  auto_confirm_online: boolean;
  allow_customer_cancellation: boolean;
  cancellation_notice_hours: number;
  timezone: string;
}

/** Only what is sent changes, all of it or nothing. */
export type SettingsIn = Partial<Omit<SettingsOut, 'timezone'>>;

// ── The public page ────────────────────────────────────────────────────────────────────────────

export interface PageOut {
  title: string;
  welcome_message: string;
  primary_color: string;
  logo_url: string;
  require_email: boolean;
  allow_staff_selection: boolean;
  allow_notes: boolean;
  cancellation_policy: string;
  min_booking_notice: number;
  max_advance_booking: number;
  allow_customer_cancellation: boolean;
  cancellation_notice_hours: number;
  timezone: string;
}

export interface PublicServicesIn {
  limit?: number;
  offset?: number;
  search?: string;
}

export interface ProfessionalOut {
  id: string;
  name: string;
}

export interface PublicServiceOut {
  id: string;
  name: string;
  description: string;
  category: string;
  price: number | null;
  duration_minutes: number | null;
  professionals: ProfessionalOut[];
}

export interface PublicSlotsIn {
  service_ids: string[];
  date: string;
  staff_id?: string;
}

export interface PublicSlotOut {
  start: string;
  end: string;
  professionals: ProfessionalOut[];
}

export interface PublicSlotsOut {
  date: string;
  timezone: string;
  duration_minutes: number;
  slots: PublicSlotOut[];
}

export interface PublicBookIn {
  service_ids: string[];
  staff_id?: string;
  start: string;
  name: string;
  phone: string;
  email?: string;
  notes?: string;
}

export interface BookedOut {
  number: string;
  status: BookingStatus;
  start: string;
  end: string;
  timezone: string;
  service_names: string;
  staff_name: string;
  message: string;
  token: string;
}

export interface TokenIn {
  token: string;
}

export interface PublicCancelIn extends TokenIn {
  reason?: string;
}

export interface PublicBookingOut {
  number: string;
  status: BookingStatus;
  start: string;
  end: string;
  timezone: string;
  service_names: string;
  staff_name: string;
  can_cancel: boolean;
  cancel_until: string | null;
  cancellation_policy: string;
}

// Services' hand-written `ServicePatchIn` lacks a field its server takes (`allow_online_booking`, schemas.py
// `ServicePatchIn`): the settings' «Online booking» switch sends it. Augmented here until Services' types say it.
declare module '../../service/frontend/operations' {
  interface ServicePatchIn {
    allow_online_booking?: boolean;
  }
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'online_booking.booking.list': { input: BookingListIn; output: Page<BookingRow> };
    'online_booking.booking.get': { input: BookingRefIn; output: BookingOut };
    'online_booking.booking.confirm': { input: BookingRefIn; output: BookingOut };
    'online_booking.booking.complete': { input: BookingRefIn; output: BookingOut };
    'online_booking.booking.no_show': { input: BookingRefIn; output: BookingOut };
    'online_booking.booking.cancel': { input: CancelIn; output: BookingOut };
    'online_booking.booking.delete': { input: BookingRefIn; output: DeletedOut };
    'online_booking.settings.get': { input: NoIn; output: SettingsOut };
    'online_booking.settings.update': { input: SettingsIn; output: SettingsOut };
    'online_booking.public.page': { input: NoIn; output: PageOut };
    'online_booking.public.services': { input: PublicServicesIn; output: Page<PublicServiceOut> };
    'online_booking.public.slots': { input: PublicSlotsIn; output: PublicSlotsOut };
    'online_booking.public.booking': { input: TokenIn; output: PublicBookingOut };
    'online_booking.public.book': { input: PublicBookIn; output: BookedOut };
    'online_booking.public.cancel': { input: PublicCancelIn; output: PublicBookingOut };
  }
}

// Rows of the reservation app's reads, as the server answers them, for the page and component tests.
import type { DayOut, FreeTableOut, ReservationOut, SlotLoadOut, TimeSlotOut, BlockedDateOut, WaitlistOut, SettingsOut } from '../operations';

export function reservationRow(overrides: Partial<ReservationOut> = {}): ReservationOut {
  return {
    id: 'r1',
    customer_id: 'c1',
    guest_name: 'Ana García',
    guest_phone: '+34600111222',
    guest_email: '',
    date: '2026-10-15',
    time: '21:00:00',
    end_time: '23:00:00',
    date_label: 'Thursday, October 15, 2026',
    time_label: '21:00',
    duration_minutes: 120,
    party_size: 4,
    table_id: 't5',
    table_label: '5 (Terrace)',
    table_capacity: 4,
    status: 'pending',
    source: 'phone',
    notes: '',
    internal_notes: '',
    cancellation_reason: '',
    confirmed_at: null,
    seated_at: null,
    completed_at: null,
    cancelled_at: null,
    no_show_at: null,
    table_session_id: null,
    waitlist_entry_id: null,
    created_at: '2026-10-14T10:00:00Z',
    updated_at: '2026-10-14T10:00:00Z',
    ...overrides,
  };
}

export function slotLoad(overrides: Partial<SlotLoadOut> = {}): SlotLoadOut {
  return {
    id: 's-dinner',
    start_time: '20:00:00',
    end_time: '23:30:00',
    max_reservations: 10,
    max_covers: null,
    reserved: 3,
    covers: 9,
    available: 7,
    full: false,
    in_hours: true,
    ...overrides,
  };
}

export function dayOut(overrides: Partial<DayOut> = {}): DayOut {
  return {
    date: '2026-10-15',
    today: '2026-10-15',
    timezone: 'Europe/Madrid',
    closed: false,
    blocks: [],
    hours_restricted: false,
    spans: [],
    slots: [slotLoad({ id: 's-lunch', start_time: '13:00:00', end_time: '16:00:00', reserved: 1, covers: 2, available: 9 }), slotLoad()],
    reservations: 4,
    covers: 11,
    ...overrides,
  };
}

export function freeTable(overrides: Partial<FreeTableOut> = {}): FreeTableOut {
  return {
    id: 't5',
    number: '5',
    label: '5 (Terrace)',
    zone_name: 'Terrace',
    capacity: 4,
    fits: true,
    free: true,
    taken_from: null,
    taken_until: null,
    ...overrides,
  };
}

export function slotRow(overrides: Partial<TimeSlotOut> = {}): TimeSlotOut {
  return { id: 'ts1', day_of_week: 3, start_time: '20:00:00', end_time: '23:30:00', max_reservations: 10, max_covers: null, ...overrides };
}

export function blockedRow(overrides: Partial<BlockedDateOut> = {}): BlockedDateOut {
  return { id: 'b1', date: '2026-12-25', reason: 'Christmas', is_full_day: true, blocked_from: null, blocked_until: null, ...overrides };
}

export function entryRow(overrides: Partial<WaitlistOut> = {}): WaitlistOut {
  return {
    id: 'w1',
    customer_id: 'c2',
    guest_name: 'Luis Pérez',
    guest_phone: '+34600333444',
    guest_email: '',
    date: '2026-10-15',
    preferred_time: '21:00:00',
    party_size: 2,
    notes: '',
    is_contacted: false,
    contacted_at: null,
    is_converted: false,
    reservation_id: null,
    created_at: '2026-10-14T10:00:00Z',
    ...overrides,
  };
}

export function settingsOut(overrides: Partial<SettingsOut> = {}): SettingsOut {
  return {
    min_party_size: 1,
    max_party_size: 20,
    min_advance_hours: 1,
    max_advance_days: 30,
    default_duration_minutes: 120,
    auto_confirm: false,
    require_phone: true,
    require_email: false,
    no_show_window_minutes: 15,
    timezone: 'Europe/Madrid',
    ...overrides,
  };
}

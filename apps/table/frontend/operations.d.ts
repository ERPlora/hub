// Types of the table app's operations for the SDK (`useLive`, `useCommand`, `client.api.call`), from
// apps/table/schemas.py. Written by hand, as the other apps', until V3 generates them from
// `/api/openapi.json`. Keep it in step with schemas.py and `frontend/generated/operations.json`.
// One input per operation (ninja's parity): no path parameters, an id travels in the input.
// On the wire: moments ISO 8601 with their zone, money in whole cents.
import type { Page } from '../../../frontend/sdk-types';

export type ZoneColor = 'primary' | 'secondary' | 'tertiary' | 'success' | 'warning' | 'danger' | 'medium';
export type TableShape = 'square' | 'round' | 'rectangle';
export type TableStatus = 'available' | 'occupied' | 'reserved' | 'blocked';
export type SessionStatus = 'open' | 'closed' | 'transferred' | 'merged' | 'parked';
export type HoldSource = 'manual' | 'reservation';
export type HoldStatus = 'held' | 'consumed' | 'released' | 'expired';

interface PageIn {
  limit?: number;
  offset?: number;
}

type NoInput = Record<string, never>;

export interface DeletedOut {
  id: string;
}

// ── Zones ──────────────────────────────────────────────────────────────────────────────────────

export interface ZoneRefIn {
  id?: string | null;
  zone?: string | null;
}

export interface ZoneListIn extends PageIn {
  search?: string;
  name?: string;
  color?: ZoneColor;
  is_active?: boolean;
  /** A column, `-` first for descending. */
  sort?: string;
}

export interface ZoneIn {
  name: string;
  description?: string;
  color?: ZoneColor;
  sort_order?: number | null;
}

export interface ZonePatchIn extends ZoneRefIn {
  name?: string;
  description?: string;
  color?: ZoneColor;
  sort_order?: number;
  is_active?: boolean;
}

export interface ZoneOut {
  id: string;
  name: string;
  description: string;
  color: ZoneColor;
  sort_order: number;
  is_active: boolean;
  table_count: number;
  available_count: number;
}

// ── Tables ─────────────────────────────────────────────────────────────────────────────────────

export interface TableRefIn {
  id?: string | null;
  table?: string | null;
  zone?: string | null;
}

export interface TableListIn extends PageIn {
  search?: string;
  number?: string;
  name?: string;
  zone_id?: string;
  zone?: string;
  status?: TableStatus;
  shape?: TableShape;
  is_active?: boolean;
  in_service?: boolean;
  capacity_min?: number;
  capacity_max?: number;
  sort?: string;
}

export interface TableIn {
  zone_id?: string | null;
  zone?: string | null;
  number?: string | null;
  name?: string;
  capacity?: number;
  shape?: TableShape;
  position_x?: number | null;
  position_y?: number | null;
  width?: number | null;
  height?: number | null;
}

export interface TableBulkIn {
  zone_id?: string | null;
  zone?: string | null;
  count: number;
  prefix?: string;
  start_number?: number;
  capacity?: number;
  shape?: TableShape;
}

export interface TablePatchIn extends TableRefIn {
  number?: string;
  name?: string;
  capacity?: number;
  shape?: TableShape;
  move_to_zone_id?: string | null;
  move_to_zone?: string | null;
  blocked?: boolean;
  is_active?: boolean;
}

export interface TableMoveIn {
  id: string;
  position_x: number;
  position_y: number;
  width?: number | null;
  height?: number | null;
}

export interface HoldShownOut {
  label: string;
  erased: boolean;
  held_from: string;
  held_until: string;
  party_size: number;
  reserving: boolean;
}

export interface TableCheckOut {
  id: string;
  order_id: string | null;
  guests_count: number;
  opened_at: string;
  waiter_name: string;
  customer_id: string | null;
  customer_name: string | null;
  split_from_id: string | null;
}

export interface TableOut {
  id: string;
  number: string;
  name: string;
  capacity: number;
  shape: TableShape;
  status: TableStatus;
  blocked: boolean;
  is_active: boolean;
  zone_id: string | null;
  zone_name: string | null;
  in_service: boolean;
  position_x: number;
  position_y: number;
  width: number;
  height: number;
  guests: number | null;
  since: string | null;
  waiter_name: string;
  checks: TableCheckOut[];
  hold: HoldShownOut | null;
}

export interface TablesOut {
  rows: TableOut[];
}

// ── Table checks ───────────────────────────────────────────────────────────────────────────────

export interface SessionRefIn {
  id?: string | null;
  table?: string | null;
  zone?: string | null;
}

export interface SessionListIn extends PageIn {
  search?: string;
  table_number?: string;
  status?: SessionStatus;
  zone_id?: string;
  waiter_id?: string;
  table_id?: string;
  opened_from?: string;
  opened_to?: string;
  sort?: string;
}

export interface SessionOut {
  id: string;
  table_id: string | null;
  table_number: string | null;
  zone_id: string | null;
  zone_name: string | null;
  order_id: string | null;
  guests_count: number;
  status: SessionStatus;
  waiter_id: string;
  waiter_name: string;
  opened_at: string;
  closed_at: string | null;
  notes: string;
  split_from_id: string | null;
  transferred_from_id: string | null;
  merged_into_id: string | null;
  paid_total: number | null;
  /** The currency its check was charged in (its sales', never rewritten) and its decimals as the server counts them
   *  (0 in JPY); null while nothing is charged. */
  currency: string | null;
  currency_decimals: number | null;
  customer_id: string | null;
  customer_name: string | null;
}

export interface SessionsOut {
  rows: SessionOut[];
}

export interface SessionOpenIn {
  table_id?: string | null;
  table?: string | null;
  zone?: string | null;
  guests_count?: number | null;
  notes?: string;
  order_id?: string | null;
  customer_id?: string | null;
  customer?: string | null;
  reservation_id?: string | null;
}

export interface SessionCloseIn extends SessionRefIn {
  order_id?: string | null;
  notes?: string | null;
}

export interface SessionTransferIn extends SessionRefIn {
  to_table_id?: string | null;
  to_table?: string | null;
  to_zone?: string | null;
}

export interface SessionMergeIn extends SessionRefIn {
  into_session_id?: string | null;
  into_table_id?: string | null;
  into_table?: string | null;
  into_zone?: string | null;
}

export interface SessionSplitIn extends SessionRefIn {
  line_ids?: string[];
  guests_count?: number;
  notes?: string;
}

export interface SessionGuestsIn extends SessionRefIn {
  guests_count: number;
}

export interface SessionRestoreIn {
  id: string;
  table_id?: string | null;
  table?: string | null;
  zone?: string | null;
}

export interface SessionLinkOrderIn extends SessionRefIn {
  order_id: string;
}

export interface ByIdIn {
  id: string;
}

export interface ByOrderIn {
  order_id: string;
}

export interface SplitOut {
  session: SessionOut;
  new_session: SessionOut;
}

// ── Waiters, floor and settings ────────────────────────────────────────────────────────────────

export interface WaiterListIn extends PageIn {
  search?: string;
}

export interface WaiterOut {
  id: string;
  name: string;
}

export interface FloorStatusOut {
  usable_tables: number;
  zones: number;
}

export interface SettingsOut {
  prompt_guests_on_seat: boolean;
  timer_warning_minutes: number;
  timer_critical_minutes: number;
  reserved_lead_minutes: number;
  timezone: string;
}

export interface SettingsIn {
  prompt_guests_on_seat?: boolean;
  timer_warning_minutes?: number;
  timer_critical_minutes?: number;
}

// ── Holds ──────────────────────────────────────────────────────────────────────────────────────

export interface HoldPlaceIn {
  table_id?: string | null;
  table?: string | null;
  zone?: string | null;
  source_ref: string;
  held_from: string;
  held_until: string;
  party_size?: number;
  label?: string;
}

export interface HoldReleaseIn {
  source?: HoldSource;
  source_ref: string;
}

export interface HoldOut {
  id: string;
  table_id: string;
  source: HoldSource;
  source_ref: string;
  held_from: string;
  held_until: string;
  party_size: number;
  label: string;
  status: HoldStatus;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'table.zone.list': { input: ZoneListIn; output: Page<ZoneOut> };
    'table.zone.get': { input: ZoneRefIn; output: ZoneOut };
    'table.zone.create': { input: ZoneIn; output: ZoneOut };
    'table.zone.update': { input: ZonePatchIn; output: ZoneOut };
    'table.zone.delete': { input: ZoneRefIn; output: DeletedOut };
    'table.table.list': { input: TableListIn; output: Page<TableOut> };
    'table.table.get': { input: TableRefIn; output: TableOut };
    'table.table.create': { input: TableIn; output: TableOut };
    'table.table.bulk_create': { input: TableBulkIn; output: TablesOut };
    'table.table.update': { input: TablePatchIn; output: TableOut };
    'table.table.move': { input: TableMoveIn; output: TableOut };
    'table.table.delete': { input: TableRefIn; output: DeletedOut };
    'table.session.list': { input: SessionListIn; output: Page<SessionOut> };
    'table.session.get': { input: SessionRefIn; output: SessionOut };
    'table.session.by_order': { input: ByOrderIn; output: SessionsOut };
    'table.session.open': { input: SessionOpenIn; output: SessionOut };
    'table.session.close': { input: SessionCloseIn; output: SessionOut };
    'table.session.transfer': { input: SessionTransferIn; output: SessionOut };
    'table.session.merge': { input: SessionMergeIn; output: SessionOut };
    'table.session.split': { input: SessionSplitIn; output: SplitOut };
    'table.session.set_guests': { input: SessionGuestsIn; output: SessionOut };
    'table.session.park': { input: SessionRefIn; output: SessionOut };
    'table.session.restore': { input: SessionRestoreIn; output: SessionOut };
    'table.session.link_order': { input: SessionLinkOrderIn; output: SessionOut };
    'table.session.delete': { input: ByIdIn; output: DeletedOut };
    'table.waiter.list': { input: WaiterListIn; output: Page<WaiterOut> };
    'table.floor.status': { input: NoInput; output: FloorStatusOut };
    'table.settings.get': { input: NoInput; output: SettingsOut };
    'table.settings.update': { input: SettingsIn; output: SettingsOut };
    'table.hold.place': { input: HoldPlaceIn; output: HoldOut };
    'table.hold.release': { input: HoldReleaseIn; output: HoldOut };
  }
}

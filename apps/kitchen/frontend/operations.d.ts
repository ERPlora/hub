// Types of the kitchen app's operations for the SDK (`useLive`, `useCommand`, `client.api.call`), from
// apps/kitchen/schemas.py. Written by hand, as the other apps', until V3 generates them from
// `/api/openapi.json`. Keep it in step with schemas.py and `frontend/generated/operations.json`.
// One input per operation (ninja's parity): no path parameters, an id travels in the input.
// On the wire: moments ISO 8601 with their zone, money in whole cents, quantities as decimal strings.
import type { Page } from '../../../frontend/sdk-types';

export type TicketStatus = 'pending' | 'preparing' | 'ready' | 'served' | 'cancelled';
export type ItemStatus = 'pending' | 'preparing' | 'ready' | 'served' | 'cancelled' | 'voided';
export type OrderType = 'dine_in' | 'takeaway' | 'delivery';
export type Priority = 'normal' | 'rush' | 'vip';
export type Destination = 'both' | 'display' | 'printer';
export type PrinterUsage = 'kitchen' | 'bar';
export type SoundTone = 'chime' | 'bell' | 'buzzer';
export type LogAction =
  | 'received'
  | 'created'
  | 'started'
  | 'ready'
  | 'item_ready'
  | 'item_recalled'
  | 'item_voided'
  | 'served'
  | 'recalled'
  | 'cancelled'
  | 'rushed'
  | 'unrushed'
  | 'reprinted'
  | 'deleted';

interface PageIn {
  limit?: number;
  offset?: number;
}

type NoInput = Record<string, never>;

export interface DeletedOut {
  id: string;
}

// ── Tickets ────────────────────────────────────────────────────────────────────────────────────

export interface TicketRefIn {
  ticket_id?: string | null;
  ticket?: string | null;
}

export interface ItemOut {
  id: string;
  position: number;
  product_id: string | null;
  name: string;
  /** A decimal: `"2.000"`. */
  quantity: string;
  unit: string;
  notes: string;
  station_id: string | null;
  station_name: string;
  station_color: string;
  destination: Destination;
  printer_usage: PrinterUsage;
  status: ItemStatus;
  void_reason: string;
  ready_at: string | null;
}

export interface TicketOut {
  id: string;
  number: string;
  short_number: string;
  label: string;
  order_type: OrderType;
  priority: Priority;
  status: TicketStatus;
  round_no: number;
  waiter: string;
  notes: string;
  order_id: string | null;
  received_at: string;
  started_at: string | null;
  ready_at: string | null;
  served_at: string | null;
  cancelled_at: string | null;
  rush_count: number;
  total: number;
  saved: boolean;
  items: ItemOut[];
  print_error: string | null;
}

export interface StationChipOut {
  id: string | null;
  name: string;
  color: string;
}

export interface BoardIn {
  /** A station's id or name, `none` (no station), or nothing (every station). */
  station?: string | null;
}

export interface BoardOut {
  cooking: TicketOut[];
  ready: TicketOut[];
  cooking_count: number;
  ready_count: number;
  stations: StationChipOut[];
  truncated: boolean;
}

export interface AllDayRowOut {
  product_id: string | null;
  name: string;
  unit: string;
  station_id: string | null;
  station_name: string;
  quantity: string;
}

export interface AllDayOut {
  rows: AllDayRowOut[];
}

export interface TicketListIn extends PageIn {
  search?: string;
  status?: TicketStatus;
  order_type?: OrderType;
  priority?: Priority;
  /** A column, `-` first for descending. */
  sort?: string;
}

export interface TicketRowOut {
  id: string;
  number: string;
  short_number: string;
  label: string;
  order_type: OrderType;
  priority: Priority;
  status: TicketStatus;
  round_no: number;
  items_count: number;
  total: number;
  received_at: string;
  order_id: string | null;
  saved: boolean;
}

export interface ByOrderIn {
  order_id: string;
}

export interface TicketsOut {
  tickets: TicketOut[];
}

export interface TicketSendIn {
  order_id: string;
  label?: string;
  channel?: OrderType;
  priority?: 'normal' | 'rush';
}

export interface ManualItemIn {
  product_id?: string | null;
  product?: string | null;
  name?: string;
  quantity?: string;
  notes?: string;
}

export interface TicketCreateIn {
  order_type?: OrderType | null;
  label?: string;
  notes?: string;
  items: ManualItemIn[];
}

export interface TicketCancelIn extends TicketRefIn {
  reason?: string;
}

export interface TicketRushIn extends TicketRefIn {
  rush?: boolean;
}

export interface ItemBumpIn extends TicketRefIn {
  item_ids?: string[];
  station?: string | null;
}

// ── Stations and routing ───────────────────────────────────────────────────────────────────────

export interface StationRefIn {
  station_id?: string | null;
  station?: string | null;
}

export interface StationListIn extends PageIn {
  search?: string;
  is_active?: boolean;
  sort?: string;
}

export interface StationOut {
  id: string;
  name: string;
  color: string;
  destination: Destination;
  printer_usage: PrinterUsage;
  printer_name: string;
  sort_order: number;
  is_active: boolean;
  in_progress: number;
  routes: number;
}

export interface StationIn {
  name: string;
  color?: string;
  destination?: Destination;
  printer_usage?: PrinterUsage;
  printer_name?: string;
  sort_order?: number;
  is_active?: boolean;
}

export interface StationPatchIn extends StationRefIn {
  name?: string;
  color?: string;
  destination?: Destination;
  printer_usage?: PrinterUsage;
  printer_name?: string;
  sort_order?: number;
  is_active?: boolean;
}

export interface RoutingListIn extends PageIn {
  station?: string | null;
  search?: string;
}

export interface RouteOut {
  kind: 'product' | 'category';
  target_id: string;
  target_name: string;
  station_id: string;
  station_name: string;
}

export interface RoutingTargetIn {
  product_id?: string | null;
  product?: string | null;
  category_id?: string | null;
  category?: string | null;
}

export interface RoutingSetIn extends RoutingTargetIn {
  station_id?: string | null;
  station?: string | null;
}

// ── Settings and history ───────────────────────────────────────────────────────────────────────

export interface SettingsOut {
  show_timer: boolean;
  warning_minutes: number;
  critical_minutes: number;
  color_coding: boolean;
  sound_enabled: boolean;
  sound_volume: number;
  sound_tone: SoundTone;
  print_pass: boolean;
  works_from_screen: boolean;
  default_order_type: OrderType;
  timezone: string;
}

export type SettingsPatchIn = Partial<Omit<SettingsOut, 'timezone'>>;

export interface LogListIn extends PageIn {
  search?: string;
  action?: LogAction;
  ticket_id?: string;
  date_from?: string;
  date_to?: string;
}

export interface LogOut {
  id: string;
  action: LogAction;
  ticket_id: string;
  ticket_number: string;
  item_name: string;
  station_name: string;
  actor: string;
  notes: string;
  created_at: string;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'kitchen.ticket.board': { input: BoardIn; output: BoardOut };
    'kitchen.ticket.all_day': { input: BoardIn; output: AllDayOut };
    'kitchen.ticket.list': { input: TicketListIn; output: Page<TicketRowOut> };
    'kitchen.ticket.get': { input: TicketRefIn; output: TicketOut };
    'kitchen.ticket.by_order': { input: ByOrderIn; output: TicketsOut };
    'kitchen.ticket.create': { input: TicketCreateIn; output: TicketOut };
    'kitchen.ticket.send': { input: TicketSendIn; output: TicketOut };
    'kitchen.ticket.start': { input: TicketRefIn; output: TicketOut };
    'kitchen.ticket.ready': { input: TicketRefIn; output: TicketOut };
    'kitchen.ticket.serve': { input: TicketRefIn; output: TicketOut };
    'kitchen.ticket.recall': { input: TicketRefIn; output: TicketOut };
    'kitchen.ticket.cancel': { input: TicketCancelIn; output: TicketOut };
    'kitchen.ticket.delete': { input: TicketRefIn; output: DeletedOut };
    'kitchen.ticket.set_rush': { input: TicketRushIn; output: TicketOut };
    'kitchen.ticket.reprint': { input: TicketRefIn; output: TicketOut };
    'kitchen.item.bump': { input: ItemBumpIn; output: TicketOut };
    'kitchen.item.recall': { input: ItemBumpIn; output: TicketOut };
    'kitchen.station.list': { input: StationListIn; output: Page<StationOut> };
    'kitchen.station.create': { input: StationIn; output: StationOut };
    'kitchen.station.update': { input: StationPatchIn; output: StationOut };
    'kitchen.station.delete': { input: StationRefIn; output: DeletedOut };
    'kitchen.routing.list': { input: RoutingListIn; output: Page<RouteOut> };
    'kitchen.routing.set': { input: RoutingSetIn; output: RouteOut };
    'kitchen.routing.clear': { input: RoutingTargetIn; output: RouteOut };
    'kitchen.settings.get': { input: NoInput; output: SettingsOut };
    'kitchen.settings.update': { input: SettingsPatchIn; output: SettingsOut };
    'kitchen.log.list': { input: LogListIn; output: Page<LogOut> };
  }
}

// Types of the kitchen app's operations for the SDK (`useLive`, `useCommand`, `client.api.call`), one module per module
// of apps/kitchen/schemas/; this one, of fields.py. Written by hand, as the other apps' are: nothing generates them
// from `/api/openapi.json`. Keep each in step with its schemas/ module and `frontend/generated/operations.json`. One
// input per operation (ninja's parity): no path parameters, an id travels in the input. On the wire: moments ISO 8601
// with their zone, money in whole cents, quantities as decimal strings.

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

export interface PageIn {
  limit?: number;
  offset?: number;
}

export type NoInput = Record<string, never>;

export interface DeletedOut {
  id: string;
}

export interface TicketRefIn {
  ticket_id?: string | null;
  ticket?: string | null;
}

export interface StationRefIn {
  station_id?: string | null;
  station?: string | null;
}

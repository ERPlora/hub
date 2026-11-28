// Types of apps/kitchen/schemas/tickets.py for the SDK; what they follow, in ./fields.d.ts.
import type { Page } from '../../../../frontend/sdk-types';
import type {
  DeletedOut,
  Destination,
  ItemStatus,
  OrderType,
  PageIn,
  PrinterUsage,
  Priority,
  TicketRefIn,
  TicketStatus,
} from './fields';

export interface ItemOut {
  id: string;
  position: number;
  product_id: string | null;
  name: string;
  /** A decimal: `"2.000"`. */
  quantity: string;
  unit: string;
  notes: string;
  /** The options chosen in the till, by the names the cook reads, in the order chosen (KITCHEN-F07). */
  modifiers: string[];
  /** The header of the menu it is a dish of; `''` out of a menu (KITCHEN-F06). */
  menu_name: string;
  /** The menu's line of the check: the dishes of one menu share it; `null` out of a menu. */
  menu_line_id: string | null;
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

export interface NoticeOut {
  id: string;
  at: string;
  number: string;
  label: string;
  dish_names: string;
  waiter: string;
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

declare module '@erplora/ui/sdk' {
  interface Operations {
    'kitchen.ticket.list': { input: TicketListIn; output: Page<TicketRowOut> };
    'kitchen.ticket.get': { input: TicketRefIn; output: TicketOut };
    'kitchen.ticket.by_order': { input: ByOrderIn; output: TicketsOut };
    'kitchen.ticket.notices': {
      input: { since?: string | null; limit?: number };
      output: { rows: NoticeOut[] };
    };
    'kitchen.ticket.create': { input: TicketCreateIn; output: TicketOut };
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
  }
}

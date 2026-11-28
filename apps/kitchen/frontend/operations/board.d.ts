// Types of apps/kitchen/schemas/board.py for the SDK; what they follow, in ./fields.d.ts.
import type { TicketOut } from './tickets';

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

declare module '@erplora/ui/sdk' {
  interface Operations {
    'kitchen.ticket.board': { input: BoardIn; output: BoardOut };
    'kitchen.ticket.all_day': { input: BoardIn; output: AllDayOut };
  }
}

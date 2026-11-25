// Types of Online orders' operations for the SDK (`useLive`, `useCommand`), from apps/online_order/schemas.py. Written by
// hand: nothing generates them from `/api/openapi.json`. Keep them in step with schemas.py and with
// `frontend/generated/operations.json`. A table is said as Tables says it (`TableRefIn`).
import type { TableRefIn } from '../../table/frontend/operations';

export interface TableCodeListIn {
  limit?: number;
  offset?: number;
}

/** A table, in the floor plan's order, with the code its QR carries: none until its QR is generated the first time. */
export interface TableCodeOut {
  table_id: string;
  /** Its number with its zone, as the floor plan names it: «5 (Terrace)». */
  table: string;
  number: string;
  zone_name: string | null;
  code: string | null;
  /** The address of the table's page, which its QR opens. */
  url: string | null;
  issued_at: string | null;
}

export interface TableCodePage {
  rows: TableCodeOut[];
  total: number;
  limit: number;
  offset: number;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'online_order.qr_code.list': { input: TableCodeListIn; output: TableCodePage };
    'online_order.qr_code.regenerate': { input: TableRefIn; output: TableCodeOut };
  }
}

import type { OrderRefIn } from '../operations';

/** The bill of an open check the device printed, as no receipt printer took it: the check notes it (TABLE-F34). */
export interface BillNoteOut {
  order_id: string;
  /** When its bill was first printed: its table shows «Bill requested» until the check is closed. */
  bill_printed_at: string;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'sale.order.note_bill': { input: OrderRefIn; output: BillNoteOut };
  }
}

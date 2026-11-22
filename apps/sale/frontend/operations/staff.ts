import type { OrderOut } from '../operations';

declare module '../operations' {
  interface OrderOut {
    /** Who serves the check (a member of Staff); `null` = whoever holds the session. */
    staff_id: string | null;
    /** Their name as Staff said it when they were chosen; empty for «me». */
    staff_name: string;
  }

  interface OrderOpenIn {
    staff_id?: string | null;
  }
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'sale.order.set_staff': { input: { order_id: string; staff_id: string | null }; output: OrderOut };
  }
}

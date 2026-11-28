// Types of apps/kitchen/schemas/rounds.py for the SDK; what they follow, in ./fields.d.ts.
import type { OrderType } from './fields';
import type { TicketOut } from './tickets';

export interface TicketSendIn {
  order_id: string;
  label?: string;
  channel?: OrderType;
  priority?: 'normal' | 'rush';
  /** Who attends the check as the till names it («Atiende»); empty: who sends it. */
  waiter?: string;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'kitchen.ticket.send': { input: TicketSendIn; output: TicketOut };
  }
}

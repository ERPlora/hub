// Types of apps/kitchen/schemas/history.py for the SDK; what they follow, in ./fields.d.ts.
import type { Page } from '../../../../frontend/sdk-types';
import type { LogAction, PageIn } from './fields';

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
  /** No person did it: the platform (the kitchen by itself, an automation, a recovery). */
  by_platform: boolean;
  notes: string;
  created_at: string;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'kitchen.log.list': { input: LogListIn; output: Page<LogOut> };
  }
}

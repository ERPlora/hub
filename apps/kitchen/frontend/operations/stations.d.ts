// Types of apps/kitchen/schemas/stations.py for the SDK; what they follow, in ./fields.d.ts.
import type { Page } from '../../../../frontend/sdk-types';
import type { DeletedOut, Destination, PageIn, PrinterUsage, StationRefIn } from './fields';

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

declare module '@erplora/ui/sdk' {
  interface Operations {
    'kitchen.station.list': { input: StationListIn; output: Page<StationOut> };
    'kitchen.station.create': { input: StationIn; output: StationOut };
    'kitchen.station.update': { input: StationPatchIn; output: StationOut };
    'kitchen.station.delete': { input: StationRefIn; output: DeletedOut };
  }
}

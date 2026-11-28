// Types of apps/kitchen/schemas/routing.py for the SDK; what they follow, in ./fields.d.ts.
import type { Page } from '../../../../frontend/sdk-types';
import type { PageIn } from './fields';

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

declare module '@erplora/ui/sdk' {
  interface Operations {
    'kitchen.routing.list': { input: RoutingListIn; output: Page<RouteOut> };
    'kitchen.routing.set': { input: RoutingSetIn; output: RouteOut };
    'kitchen.routing.clear': { input: RoutingTargetIn; output: RouteOut };
  }
}

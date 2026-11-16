// Op → route map of the hub's API, for the SDK's API client (`createLiveClient(cfg, { routes })`).
// `operations.json` is written by hand, from base/api.py, as are the types of `../sdk-types.d.ts`.
import { parseOperationRoutes } from '@erplora/ui/sdk';

import operations from './operations.json';

export const OPERATION_ROUTES = parseOperationRoutes(operations);

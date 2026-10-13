// Op → route map of the hub's API, for the SDK's API client (`createLiveClient(cfg, { routes })`).
// `operations.json` is written BY HAND for the PoC, from base/api.py and plan §4.5; V3 generates it
// (and the types of `../sdk-types.d.ts`) from `/api/openapi.json` and CI checks it is current.
import { parseOperationRoutes } from '@erplora/ui/sdk';

import operations from './operations.json';

export const OPERATION_ROUTES = parseOperationRoutes(operations);

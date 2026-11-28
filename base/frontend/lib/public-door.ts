// A public page's way in through base's public door (`base/public_door.py`), for a visitor without a session: each
// operation the page names posted to `/p/<slug>/api/<operation>` with its input as the JSON body (never the query
// string, which servers log: a personal link's token travels in it), and the business's money from the page's own HTML
// (`public-door`), since a visitor has no session to read `base.business.get` with.
import type { Money } from '@erplora/ui/components';
import { type ApiClient, createApiClient, createHeaderProvider, type HeaderDeps, type OperationRoutes, type SpaConfig } from '@erplora/ui/sdk';
import { computed, type ComputedRef } from 'vue';

import { readJsonBlock } from './embedded';

/** What a public page calls the business with, and the money it writes its amounts in (unknown without it). */
export interface PublicDoorClient {
  api: ApiClient;
  money: ComputedRef<Money | undefined>;
}

export interface DoorDeps extends HeaderDeps {
  fetchImpl: (url: string, init: RequestInit) => Promise<Response>;
  doc: Document;
}

/** What base embeds as `public-door`. */
interface DoorBlock {
  currency: string;
  currency_decimals: number;
}

export function doorRoutes(slug: string, operations: readonly string[]): OperationRoutes {
  return Object.fromEntries(operations.map((op) => [op, { method: 'post', path: `/p/${slug}/api/${op}` }]));
}

function browser(): DoorDeps {
  return {
    fetchImpl: (url, init) => globalThis.fetch(url, init),
    storage: globalThis.localStorage,
    cookies: () => document.cookie,
    randomUUID: () => globalThis.crypto.randomUUID(),
    doc: document,
  };
}

/** The business's page: its slug and the operations it calls, each asking the page's own permission (the only ones
 *  the door runs). */
export interface PublicPage {
  slug: string;
  operations: readonly string[];
}

export function openPublicDoor(config: SpaConfig, page: PublicPage, deps: DoorDeps = browser()): PublicDoorClient {
  const api = createApiClient({
    fetchImpl: deps.fetchImpl,
    headers: createHeaderProvider(config, deps),
    apiBase: '',
    routes: doorRoutes(page.slug, page.operations),
  });
  const block = readJsonBlock<DoorBlock>('public-door', deps.doc);
  return {
    api,
    money: computed(() => (block ? { currency: block.currency, decimals: block.currency_decimals } : undefined)),
  };
}

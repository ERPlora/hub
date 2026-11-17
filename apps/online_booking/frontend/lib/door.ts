// The booking page's way in through base's public door (`base/public_door.py`), for a visitor without a session: each
// public operation posted to `/p/<slug>/api/<operation>` with its input as the JSON body (never the query string, which
// servers log: the personal link's token travels in it), and the business's money from the page's own HTML
// (`public-door`), since a visitor has no session to read `base.business.get` with.
import type { Money } from '@erplora/ui/components';
import { type ApiClient, createApiClient, createHeaderProvider, type HeaderDeps, type OperationRoutes, type SpaConfig } from '@erplora/ui/sdk';
import { computed, type ComputedRef, type InjectionKey } from 'vue';

import { readJsonBlock } from '../../../../base/frontend/lib/home';

/** The operations of the page (they ask `online_booking.public`, the one permission the door holds). */
export const PUBLIC_OPERATIONS = [
  'online_booking.public.page',
  'online_booking.public.services',
  'online_booking.public.slots',
  'online_booking.public.book',
  'online_booking.public.booking',
  'online_booking.public.cancel',
] as const;

/** What the page calls the business with, and the money it writes its prices in (unknown without it). */
export interface PublicDoor {
  api: ApiClient;
  money: ComputedRef<Money | undefined>;
}

/** Given by the public page to the booking flow it paints: without it, the flow is the team's preview. */
export const PUBLIC_DOOR: InjectionKey<PublicDoor> = Symbol('online_booking.public-door');

export interface DoorDeps extends HeaderDeps {
  fetchImpl: (url: string, init: RequestInit) => Promise<Response>;
  doc: Document;
}

/** What base embeds as `public-door`. */
interface DoorBlock {
  currency: string;
  currency_decimals: number;
}

export function doorRoutes(slug: string): OperationRoutes {
  return Object.fromEntries(PUBLIC_OPERATIONS.map((op) => [op, { method: 'post', path: `/p/${slug}/api/${op}` }]));
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

export function openDoor(config: SpaConfig, slug: string, deps: DoorDeps = browser()): PublicDoor {
  const api = createApiClient({
    fetchImpl: deps.fetchImpl,
    headers: createHeaderProvider(config, deps),
    apiBase: '',
    routes: doorRoutes(slug),
  });
  const block = readJsonBlock<DoorBlock>('public-door', deps.doc);
  return {
    api,
    money: computed(() => (block ? { currency: block.currency, decimals: block.currency_decimals } : undefined)),
  };
}

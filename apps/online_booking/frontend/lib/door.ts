// The booking page's way in through base's public door (`base/frontend/lib/public-door.ts`): its operations posted to
// `/p/<slug>/api/<operation>`, and the business's money from the page's own HTML.
import type { SpaConfig } from '@erplora/ui/sdk';
import type { InjectionKey } from 'vue';

import { type DoorDeps, openPublicDoor, type PublicDoorClient } from '../../../../base/frontend/lib/public-door';

/** The operations of the page (they ask `online_booking.public`, the one permission the door holds). */
export const PUBLIC_OPERATIONS = [
  'online_booking.public.page',
  'online_booking.public.services',
  'online_booking.public.slots',
  'online_booking.public.book',
  'online_booking.public.booking',
  'online_booking.public.cancel',
] as const;

/** What the page calls the business with, the money it writes its prices in (unknown without it), and its slug. */
export interface PublicDoor extends PublicDoorClient {
  slug: string;
}

/** Given by the public page to the booking flow it paints: without it, the flow is the team's preview. */
export const PUBLIC_DOOR: InjectionKey<PublicDoor> = Symbol('online_booking.public-door');

export function openDoor(config: SpaConfig, slug: string, deps?: DoorDeps): PublicDoor {
  return { ...openPublicDoor(config, { slug, operations: PUBLIC_OPERATIONS }, deps), slug };
}

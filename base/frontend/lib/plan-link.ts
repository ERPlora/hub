// Buying for this business on erplora.com (BASE-F11): «Upgrade plan», to this hub's plan page that `base/spa.py` embeds
// in `hub-home`, and the links to erplora.com's Store. Only the owner buys there, so only the owner is offered either,
// and only on the web (`useSurface`): the Hub never sells inside the installed app. Where the address does not come, it
// is not offered: never a button that does nothing. Its click goes with the pass (`useSaasPass`), so the person arrives
// already signed in.
import { useSession, useSurface } from '@erplora/ui/shell';
import { computed, type ComputedRef } from 'vue';

import { type HubHome, readJsonBlock } from './home';

/** Owning the business, the owner's alone (`base.permissions.OWN_BUSINESS`). */
export const OWN_BUSINESS = 'base.own_business';

/** Whether this person is offered to buy for the business: its owner, on the web. */
export function useMayBuy(): ComputedRef<boolean> {
  const { isWeb } = useSurface();
  const session = useSession();
  return computed(() => isWeb.value && session.can(OWN_BUSINESS));
}

export function usePlanLink(): { planUrl: string; offered: ComputedRef<boolean> } {
  const mayBuy = useMayBuy();
  const planUrl = readJsonBlock<HubHome>('hub-home')?.plan_url ?? '';
  return { planUrl, offered: computed(() => mayBuy.value && planUrl !== '') };
}

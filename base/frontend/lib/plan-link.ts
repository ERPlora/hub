// «Upgrade plan» (BASE-F11): this hub's plan page on erplora.com, which `base/spa.py` embeds in `hub-home`. It sells, so it
// is offered only on the web (`useSurface`); where the address does not come, it is not offered: never a button that does
// nothing. Its click goes the Hub's one way out, `openExternalLink` (gh:hub#439).
import { useSurface } from '@erplora/ui/shell';
import { computed, type ComputedRef } from 'vue';

import { type HubHome, readJsonBlock } from './home';

export function usePlanLink(): { planUrl: string; offered: ComputedRef<boolean> } {
  const { isWeb } = useSurface();
  const planUrl = readJsonBlock<HubHome>('hub-home')?.plan_url ?? '';
  return { planUrl, offered: computed(() => isWeb.value && planUrl !== '') };
}

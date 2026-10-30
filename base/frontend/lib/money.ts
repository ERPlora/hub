// The business's currency for the Home's amounts (BASE-G98): its country's, with its decimals, as `base.business.get`
// says it — the registry of this hub, never a call to erplora.com. Followed live (a change on erplora.com is pushed
// and arrives), one subscription for the whole tab however many pieces ask (the SDK shares it), and unknown until the
// business answers: an amount is then written without a symbol, never in the euro by default.
import { useLive } from '@erplora/ui/sdk';
import { computed, type ComputedRef } from 'vue';

import type { Money } from './home';

export function useBusinessMoney(): ComputedRef<Money | undefined> {
  const { data } = useLive('base.business.get', {});
  return computed(() => (data.value ? { currency: data.value.currency, decimals: data.value.currency_decimals } : undefined));
}

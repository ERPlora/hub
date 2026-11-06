// The business's currency for the Home's amounts (BASE-G98): its country's, with its decimals, as `base.business.get`
// says it — the registry of this hub, never a call to erplora.com. Followed live (a change on erplora.com is pushed
// and arrives), one subscription for the whole tab however many pieces ask (the SDK shares it), and unknown until the
// business answers: an amount is then written without a symbol, never in the euro by default.
import { formatMoney as writeMoney } from '@erplora/ui/components';
import { type ApiError, useLive } from '@erplora/ui/sdk';
import { computed, type ComputedRef, type Ref } from 'vue';

import type { Money } from './home';

/** Minor units in `money`, in `locale`, its thousands grouped («1.234,50 €», «€22.50», «¥1,500»; «22,50» while it is
 *  unknown): the platform's way of writing an amount, for the screens whose amount is always a number. */
export const formatMoney: (cents: number, locale: string, money?: Money) => string = writeMoney;

export function useBusinessMoney(): ComputedRef<Money | undefined> {
  return useBusinessMoneyRead().money;
}

/** The read of the business's money as a window that waits for it needs it (hub#938): the money (unknown until the
 *  business answers), the read's `error` (an error frame of `base.business.get`, such as `base.hub_busy`; the money is
 *  kept if it was known) and `retry`, which reopens the tab's stream so the server answers again. `BusinessMoneyError`
 *  says it in the window; the money alone is `useBusinessMoney`. */
export interface BusinessMoneyRead {
  money: ComputedRef<Money | undefined>;
  error: Readonly<Ref<ApiError | null>>;
  retry: () => void;
}

export function useBusinessMoneyRead(): BusinessMoneyRead {
  const { data, error, refresh } = useLive('base.business.get', {});
  const money = computed(() => (data.value ? { currency: data.value.currency, decimals: data.value.currency_decimals } : undefined));
  return { money, error, retry: refresh };
}

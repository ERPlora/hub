// `useBusinessDay()`: the day the Sales periods count from (SALE-F28). It is the hub's business day
// (`sale.business_day.get`: asked, not live), read when the page asks (`read()`: on opening and on
// every press of a period). Until the hub answers, and if it does not, the device's day; a failed read
// is kept in `error` so the page can say it.
import { type ApiError, useLiveClient } from '@erplora/ui/sdk';
import { type Ref, shallowRef } from 'vue';

import { deviceDay } from './period';

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

export interface BusinessDay {
  /** The ISO day «Today» is. */
  today: Readonly<Ref<string>>;
  /** Why the last read failed; null after a good one. */
  error: Readonly<Ref<ApiError | null>>;
  /** Asks the hub again. Never throws. */
  read(): Promise<void>;
}

export function useBusinessDay(): BusinessDay {
  const client = useLiveClient();
  const today = shallowRef(deviceDay());
  const error = shallowRef<ApiError | null>(null);

  async function read(): Promise<void> {
    try {
      const answer = await client.api.call('sale.business_day.get', {});
      if (typeof answer?.today === 'string' && ISO_DAY.test(answer.today)) today.value = answer.today;
      error.value = null;
    } catch (failure) {
      error.value = failure as ApiError;
    }
  }

  return { today, error, read };
}

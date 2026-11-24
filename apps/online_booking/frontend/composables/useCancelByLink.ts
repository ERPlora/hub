import { ApiError, type ApiClient } from '@erplora/ui/sdk';
import { ref, toValue, type MaybeRefOrGetter } from 'vue';

import type { PublicBookingOut } from '../operations';

/** The customer cancels her booking with its personal link, the same call on the booking page and on her link's page. */
export function useCancelByLink(
  api: Pick<ApiClient, 'call'>,
  token: MaybeRefOrGetter<string>,
  cancelled: (booking: PublicBookingOut) => void,
) {
  const pending = ref(false);
  const error = ref<ApiError | null>(null);

  async function cancel(reason: string): Promise<void> {
    pending.value = true;
    error.value = null;
    try {
      cancelled(await api.call('online_booking.public.cancel', { token: toValue(token), reason }));
    } catch (failure) {
      error.value = failure instanceof ApiError ? failure : new ApiError(0, 'client_error', String(failure));
    } finally {
      pending.value = false;
    }
  }

  return { pending, error, cancel };
}

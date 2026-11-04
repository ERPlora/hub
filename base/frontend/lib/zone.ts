// The business's clock on a screen (hub#687): its time zone, as `base.business.get` says it — the hub's, the one every
// hour of the server is told in. Followed live, one subscription for the whole tab however many pieces ask (the SDK
// shares it), and unknown until the business answers: `Intl` then uses the device's, never a zone written by hand.
import { useLive } from '@erplora/ui/sdk';
import { computed, type ComputedRef } from 'vue';

export function useBusinessZone(): ComputedRef<string | undefined> {
  const { data } = useLive('base.business.get', {});
  return computed(() => data.value?.timezone);
}

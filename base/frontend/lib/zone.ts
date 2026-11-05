// The business's clock on a screen (hub#687): its time zone, as `base.business.get` says it — the hub's, the one every
// hour of the server is told in. Followed live, one subscription for the whole tab however many pieces ask (the SDK
// shares it), and unknown until the business answers: `Intl` then uses the device's, never a zone written by hand.
import { useLive } from '@erplora/ui/sdk';
import { computed, type ComputedRef } from 'vue';

export function useBusinessZone(): ComputedRef<string | undefined> {
  return useBusinessClock().zone;
}

/** The same zone, and whether it could not be read: the screen that cannot go on without it has to say so. */
export function useBusinessClock(): { zone: ComputedRef<string | undefined>; unread: ComputedRef<boolean> } {
  const { data, status } = useLive('base.business.get', {});
  return {
    zone: computed(() => data.value?.timezone),
    unread: computed(() => !data.value && (status.value === 'error' || status.value === 'reconnecting')),
  };
}

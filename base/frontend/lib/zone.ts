// The business's clock on a screen (hub#687): its time zone, as `base.business.get` says it — the hub's, the one every
// hour of the server is told in. Followed live, one subscription for the whole tab however many pieces ask (the SDK
// shares it), and unknown until the business answers: `Intl` then uses the device's, never a zone written by hand.
import { useLive } from '@erplora/ui/sdk';
import { computed, type ComputedRef } from 'vue';

export function useBusinessZone(): ComputedRef<string | undefined> {
  return useBusinessClock().zone;
}

/** The day it is now in `zone` (`2026-11-24`): the device's while the zone is not known, or when the browser knows none
 *  by that name. */
export function todayIn(zone: string | undefined, now: Date = new Date()): string {
  const parts = { year: 'numeric', month: '2-digit', day: '2-digit' } as const;
  try {
    return new Intl.DateTimeFormat('en-CA', { ...parts, timeZone: zone }).format(now);
  } catch {
    return new Intl.DateTimeFormat('en-CA', parts).format(now);
  }
}

/** The same zone, and whether it could not be read: the screen that cannot go on without it has to say so. */
export function useBusinessClock(): { zone: ComputedRef<string | undefined>; unread: ComputedRef<boolean> } {
  const { data, status } = useLive('base.business.get', {});
  return {
    zone: computed(() => data.value?.timezone),
    unread: computed(() => !data.value && (status.value === 'error' || status.value === 'reconnecting')),
  };
}

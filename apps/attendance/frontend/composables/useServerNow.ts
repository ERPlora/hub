// `useServerNow(asOf, ms)`: the page's clock on the SERVER's time. The figures come «as of» the server's
// instant (`as_of`); a device whose clock is off would make the timer and today's totals jump or run
// backwards. The gap between the two clocks is measured when each result arrives and the ticking clock
// (`useNow`) runs with it; until a result arrives, it is the device's own time.
import { computed, type ComputedRef, shallowRef, watch } from 'vue';

import { useNow } from './useNow';

export function useServerNow(asOf: () => string | undefined, intervalMs = 1000): ComputedRef<number> {
  const now = useNow(intervalMs);
  const skew = shallowRef(0);
  watch(
    asOf,
    (instant) => {
      const server = instant ? Date.parse(instant) : Number.NaN;
      if (Number.isFinite(server)) skew.value = server - Date.now();
    },
    { immediate: true },
  );
  return computed(() => now.value + skew.value);
}

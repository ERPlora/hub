// `useNow(ms)`: the time as a ref that moves on by itself every `ms` (30 s by default: the old screen's
// refresh), for what the printing screens read from the clock — how long a job has waited, a printer
// «Waiting», a device that did not answer within its lease. The interval stops with its component.
import { onScopeDispose, type ShallowRef, shallowRef } from 'vue';

export const NOW_TICK_MS = 30_000;

export function useNow(ms: number = NOW_TICK_MS): ShallowRef<Date> {
  const now = shallowRef(new Date());
  const tick = setInterval(() => (now.value = new Date()), ms);
  onScopeDispose(() => clearInterval(tick));
  return now;
}

// `useNow()`: the clock a screen paints a check's minutes with («3 pax · 35 min»). It moves on by itself
// every 30 seconds while the screen lives (the old plan's refresh), and stops with it.
import { onScopeDispose, type Ref, shallowRef } from 'vue';

export const NOW_TICK_MS = 30_000;

export function useNow(): Readonly<Ref<Date>> {
  const now = shallowRef(new Date());
  const timer = setInterval(() => {
    now.value = new Date();
  }, NOW_TICK_MS);
  onScopeDispose(() => clearInterval(timer));
  return now;
}

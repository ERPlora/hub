// `useNow(tickMs)`: the clock a screen paints with. The kitchen display's card clock moves every second
// (m:ss, as the old KDS); a list can tick slower. It stops with the screen.
import { onScopeDispose, type Ref, shallowRef } from 'vue';

export const NOW_TICK_MS = 1000;

export function useNow(tickMs: number = NOW_TICK_MS): Readonly<Ref<Date>> {
  const now = shallowRef(new Date());
  const timer = setInterval(() => {
    now.value = new Date();
  }, tickMs);
  onScopeDispose(() => clearInterval(timer));
  return now;
}

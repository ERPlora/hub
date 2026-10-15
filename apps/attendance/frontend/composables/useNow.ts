// `useNow(ms)`: the page's clock, ticking every `ms`. «It is 09:00», the running timer and today's totals
// run on from the server's figures with it, without asking the server every second; it stops when the
// component goes.
import { onScopeDispose, type Ref, shallowRef } from 'vue';

export function useNow(intervalMs = 1000): Readonly<Ref<number>> {
  const now = shallowRef(Date.now());
  const timer = setInterval(() => {
    now.value = Date.now();
  }, intervalMs);
  onScopeDispose(() => clearInterval(timer));
  return now;
}

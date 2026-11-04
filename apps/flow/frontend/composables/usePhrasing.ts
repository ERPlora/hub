// `usePhrasing()`: the translator the phrasing of `lib/phrasing.ts` needs (`t`, `te`, the language and the business's
// clock), as a computed value that follows a change of language. The clock comes from the page (`provideBusinessClock`):
// a panel opened later says its moments on it with no live read of its own, which would reopen the page's stream.
import { computed, type ComputedRef, inject, type InjectionKey, provide } from 'vue';

import { useBusinessZone } from '../../../../base/frontend/lib/zone';
import type { Phrasing } from '../lib/phrasing';
import { useLocale, useT, useTe } from './useT';

const BUSINESS_CLOCK: InjectionKey<ComputedRef<string | undefined>> = Symbol('flow.businessClock');

/** Follows the business's zone for everything this page shows. */
export function provideBusinessClock(): void {
  provide(BUSINESS_CLOCK, useBusinessZone());
}

export function usePhrasing(): ComputedRef<Phrasing> {
  const t = useT();
  const te = useTe();
  const locale = useLocale();
  const timeZone = inject(BUSINESS_CLOCK, undefined);
  return computed(() => ({ t, te, locale: locale.value, timeZone: timeZone?.value }));
}

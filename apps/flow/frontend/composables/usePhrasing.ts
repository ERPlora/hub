// `usePhrasing()`: the translator the phrasing of `lib/phrasing.ts` needs (`t`, `te` and the language),
// as a computed value that follows a change of language.
import { computed, type ComputedRef } from 'vue';

import type { Phrasing } from '../lib/phrasing';
import { useLocale, useT, useTe } from './useT';

export function usePhrasing(): ComputedRef<Phrasing> {
  const t = useT();
  const te = useTe();
  const locale = useLocale();
  return computed(() => ({ t, te, locale: locale.value }));
}

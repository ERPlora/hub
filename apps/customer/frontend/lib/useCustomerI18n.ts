// The shell's i18n from a script: `t` and the reactive `locale` of the instance `createShell`
// installed (vue-i18n's global injection: `$t`, `$i18n`). The Hub does not depend on vue-i18n
// itself; when `@erplora/ui/shell` exports `useI18n` (UI-REQUESTS.md) this becomes that import.
import { computed, type ComputedRef, getCurrentInstance } from 'vue';

type Translate = (key: string, values?: Record<string, unknown>) => string;

interface InjectedI18n {
  $t: Translate;
  $i18n: { locale: string };
}

export function useCustomerI18n(): { t: Translate; locale: ComputedRef<string> } {
  const instance = getCurrentInstance();
  if (!instance) throw new Error('useCustomerI18n() must be called from setup()');
  const injected = instance.appContext.config.globalProperties as unknown as InjectedI18n;
  return {
    t: (key, values) => (values ? injected.$t(key, values) : injected.$t(key)),
    locale: computed(() => injected.$i18n.locale),
  };
}

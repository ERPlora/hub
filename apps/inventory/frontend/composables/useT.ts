// Translations in a script: hub-next does not depend on vue-i18n (only @erplora/ui does), so a
// component reads the shell's i18n through its own `$t` and `$i18n`, the public API the i18n plugin
// installs on every component. Until @erplora/ui re-exports `useI18n` (UI-REQUESTS.md).
import { computed, type ComputedRef, getCurrentInstance } from 'vue';

type Translate = (key: string, ...args: unknown[]) => string;

export function useT(): { t: Translate; locale: ComputedRef<string> } {
  const proxy = getCurrentInstance()?.proxy;
  if (!proxy) throw new Error('useT() must be called from setup(): it reads the i18n of its component.');
  const translate = proxy.$t as unknown as Translate;
  return {
    t: (key, ...args) => translate.call(proxy, key, ...args),
    locale: computed(() => String(proxy.$i18n.locale)),
  };
}

// `useT()`: the shell's translator (`$t`, installed by `createShellI18n`) from a component's script,
// for the texts a page builds in code (a confirmation, a picker's labels). Templates use `$t` and
// scripts this, both the same global translator, so a text built in a `computed` follows a change of
// language. The app has no `vue-i18n` dependency of its own.
import { computed, type ComputedRef, getCurrentInstance } from 'vue';

/** Translates `key` (with `named` values) in the app's language. */
export type Translate = (key: string, named?: Record<string, unknown>) => string;

export function useT(): Translate {
  const instance = getCurrentInstance();
  if (!instance) throw new Error('useT() must be called from setup(): the translator belongs to the app.');
  const $t = instance.appContext.config.globalProperties.$t as Translate;
  return (key, named) => (named ? $t(key, named) : $t(key));
}

/** The app's language (`en`, `es`), live: what dates and money built in script are painted for. */
export function useLocale(): ComputedRef<string> {
  const instance = getCurrentInstance();
  if (!instance) throw new Error('useLocale() must be called from setup(): the language belongs to the app.');
  const i18n = instance.appContext.config.globalProperties.$i18n as { locale: string };
  return computed(() => i18n.locale);
}

/** Whether `key` has a text in the app's language (`$te`): the phrasing reads it before composing one. */
export function useTe(): (key: string) => boolean {
  const instance = getCurrentInstance();
  if (!instance) throw new Error('useTe() must be called from setup(): the translator belongs to the app.');
  const $te = instance.appContext.config.globalProperties.$te as (key: string) => boolean;
  return (key) => $te(key);
}

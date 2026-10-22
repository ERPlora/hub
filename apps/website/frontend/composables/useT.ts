// `useT()`: the shell's translator (`$t`, installed by `createShellI18n`) from a component's script, for the texts
// the editor builds in code (a confirmation, a toast, a label). The app has no `vue-i18n` dependency of its own:
// templates use `$t` and scripts this, both the same global translator, so a text built in a `computed` follows a
// change of language (as apps/online_booking does).
import { getCurrentInstance } from 'vue';

/** Translates `key` (with `named` values) in the app's language. */
export type Translate = (key: string, named?: Record<string, unknown>) => string;

export function useT(): Translate {
  const instance = getCurrentInstance();
  if (!instance) throw new Error('useT() must be called from setup(): the translator belongs to the app.');
  const $t = instance.appContext.config.globalProperties.$t as Translate;
  return (key, named) => (named ? $t(key, named) : $t(key));
}

import { ref, watch, type Ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

/**
 * A page's tab, deep-linked by HASH (`/settings#permissions`): the base route does not change, so
 * Ionic does not treat a tab switch as a secondary page (no unmounted tab bar, no back button).
 *
 * Ionic keeps every visited page mounted and `useRoute()` is the app's ONE route, so the sync only
 * runs while the address is on `path` (hub#2444, the hub#2332 guard of System for every page).
 * Without it the page left behind read the next page's hash as an unknown tab of its own and wrote
 * its default back onto it: a link from Settings to System → Updates landed on System → Resources.
 * The path is watched too, so coming back to a plain address opens the tab it names instead of the
 * last one (hub#2447).
 *
 * `resolve('')` is the default tab. `canonicalize` rewrites a retired or unknown hash to the tab it
 * opened (Settings: `#store` → `#hub`); without it the address is left as it came.
 */
export function useHashTab<T extends string>(
  path: string,
  resolve: (hash: string) => T,
  options: { canonicalize?: boolean } = {},
): Ref<T> {
  const route = useRoute();
  const router = useRouter();
  const onOwnAddress = () => route.path === path;
  const canonicalize = (hash: string, tab: T) => {
    if (options.canonicalize && hash && hash !== `#${tab}`) void router.replace({ hash: `#${tab}` });
  };

  const tab = ref(resolve(route.hash)) as Ref<T>;
  if (onOwnAddress()) canonicalize(route.hash, tab.value);

  // Choosing a tab writes it to the address (replace: «back» leaves the page, not the tab).
  watch(tab, (value) => {
    if (!onOwnAddress()) return;
    if (value !== (route.hash.slice(1) || resolve(''))) void router.replace({ hash: `#${value}` });
  });
  // Back/forward and deep links: the address picks the tab.
  watch([() => route.path, () => route.hash], ([, hash]) => {
    if (!onOwnAddress()) return;
    const next = resolve(hash);
    if (next !== tab.value) tab.value = next;
    canonicalize(hash, next);
  });
  return tab;
}

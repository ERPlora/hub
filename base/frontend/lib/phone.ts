// The screen's shape, live. `usePhone`: whether it is a phone; the Home folds «My apps» and «Finish setting up your
// business» there, at the topbar's breakpoint (AppTopbar's `PHONE_QUERY`), so both switch at once.
import { onBeforeUnmount, ref, type Ref } from 'vue';

export const PHONE_QUERY = '(max-width: 767px)';

/** Whether `query` matches, following it while the component is mounted; false without `matchMedia`. */
function useMedia(query: string): Ref<boolean> {
  const matches = ref(false);
  const media = typeof window.matchMedia === 'function' ? window.matchMedia(query) : undefined;
  if (!media) return matches;
  matches.value = media.matches;
  const onChange = (event: { matches: boolean }) => (matches.value = event.matches);
  media.addEventListener('change', onChange);
  onBeforeUnmount(() => media.removeEventListener('change', onChange));
  return matches;
}

export function usePhone(): Ref<boolean> {
  return useMedia(PHONE_QUERY);
}

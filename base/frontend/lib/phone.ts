// Whether the screen is a phone, live: the Home folds «My apps» and «Finish setting up your business» there.
// The topbar's breakpoint (AppTopbar's `PHONE_QUERY`), so both switch at once.
import { onBeforeUnmount, ref, type Ref } from 'vue';

export const PHONE_QUERY = '(max-width: 767px)';

export function usePhone(): Ref<boolean> {
  const phone = ref(false);
  const media = typeof window.matchMedia === 'function' ? window.matchMedia(PHONE_QUERY) : undefined;
  if (!media) return phone;
  phone.value = media.matches;
  const onChange = (event: { matches: boolean }) => (phone.value = event.matches);
  media.addEventListener('change', onChange);
  onBeforeUnmount(() => media.removeEventListener('change', onChange));
  return phone;
}

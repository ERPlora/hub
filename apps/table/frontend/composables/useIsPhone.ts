import { onBeforeUnmount, type Ref, ref } from 'vue';

/** The same phone breakpoint as `@erplora/ui`'s lists; without `matchMedia` the screen is a desk. */
const PHONE = '(max-width: 640px)';

export function useIsPhone(): Readonly<Ref<boolean>> {
  const phone = ref(false);
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return phone;
  const media = window.matchMedia(PHONE);
  const onChange = (event: { matches: boolean }) => {
    phone.value = event.matches;
  };
  phone.value = media.matches;
  media.addEventListener('change', onChange);
  onBeforeUnmount(() => media.removeEventListener('change', onChange));
  return phone;
}

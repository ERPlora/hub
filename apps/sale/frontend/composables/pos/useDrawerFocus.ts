// `useDrawerFocus()`: the phone's cart drawer behaves as the dialog it is. Opening it moves the focus to
// the first thing inside; Tab and Shift+Tab go round inside it (bind `onKeydown` on the drawer); closing
// it gives the focus back to what opened it (the cart button). Where the cart is a column of the till
// (`enabled` false: a tablet, a desktop) it does nothing.
import { nextTick, type Ref, watch } from 'vue';

export interface DrawerFocusOptions {
  container: Readonly<Ref<HTMLElement | null>>;
  open: Readonly<Ref<boolean>>;
  /** The cart is a drawer now (the phone's layout). */
  enabled: Readonly<Ref<boolean>>;
  /** Where the focus goes back on closing. */
  returnTo: () => HTMLElement | null | undefined;
}

const FOCUSABLE = [
  'button:not([disabled])',
  'a[href]',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  'ion-button:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ');

export function useDrawerFocus(options: DrawerFocusOptions) {
  const focusables = (): HTMLElement[] =>
    [...(options.container.value?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [])].filter(
      (el) => !(el as HTMLElement & { disabled?: boolean }).disabled,
    );

  watch(options.open, async (isOpen, wasOpen) => {
    if (!options.enabled.value) return;
    if (isOpen) {
      await nextTick();
      (focusables()[0] ?? options.container.value)?.focus();
    } else if (wasOpen) {
      options.returnTo()?.focus();
    }
  });

  /** Tab and Shift+Tab go round inside the open drawer. */
  function onKeydown(event: KeyboardEvent): void {
    if (event.key !== 'Tab' || !options.enabled.value || !options.open.value) return;
    const items = focusables();
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    const current = document.activeElement;
    if (event.shiftKey && (current === first || current === options.container.value)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && current === last) {
      event.preventDefault();
      first.focus();
    }
  }

  return { onKeydown };
}

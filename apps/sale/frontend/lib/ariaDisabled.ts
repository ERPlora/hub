import { onMounted, onUpdated } from 'vue';

/** Ionic copies a button host's `aria-*` to its native button only when it loads: every Ionic button under `root` (and
 *  `root` itself, when it is one) that says its state in `data-aria-disabled` gets it on its native button now. */
export function syncAriaDisabled(root: HTMLElement | null | undefined): void {
  if (!root) return;
  const hosts = [...(root.matches('[data-aria-disabled]') ? [root] : []), ...root.querySelectorAll<HTMLElement>('[data-aria-disabled]')];
  hosts.forEach((host) => {
    const button = host.shadowRoot?.querySelector('button');
    if (!button) return;
    if (host.dataset.ariaDisabled === 'true') button.setAttribute('aria-disabled', 'true');
    else button.removeAttribute('aria-disabled');
  });
}

/** For a component whose Ionic buttons change between available and not while it is on screen: brings their native
 *  buttons in step (`syncAriaDisabled` on `target()`) once it mounts and after each of its updates. */
export function useNativeAriaDisabled(target: () => HTMLElement | null | undefined): void {
  const sync = () => syncAriaDisabled(target());
  onMounted(sync);
  onUpdated(sync);
}

export function syncAriaDisabled(root: HTMLElement | null | undefined): void {
  root?.querySelectorAll<HTMLElement>('[data-aria-disabled]').forEach((host) => {
    const button = host.shadowRoot?.querySelector('button');
    if (!button) return;
    if (host.dataset.ariaDisabled === 'true') button.setAttribute('aria-disabled', 'true');
    else button.removeAttribute('aria-disabled');
  });
}

// The browser's Fullscreen API, wrapped once for the till: the ⋮ screen menu offers «Full screen» /
// «Exit full screen» only where the device allows it, on the till's own element (the product's shell
// did it for the view; here the page asks the browser). Esc and F11 leave it too: `onChange` follows.

type FullscreenTarget = Element & { requestFullscreen?: () => Promise<void> };

/** Whether the device lets `el` go full screen (an iPhone's Safari, for one, does not). */
export function isCapable(el: Element | null | undefined): boolean {
  if (!el || typeof document === 'undefined' || !document.fullscreenEnabled) return false;
  return typeof (el as FullscreenTarget).requestFullscreen === 'function';
}

/** Whether `el` itself is the element on full screen now. */
export function isActive(el: Element | null | undefined): boolean {
  return !!el && typeof document !== 'undefined' && document.fullscreenElement === el;
}

/** Puts `el` on full screen, or leaves it when `el` already is. A refusal of the browser is not an error. */
export async function toggle(el: Element): Promise<void> {
  try {
    if (isActive(el)) await document.exitFullscreen();
    else await (el as FullscreenTarget).requestFullscreen?.();
  } catch {
    // No user gesture or a policy said no: the screen simply stays as it was, and `onChange` says nothing.
  }
}

/** Calls `listener` on every change of state (the toggle, Esc, F11); returns the unsubscribe. */
export function onChange(listener: () => void): () => void {
  document.addEventListener('fullscreenchange', listener);
  return () => document.removeEventListener('fullscreenchange', listener);
}

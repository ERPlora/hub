// The browser's Fullscreen API, wrapped once for the till: the ⋮ screen menu offers «Full screen» /
// «Exit full screen» only where the device allows it. It is the WHOLE document that goes full screen,
// as the old shell did: the till's sheets, the checkout and the toasts live in the app's root
// (`ion-app`), and an element of the page on full screen would hide them. Esc and F11 leave it too:
// `onChange` follows.

type FullscreenRoot = HTMLElement & { requestFullscreen?: () => Promise<void> };

const root = (): FullscreenRoot | null => (typeof document === 'undefined' ? null : document.documentElement);

/** Whether the device lets the page go full screen (an iPhone's Safari, for one, does not). */
export function isCapable(): boolean {
  const page = root();
  return !!page && !!document.fullscreenEnabled && typeof page.requestFullscreen === 'function';
}

/** Whether the page is on full screen now. */
export function isActive(): boolean {
  return typeof document !== 'undefined' && !!document.fullscreenElement;
}

/** Puts the page on full screen, or leaves it. A refusal of the browser is not an error. */
export async function toggle(): Promise<void> {
  try {
    if (isActive()) await document.exitFullscreen();
    else await root()?.requestFullscreen?.();
  } catch {
    // No user gesture or a policy said no: the screen simply stays as it was, and `onChange` says nothing.
  }
}

/** Calls `listener` on every change of state (the toggle, Esc, F11); returns the unsubscribe. */
export function onChange(listener: () => void): () => void {
  document.addEventListener('fullscreenchange', listener);
  return () => document.removeEventListener('fullscreenchange', listener);
}

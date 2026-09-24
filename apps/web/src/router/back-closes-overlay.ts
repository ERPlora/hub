import { invokeTauri } from '../lib/device';

/**
 * hub#1906 — the system Back button closes what is open on top BEFORE it leaves the screen.
 *
 * On the installed Android app, Tauri's activity turns the system Back into `webView.goBack()` —
 * but only while nobody listens to its `back-button` event (`AppPlugin.kt`). With nobody
 * listening, the router slid the screen away and took the payment sheet, the modal or the side
 * menu with it. Android's rule — and what every POS on it does (Square, Loyverse) — is the
 * opposite: Back dismisses the topmost layer first, and only an empty screen goes back.
 *
 * So the shell TAKES the button (`installSystemBackButton`) and never cancels a navigation: a
 * guard that aborts the popstate leaves @ionic/vue-router with a stale "this was a Back" and the
 * next push animates to the wrong view (rv-2042). The browser's own Back arrow stays a plain
 * navigation, as in most Ionic apps.
 *
 * The layers, topmost first (`closeTopmostLayer`):
 *   1. a presented Ionic overlay in the document (modal, alert, popover, action sheet, loading) —
 *      dismissed with role `backdrop` like Ionic's own hardware back; one that cannot be dismissed
 *      (`backdropDismiss: false`) HOLDS the press;
 *   2. an open `ion-menu`;
 *   3. the mounted module, through the `erplora:back` contract below.
 *
 * MODULE CONTRACT — `erplora:back`. Modules draw their own sheets inside their shadow DOM (the
 * till's payment sheet is a `<div>` of its own), which the shell cannot see nor close. On every Back
 * the shell dispatches a cancelable `erplora:back` on `window`. A module with something open closes
 * its TOPMOST layer synchronously and calls `event.preventDefault()`: the shell then keeps the
 * screen. A module with nothing open ignores it.
 */
export const SHELL_BACK_EVENT = 'erplora:back';

/** `closed`: a layer was dismissed · `held`: one refuses to close · `none`: nothing was open. */
export type BackOutcome = 'closed' | 'held' | 'none';

/** Ionic's own overlay list (`getOverlays` in @ionic/core) minus the toast, which never blocks. */
const IONIC_OVERLAYS = 'ion-alert,ion-action-sheet,ion-loading,ion-modal,ion-picker-legacy,ion-popover';

/** Our Android plugin's way out, used when there is nothing to close and no history left. */
const LEAVE_APP = 'plugin:erplora-android|leave_app';

type IonicOverlay = HTMLElement & {
  overlayIndex?: number;
  backdropDismiss?: boolean;
  dismiss: (data?: unknown, role?: string) => Promise<boolean>;
};
type IonicMenu = HTMLElement & { isOpen?: () => Promise<boolean>; close?: () => Promise<boolean> };

function topmostPresentedOverlay(doc: Document): IonicOverlay | undefined {
  // Same test as Ionic's `getPresentedOverlay`: registered (`overlayIndex > 0`) and not an inline
  // overlay parked hidden. Document order is presentation order, so the last one is on top.
  const presented = Array.from(doc.querySelectorAll<IonicOverlay>(IONIC_OVERLAYS)).filter(
    (o) => (o.overlayIndex ?? 0) > 0 && !o.classList.contains('overlay-hidden'),
  );
  return presented[presented.length - 1];
}

async function openMenu(doc: Document): Promise<IonicMenu | undefined> {
  for (const menu of Array.from(doc.querySelectorAll<IonicMenu>('ion-menu'))) {
    if (typeof menu.isOpen === 'function' && (await menu.isOpen())) return menu;
  }
  return undefined;
}

export async function closeTopmostLayer(doc: Document = document, win: Window = window): Promise<BackOutcome> {
  const overlay = topmostPresentedOverlay(doc);
  if (overlay) {
    if (!overlay.backdropDismiss) return 'held';
    // Not awaited on purpose (as Ionic does): a `canDismiss` that asks for confirmation must not
    // block the Back of the alert it opens.
    void overlay.dismiss(undefined, 'backdrop');
    return 'closed';
  }
  const menu = await openMenu(doc);
  if (menu?.close) {
    void menu.close();
    return 'closed';
  }
  const ask = new CustomEvent(SHELL_BACK_EVENT, { cancelable: true });
  win.dispatchEvent(ask);
  return ask.defaultPrevented ? 'closed' : 'none';
}

type PluginListener = { unregister: () => Promise<void> };
type TauriApp = { onBackButtonPress?: (handler: (payload: { canGoBack: boolean }) => void) => Promise<PluginListener> };

/**
 * Takes the Android Back button (Tauri's `onBackButtonPress`, exposed by `withGlobalTauri`). With a
 * listener registered Tauri no longer moves the WebView itself, so the shell does what the system
 * would have done once nothing is left to close: `history.back()` (a real popstate, which the
 * router and Ionic see as the pop it is) or, with no history left, leave the app.
 *
 * Resolves `false` where there is no such button — a browser, or the desktop app, where the
 * listener is refused. The listener is dropped on `pagehide`: Tauri keeps listeners across page
 * loads, and a dead one would swallow the button on whatever page the app loads next.
 */
export async function installSystemBackButton(
  opts: { win?: Window; closeTop?: () => Promise<BackOutcome>; leaveApp?: () => Promise<unknown> } = {},
): Promise<boolean> {
  const win = opts.win ?? window;
  const closeTop = opts.closeTop ?? (() => closeTopmostLayer());
  const leaveApp = opts.leaveApp ?? (() => invokeTauri(LEAVE_APP));
  const app = (win as unknown as { __TAURI__?: { app?: TauriApp } }).__TAURI__?.app;
  if (typeof app?.onBackButtonPress !== 'function') return false;
  let listener: PluginListener;
  try {
    listener = await app.onBackButtonPress(async ({ canGoBack }) => {
      if ((await closeTop()) !== 'none') return;
      if (canGoBack) win.history.back();
      // An app build older than `leave_app` refuses it: give the button back to Tauri, whose own
      // Back leaves from the root, instead of a button that no longer does anything.
      else await leaveApp().catch(() => listener.unregister());
    });
  } catch {
    return false;
  }
  win.addEventListener('pagehide', () => void listener.unregister().catch(() => undefined), { once: true });
  return true;
}

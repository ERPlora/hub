import type { Router } from 'vue-router';

/**
 * hub#1906 — the system Back button closes what is open on top BEFORE it leaves the screen.
 *
 * On the installed Android app, Back is a plain `history.back()` of the WebView (Tauri's activity
 * does `goBack()` while it can). Nobody in the shell listened, so the router slid the screen away
 * and took the payment sheet, the modal or the side menu with it. Android's rule — and what every
 * POS on it does (Square, Loyverse) — is the opposite: Back dismisses the topmost layer first, and
 * only an empty screen navigates. The browser's Back gets the same treatment, as it does in most
 * web apps with sheets.
 *
 * The layers, topmost first:
 *   1. a presented Ionic overlay in the document (modal, alert, popover, action sheet, loading) —
 *      dismissed with role `backdrop` like Ionic's own hardware back; one that cannot be dismissed
 *      (`backdropDismiss: false`) HOLDS the back instead of letting the page slide away under it;
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

/**
 * Wires the rule into `router`. MUST run right after `createRouter()` and before the first
 * navigation: the history listener registered here has to fire BEFORE the router's own popstate
 * listener (registered on its first navigation), so the guard knows the navigation is a Back.
 */
export function installBackClosesOverlay(router: Router, closeTop: () => Promise<BackOutcome> = () => closeTopmostLayer()): void {
  let backPending = false;
  router.options.history.listen((_to, _from, info) => {
    backPending = info.direction === 'back';
  });
  router.beforeEach(async () => {
    const isBack = backPending;
    backPending = false;
    if (!isBack) return true;
    // `false` aborts the popstate navigation and vue-router restores the history entry, so the
    // next Back behaves exactly like this one.
    return (await closeTop()) === 'none';
  });
}

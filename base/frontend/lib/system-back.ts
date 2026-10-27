// Android's Back button on the installed app (BASE-F05, gh:hub#1906; ported from the old hub's
// `apps/web/src/router/back-closes-overlay.ts`, origin/develop): it closes what is open on top BEFORE it leaves the
// screen, and only Home leaves the app.
//
// On the installed Android app, Tauri's activity turns the system Back into `webView.goBack()` — but only while nobody
// listens to its `back-button` event. With nobody listening, an app opened cold (a link, a reload) closed the app on
// Back, and the router slid the screen away taking the «My apps» sheet, a modal or the side menu with it. Android's
// rule — and what every POS on it does (Square, Loyverse) — is the opposite: Back dismisses the topmost layer first,
// then goes up, and only the start screen leaves the app.
//
// So base TAKES the button (`installSystemBackButton`) and never cancels a navigation: a guard that aborts the popstate
// leaves @ionic/vue-router with a stale "this was a Back" and the next push animates to the wrong view (rv-2042). The
// browser's own Back arrow stays a plain navigation, as in most Ionic apps.
//
// A press, topmost first:
//   1. a presented Ionic overlay in the document (modal, alert, popover, action sheet, loading) — dismissed with role
//      `backdrop` like Ionic's own hardware back; one that cannot be dismissed (`backdropDismiss: false`) HOLDS it;
//   2. an open `ion-menu` (the drawer); one still sliding in or out HOLDS the press (Ionic ignores a close mid-slide,
//      and the screen must not move under it);
//   3. the mounted app, through the `erplora:back` contract below;
//   and with nothing open:
//   4. on a detail view, the screen's own Back (the topbar's: history inside the app, else its `backHref`);
//   5. on the root of an app, Home, with history behind or not: a screen of an app has no Back (PLAN-MIGRATIONS §16),
//      and Home is where the menu's «Home» and the «My apps» sheet's lead;
//   6. on Home, out of the app (`leave_app`), what the system Back does on a start screen.
//
// APP CONTRACT — `erplora:back`. An app may draw a sheet of its own (not an Ionic overlay) that the shell cannot see
// nor close. On every Back the shell dispatches a cancelable `erplora:back` on `window`. An app with something open
// closes its TOPMOST layer synchronously and calls `event.preventDefault()`: the shell then keeps the screen. An app
// with nothing open ignores it.
import { nativeBridge } from '@erplora/ui/shell';

export const SHELL_BACK_EVENT = 'erplora:back';

/** `closed`: a layer was dismissed · `held`: one refuses to close · `none`: nothing was open. */
export type BackOutcome = 'closed' | 'held' | 'none';

/** Ionic's own overlay list (`getOverlays` in @ionic/core) minus the toast, which never blocks. */
const IONIC_OVERLAYS = 'ion-alert,ion-action-sheet,ion-loading,ion-modal,ion-picker-legacy,ion-popover';

/** The topbar's Back of the screen on view: AppTopbar paints it only on a detail view (`backHref`). */
const SCREEN_BACK = 'ion-router-outlet > .ion-page:not(.ion-page-hidden) ion-header.app-topbar [data-testid="topbar-back"]';

/** The plugin event Tauri's `onBackButtonPress` listens to (`@tauri-apps/api/app`), through the bridge. */
const BACK_BUTTON = ['app', 'back-button'] as const;

/** Our Android plugin's way out, used on Home with nothing to close. */
const LEAVE_APP = 'plugin:erplora-android|leave_app';

type IonicOverlay = HTMLElement & {
  overlayIndex?: number;
  backdropDismiss?: boolean;
  dismiss: (data?: unknown, role?: string) => Promise<boolean>;
};
type IonicMenu = HTMLElement & { isOpen?: () => Promise<boolean>; close?: () => Promise<boolean> };

function topmostPresentedOverlay(doc: Document): IonicOverlay | undefined {
  // Same test as Ionic's `getPresentedOverlay`: registered (`overlayIndex > 0`) and not an inline overlay parked
  // hidden. Document order is presentation order, so the last one is on top.
  const presented = Array.from(doc.querySelectorAll<IonicOverlay>(IONIC_OVERLAYS)).filter(
    (overlay) => (overlay.overlayIndex ?? 0) > 0 && !overlay.classList.contains('overlay-hidden'),
  );
  return presented[presented.length - 1];
}

/** Ionic's class on a drawer that is showing: open, or sliding in or out (never the menu pinned beside the content). */
const MENU_SHOWN = 'show-menu';

async function shownMenu(doc: Document): Promise<{ menu: IonicMenu; open: boolean } | undefined> {
  for (const menu of Array.from(doc.querySelectorAll<IonicMenu>('ion-menu'))) {
    const open = typeof menu.isOpen === 'function' && (await menu.isOpen());
    if (open || menu.classList.contains(MENU_SHOWN)) return { menu, open };
  }
  return undefined;
}

/** Closes the topmost thing open on the screen, if any (layers 1–3). */
export async function closeTopmostLayer(doc: Document = document, win: Window = window): Promise<BackOutcome> {
  const overlay = topmostPresentedOverlay(doc);
  if (overlay) {
    if (!overlay.backdropDismiss) return 'held';
    // Not awaited on purpose (as Ionic does): a `canDismiss` that asks for confirmation must not block the Back of the
    // alert it opens.
    void overlay.dismiss(undefined, 'backdrop');
    return 'closed';
  }
  const shown = await shownMenu(doc);
  if (shown) {
    if (!shown.open || !shown.menu.close) return 'held';
    void shown.menu.close();
    return 'closed';
  }
  const ask = new CustomEvent(SHELL_BACK_EVENT, { cancelable: true });
  win.dispatchEvent(ask);
  return ask.defaultPrevented ? 'closed' : 'none';
}

/** The Back of the screen on view, on a detail view; `null` on the root of an app and on Home. */
export function screenBack(doc: Document = document): HTMLElement | null {
  return doc.querySelector<HTMLElement>(SCREEN_BACK);
}

export interface SystemBackOptions {
  /** Is the screen on view Home? */
  atHome: () => boolean;
  /** Goes Home, as the menu's «Home» does. */
  goHome: () => unknown;
  /** Where the installed app's bridge lives and `pagehide` is heard. Default `window`. */
  win?: Window;
  /** Layers 1–3. Default `closeTopmostLayer` on `document` and `window`. */
  closeTop?: () => Promise<BackOutcome>;
  /** Layer 4. Default `screenBack` on `document`. */
  screenBack?: () => HTMLElement | null;
}

/**
 * Takes the Android Back button (the `app` plugin's `back-button`, what Tauri's `onBackButtonPress` listens to). With
 * a listener registered Tauri no longer moves the WebView itself, so the shell does what the press means (see above).
 *
 * Resolves how to let go of the button, or `null` where there is none — a browser, or an app that refuses the listener.
 * The listener is also dropped on `pagehide`: Tauri keeps listeners across page loads, and a dead one would swallow the
 * button on whatever page the app loads next.
 */
export async function installSystemBackButton(opts: SystemBackOptions): Promise<(() => void) | null> {
  const win = opts.win ?? window;
  const closeTop = opts.closeTop ?? (() => closeTopmostLayer());
  const findBack = opts.screenBack ?? (() => screenBack());
  const bridge = nativeBridge(win);
  if (!bridge?.addPluginListener) return null;
  let listener: { unregister: () => Promise<void> };
  let listening = true;
  const release = () => {
    if (!listening) return;
    listening = false;
    win.removeEventListener('pagehide', release);
    listener.unregister().catch((error: unknown) => console.error('base: could not let go of the Back button', error));
  };
  try {
    listener = await bridge.addPluginListener(...BACK_BUTTON, async () => {
      if ((await closeTop()) !== 'none') return;
      const back = findBack();
      if (back) return back.click();
      if (!opts.atHome()) return void opts.goHome();
      // An app build older than `leave_app` refuses it: give the button back to Tauri, whose own Back leaves from the
      // root, instead of a button that no longer does anything.
      await bridge.invoke(LEAVE_APP).catch(release);
    });
  } catch (error) {
    // The button stays Tauri's (its own Back), as before the shell took it.
    console.warn('base: the app did not hand over its Back button', error);
    return null;
  }
  win.addEventListener('pagehide', release);
  return release;
}

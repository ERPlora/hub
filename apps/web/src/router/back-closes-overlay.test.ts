// @vitest-environment happy-dom
//
// hub#1906 — Android's Back button, with the payment sheet open, threw the cashier out of the till.
//
// On the installed app Tauri's Android activity turns the system Back into `webView.goBack()` —
// but ONLY while nobody listens to its `back-button` event (`AppPlugin.kt`). Nobody in the shell
// did, so the router left the screen and took whatever was open on top of it (the payment sheet, a
// modal, the side menu) with it. Android — and every POS on it (Square, Loyverse) — does the
// opposite: Back dismisses what is open on top FIRST, and only an empty screen goes back.
//
// The first fix aborted the popstate navigation from a router guard. That leaves @ionic/vue-router
// with a stale "this was a Back" (rv-2042; `back-button-ionic-navinfo.hub1906.test.ts`), so the
// shell now takes the button itself and NEVER cancels a navigation: it closes a layer, or goes back,
// or leaves the app.
//
// The contract pinned here:
//   1. `closeTopmostLayer`: a presented Ionic overlay is dismissed (role `backdrop`, as Ionic's own
//      hardware back); one that cannot be dismissed HOLDS the press; inline-hidden overlays and
//      toasts do not count; then an open `ion-menu`; then the module, through the cancelable
//      `erplora:back` event (`preventDefault()` = "I closed something");
//   2. `installSystemBackButton`: on Android it registers Tauri's `onBackButtonPress`; a press with
//      something open closes it and stays; with nothing open it goes back in the WebView history, or
//      — with no history left — leaves the app, as the system Back would;
//   3. outside the Android app (browser, desktop) it registers nothing and never throws;
//   4. the listener is unregistered when the page goes away: Tauri keeps listeners across page
//      loads, and a dead one would swallow the button on the next page.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SHELL_BACK_EVENT, closeTopmostLayer, installSystemBackButton, type BackOutcome } from './back-closes-overlay';

type FakeOverlay = HTMLElement & { overlayIndex: number; backdropDismiss?: boolean; dismiss: ReturnType<typeof vi.fn> };

function presentOverlay(tag: string, opts: { backdropDismiss?: boolean; hidden?: boolean } = {}): FakeOverlay {
  // A custom tag stands in for the Ionic one: this file never registers Ionic's elements, but the
  // selector is the real one, so the fake has to wear the real tag name.
  const el = document.createElement(tag) as FakeOverlay;
  el.overlayIndex = 1;
  el.backdropDismiss = opts.backdropDismiss ?? true;
  el.dismiss = vi.fn(async () => {
    el.remove();
    return true;
  });
  if (opts.hidden) el.classList.add('overlay-hidden');
  document.body.appendChild(el);
  return el;
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('hub#1906 — closeTopmostLayer', () => {
  it('dismisses a presented Ionic modal', async () => {
    const modal = presentOverlay('ion-modal');

    await expect(closeTopmostLayer(document, window)).resolves.toBe('closed');
    expect(modal.dismiss).toHaveBeenCalledWith(undefined, 'backdrop');
  });

  it('closes only the TOPMOST overlay, one per press', async () => {
    const below = presentOverlay('ion-modal');
    const top = presentOverlay('ion-alert');

    await expect(closeTopmostLayer(document, window)).resolves.toBe('closed');
    expect(top.dismiss).toHaveBeenCalledTimes(1);
    expect(below.dismiss).not.toHaveBeenCalled();
  });

  it('an overlay that cannot be dismissed holds the press', async () => {
    const loading = presentOverlay('ion-loading', { backdropDismiss: false });

    await expect(closeTopmostLayer(document, window)).resolves.toBe('held');
    expect(loading.dismiss).not.toHaveBeenCalled();
  });

  it('an inline overlay that is NOT presented does not count', async () => {
    const idle = presentOverlay('ion-modal', { hidden: true });

    await expect(closeTopmostLayer(document, window)).resolves.toBe('none');
    expect(idle.dismiss).not.toHaveBeenCalled();
  });

  it('a toast never holds the press', async () => {
    const toast = presentOverlay('ion-toast', { backdropDismiss: false });

    await expect(closeTopmostLayer(document, window)).resolves.toBe('none');
    expect(toast.dismiss).not.toHaveBeenCalled();
  });

  it('closes an open side menu', async () => {
    const menu = document.createElement('ion-menu') as unknown as HTMLElement & { isOpen: () => Promise<boolean>; close: ReturnType<typeof vi.fn> };
    menu.isOpen = async () => true;
    menu.close = vi.fn(async () => true);
    document.body.appendChild(menu);

    await expect(closeTopmostLayer(document, window)).resolves.toBe('closed');
    expect(menu.close).toHaveBeenCalledTimes(1);
  });

  it('asks the module with a CANCELABLE `erplora:back`; `preventDefault()` means it closed something', async () => {
    let sheetOpen = true;
    let seen: Event | undefined;
    const onBack = (e: Event) => {
      seen = e;
      if (!sheetOpen) return;
      sheetOpen = false;
      e.preventDefault();
    };
    window.addEventListener(SHELL_BACK_EVENT, onBack);
    try {
      await expect(closeTopmostLayer(document, window)).resolves.toBe('closed');
      expect(seen?.cancelable).toBe(true);
      expect(sheetOpen).toBe(false);
      // Nothing left open in the module.
      await expect(closeTopmostLayer(document, window)).resolves.toBe('none');
    } finally {
      window.removeEventListener(SHELL_BACK_EVENT, onBack);
    }
  });
});

type BackHandler = (payload: { canGoBack: boolean }) => void | Promise<void>;

/** Tauri's global as `withGlobalTauri` exposes it: only the one call the shell uses. */
function fakeTauri(opts: { rejects?: boolean } = {}) {
  const state: { handler?: BackHandler; unregister: ReturnType<typeof vi.fn> } = { unregister: vi.fn(async () => undefined) };
  const onBackButtonPress = vi.fn(async (handler: BackHandler) => {
    if (opts.rejects) throw new Error('plugin app not found');
    state.handler = handler;
    return { unregister: state.unregister };
  });
  const win = Object.assign(new EventTarget(), {
    __TAURI__: { app: { onBackButtonPress } },
    history: { back: vi.fn() },
  });
  return { win: win as unknown as Window, state, onBackButtonPress, historyBack: win.history.back };
}

describe('hub#1906 — installSystemBackButton (the Android button)', () => {
  function setup(outcome: BackOutcome) {
    const tauri = fakeTauri();
    const closeTop = vi.fn(async () => outcome);
    const leaveApp = vi.fn(async () => undefined);
    return { ...tauri, closeTop, leaveApp };
  }

  it('with something open: closes it and stays — no history move, no leaving', async () => {
    const t = setup('closed');
    await expect(installSystemBackButton({ win: t.win, closeTop: t.closeTop, leaveApp: t.leaveApp })).resolves.toBe(true);

    await t.state.handler!({ canGoBack: true });

    expect(t.closeTop).toHaveBeenCalledTimes(1);
    expect(t.historyBack).not.toHaveBeenCalled();
    expect(t.leaveApp).not.toHaveBeenCalled();
  });

  it('a layer that holds the press: nothing else happens', async () => {
    const t = setup('held');
    await installSystemBackButton({ win: t.win, closeTop: t.closeTop, leaveApp: t.leaveApp });

    await t.state.handler!({ canGoBack: true });

    expect(t.historyBack).not.toHaveBeenCalled();
    expect(t.leaveApp).not.toHaveBeenCalled();
  });

  it('with nothing open and history behind: goes back, like the system Back', async () => {
    const t = setup('none');
    await installSystemBackButton({ win: t.win, closeTop: t.closeTop, leaveApp: t.leaveApp });

    await t.state.handler!({ canGoBack: true });

    expect(t.historyBack).toHaveBeenCalledTimes(1);
    expect(t.leaveApp).not.toHaveBeenCalled();
  });

  it('with nothing open and no history: leaves the app, like the system Back', async () => {
    const t = setup('none');
    await installSystemBackButton({ win: t.win, closeTop: t.closeTop, leaveApp: t.leaveApp });

    await t.state.handler!({ canGoBack: false });

    expect(t.leaveApp).toHaveBeenCalledTimes(1);
    expect(t.historyBack).not.toHaveBeenCalled();
  });

  it('an app build without `leave_app` hands the button back to Tauri instead of leaving it dead', async () => {
    // The web ships with the hub, the APK with the store: an older app may lack the command. Once
    // the listener is gone Tauri's own Back runs again (goBack, or the system Back at the root).
    const t = setup('none');
    t.leaveApp.mockRejectedValueOnce(new Error('command leave_app not found'));
    await installSystemBackButton({ win: t.win, closeTop: t.closeTop, leaveApp: t.leaveApp });

    await expect(t.state.handler!({ canGoBack: false })).resolves.toBeUndefined();

    expect(t.state.unregister).toHaveBeenCalledTimes(1);
  });

  it('unregisters the listener when the page goes away', async () => {
    const t = setup('none');
    await installSystemBackButton({ win: t.win, closeTop: t.closeTop, leaveApp: t.leaveApp });

    t.win.dispatchEvent(new Event('pagehide'));

    expect(t.state.unregister).toHaveBeenCalledTimes(1);
  });

  it('outside the Android app (no Tauri global) registers nothing', async () => {
    const win = Object.assign(new EventTarget(), { history: { back: vi.fn() } }) as unknown as Window;

    await expect(installSystemBackButton({ win })).resolves.toBe(false);
  });

  it('where Tauri has no back button (desktop refuses the listener) it does not throw', async () => {
    const t = fakeTauri({ rejects: true });

    await expect(installSystemBackButton({ win: t.win })).resolves.toBe(false);
    expect(t.onBackButtonPress).toHaveBeenCalledTimes(1);
  });
});

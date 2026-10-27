// BASE-F05 · gh:hub#1906 — Android's Back button on the installed app (ported from the old hub's
// `apps/web/src/router/back-closes-overlay.ts` and its test, origin/develop).
//
// On the installed app Tauri's Android activity turns the system Back into `webView.goBack()` — but ONLY while nobody
// listens to its `back-button` event. Nobody in the Hub did: an app opened cold (a link, a reload) CLOSED the app on
// Back, and with a sheet, a modal or the menu open the router took the screen away with them. Android — and every POS
// on it — does the opposite: Back dismisses what is open on top FIRST, and only the start screen leaves the app.
//
// The contract pinned here:
//   1. `closeTopmostLayer`: a presented Ionic overlay is dismissed (role `backdrop`, as Ionic's own hardware back); one
//      that cannot be dismissed HOLDS the press; inline-hidden overlays and toasts do not count; then an open
//      `ion-menu`; then the mounted app, through the cancelable `erplora:back` (`preventDefault()` = "I closed one");
//   2. `installSystemBackButton`, with nothing open: on a detail view the screen's own Back (the topbar's: history
//      inside the app, else its `backHref`); on the root of an app, Home, with history behind or not (a screen of an
//      app has no Back, PLAN-MIGRATIONS §16); on Home, out of the app (`leave_app`), as the system Back would;
//   3. it never cancels a navigation (rv-2042), and outside the installed app it registers nothing and never throws;
//   4. the listener goes when the page goes (Tauri keeps listeners across page loads) or when the shell lets go.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { type BackOutcome, closeTopmostLayer, installSystemBackButton, screenBack, SHELL_BACK_EVENT } from './system-back';

type FakeOverlay = HTMLElement & { overlayIndex: number; backdropDismiss?: boolean; dismiss: ReturnType<typeof vi.fn> };

function presentOverlay(tag: string, opts: { backdropDismiss?: boolean; hidden?: boolean } = {}): FakeOverlay {
  // This file never registers Ionic's elements, but the selector is the real one: the fake wears the real tag name.
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

type FakeMenu = HTMLElement & { isOpen: () => Promise<boolean>; close: ReturnType<typeof vi.fn> };

function openMenu(): FakeMenu {
  const menu = document.createElement('ion-menu') as unknown as FakeMenu;
  menu.isOpen = async () => true;
  menu.close = vi.fn(async () => true);
  document.body.appendChild(menu);
  return menu;
}

/** A screen in the outlet as the shell paints it: the topbar, with Back only on a detail view; `hidden` = left behind. */
function screen(opts: { back?: boolean; hidden?: boolean } = {}): HTMLElement | null {
  let outlet = document.querySelector('ion-router-outlet');
  if (!outlet) outlet = document.body.appendChild(document.createElement('ion-router-outlet'));
  const page = document.createElement('div');
  page.className = opts.hidden ? 'ion-page ion-page-hidden' : 'ion-page';
  page.innerHTML = `<ion-header class="app-topbar"><ion-toolbar><ion-buttons slot="start">${
    opts.back ? '<ion-button data-testid="topbar-back"></ion-button>' : ''
  }</ion-buttons></ion-toolbar></ion-header>`;
  outlet.appendChild(page);
  return page.querySelector<HTMLElement>('[data-testid="topbar-back"]');
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('gh:hub#1906 — closeTopmostLayer', () => {
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
    const menu = openMenu();

    await expect(closeTopmostLayer(document, window)).resolves.toBe('closed');
    expect(menu.close).toHaveBeenCalledTimes(1);
  });

  it('asks the app with a CANCELABLE `erplora:back`; `preventDefault()` means it closed something', async () => {
    let sheetOpen = true;
    let seen: Event | undefined;
    const onBack = (event: Event) => {
      seen = event;
      if (!sheetOpen) return;
      sheetOpen = false;
      event.preventDefault();
    };
    window.addEventListener(SHELL_BACK_EVENT, onBack);
    try {
      await expect(closeTopmostLayer(document, window)).resolves.toBe('closed');
      expect(seen?.cancelable).toBe(true);
      expect(sheetOpen).toBe(false);
      // Nothing left open in the app.
      await expect(closeTopmostLayer(document, window)).resolves.toBe('none');
    } finally {
      window.removeEventListener(SHELL_BACK_EVENT, onBack);
    }
  });
});

describe('screenBack — the Back of the screen on view', () => {
  it('is the topbar\'s Back of a detail view', () => {
    const back = screen({ back: true });

    expect(screenBack(document)).toBe(back);
  });

  it('the root of an app has none', () => {
    screen();

    expect(screenBack(document)).toBeNull();
  });

  it('a screen left behind in the outlet does not count', () => {
    screen({ back: true, hidden: true });
    screen();

    expect(screenBack(document)).toBeNull();
  });
});

type BackHandler = (payload: unknown) => void | Promise<void>;

/** The installed app's bridge as `withGlobalTauri` exposes it: only what the shell uses. */
function fakeTauri(opts: { refuses?: boolean; leaveApp?: () => Promise<unknown> } = {}) {
  const state: { handler?: BackHandler; unregister: ReturnType<typeof vi.fn> } = { unregister: vi.fn(async () => undefined) };
  const addPluginListener = vi.fn(async (_plugin: string, _event: string, handler: BackHandler) => {
    if (opts.refuses) throw new Error('plugin app not found');
    state.handler = handler;
    return { unregister: state.unregister };
  });
  const invoke = vi.fn(async (command: string) => {
    if (command === 'plugin:erplora-android|leave_app') return (opts.leaveApp ?? (async () => null))();
    return null;
  });
  const win = Object.assign(new EventTarget(), { __TAURI__: { core: { invoke, addPluginListener } } }) as unknown as Window;
  return { win, state, addPluginListener, invoke };
}

describe('gh:hub#1906 — installSystemBackButton (the Android button)', () => {
  function setup(opts: { outcome?: BackOutcome; back?: HTMLElement | null; home?: boolean; leaveApp?: () => Promise<unknown> } = {}) {
    const tauri = fakeTauri({ leaveApp: opts.leaveApp });
    const closeTop = vi.fn(async () => opts.outcome ?? 'none');
    const goHome = vi.fn();
    const back = opts.back ?? null;
    const install = () =>
      installSystemBackButton({ win: tauri.win, closeTop, screenBack: () => back, atHome: () => opts.home ?? false, goHome });
    return { ...tauri, closeTop, goHome, install };
  }

  const leftTheApp = (invoke: ReturnType<typeof vi.fn>) =>
    invoke.mock.calls.some(([command]) => command === 'plugin:erplora-android|leave_app');

  it('takes the button: listens to the `app` plugin\'s `back-button`', async () => {
    const t = setup();

    await expect(t.install()).resolves.toBeTypeOf('function');
    expect(t.addPluginListener).toHaveBeenCalledWith('app', 'back-button', expect.any(Function));
  });

  it('with something open: closes it and stays — no screen Back, no Home, no leaving', async () => {
    const back = document.createElement('button');
    const click = vi.spyOn(back, 'click');
    const t = setup({ outcome: 'closed', back });
    await t.install();

    await t.state.handler!({});

    expect(t.closeTop).toHaveBeenCalledTimes(1);
    expect(click).not.toHaveBeenCalled();
    expect(t.goHome).not.toHaveBeenCalled();
    expect(leftTheApp(t.invoke)).toBe(false);
  });

  it('a layer that holds the press: nothing else happens', async () => {
    const t = setup({ outcome: 'held', home: true });
    await t.install();

    await t.state.handler!({});

    expect(t.goHome).not.toHaveBeenCalled();
    expect(leftTheApp(t.invoke)).toBe(false);
  });

  it('on a detail view with nothing open: the screen\'s own Back', async () => {
    const back = document.createElement('button');
    const click = vi.spyOn(back, 'click');
    const t = setup({ back });
    await t.install();

    await t.state.handler!({});

    expect(click).toHaveBeenCalledTimes(1);
    expect(t.goHome).not.toHaveBeenCalled();
    expect(leftTheApp(t.invoke)).toBe(false);
  });

  it('on the root of an app with nothing open: Home, with history behind or not', async () => {
    const t = setup();
    await t.install();

    await t.state.handler!({ canGoBack: false });
    await t.state.handler!({ canGoBack: true });

    expect(t.goHome).toHaveBeenCalledTimes(2);
    expect(leftTheApp(t.invoke)).toBe(false);
  });

  it('on Home with nothing open: leaves the app, like the system Back on the start screen', async () => {
    const t = setup({ home: true });
    await t.install();

    await t.state.handler!({ canGoBack: true });

    expect(t.invoke).toHaveBeenCalledWith('plugin:erplora-android|leave_app');
    expect(t.goHome).not.toHaveBeenCalled();
  });

  it('an app build without `leave_app` hands the button back to Tauri instead of leaving it dead', async () => {
    // The page ships with the Hub, the APK with the store: an older app may lack the command. Once the listener is
    // gone Tauri's own Back runs again.
    const t = setup({ home: true, leaveApp: async () => Promise.reject(new Error('command leave_app not found')) });
    const release = await t.install();

    await expect(t.state.handler!({})).resolves.toBeUndefined();
    expect(t.state.unregister).toHaveBeenCalledTimes(1);

    // Already handed back: the person signing out later lets go of nothing more.
    release!();
    expect(t.state.unregister).toHaveBeenCalledTimes(1);
  });

  it('never navigates on its own on a press: the screen\'s Back and Home are the shell\'s', async () => {
    const pushState = vi.spyOn(window.history, 'pushState');
    const historyBack = vi.spyOn(window.history, 'back');
    const t = setup();
    await t.install();

    await t.state.handler!({});

    expect(pushState).not.toHaveBeenCalled();
    expect(historyBack).not.toHaveBeenCalled();
    pushState.mockRestore();
    historyBack.mockRestore();
  });

  it('unregisters the listener when the page goes away', async () => {
    const t = setup();
    await t.install();

    t.win.dispatchEvent(new Event('pagehide'));

    expect(t.state.unregister).toHaveBeenCalledTimes(1);
  });

  it('lets go of the button when the shell asks (the person signs out), once', async () => {
    const t = setup();
    const release = await t.install();

    release!();
    t.win.dispatchEvent(new Event('pagehide'));

    expect(t.state.unregister).toHaveBeenCalledTimes(1);
  });

  it('outside the installed app (no Tauri global) registers nothing', async () => {
    const win = Object.assign(new EventTarget(), {}) as unknown as Window;

    await expect(installSystemBackButton({ win, atHome: () => false, goHome: vi.fn() })).resolves.toBeNull();
  });

  it('where the app refuses the listener it does not throw, and says so in the console', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const t = fakeTauri({ refuses: true });

    await expect(installSystemBackButton({ win: t.win, atHome: () => false, goHome: vi.fn() })).resolves.toBeNull();
    expect(t.addPluginListener).toHaveBeenCalledTimes(1);
    expect(warn).toHaveBeenCalledWith('base: the app did not hand over its Back button', expect.any(Error));
    warn.mockRestore();
  });
});

// The layers end to end on the real document and window (`window.__TAURI__` as the installed app puts it), every
// default in place: what is open is closed first, and only an empty screen moves. The shell's barrel registers Ionic's
// elements, which park an inline overlay hidden once they upgrade: each screen is arranged right before the press.
describe('gh:hub#1906 — a press on the real document, layer by layer', () => {
  type TauriWindow = { __TAURI__?: unknown };
  let release: (() => void) | null = null;

  afterEach(() => {
    release?.();
    release = null;
    delete (window as TauriWindow).__TAURI__;
  });

  async function press(arrange: () => void, opts: { home?: boolean } = {}) {
    const tauri = fakeTauri();
    (window as TauriWindow).__TAURI__ = (tauri.win as unknown as TauriWindow).__TAURI__;
    const goHome = vi.fn();
    release = await installSystemBackButton({ atHome: () => opts.home ?? false, goHome });
    arrange();
    await tauri.state.handler!({});
    return { goHome, left: tauri.invoke.mock.calls.some(([command]) => command === 'plugin:erplora-android|leave_app') };
  }

  it('the «My apps» sheet open on the root of an app: the sheet closes, the screen stays', async () => {
    let sheet: FakeOverlay | undefined;
    const { goHome, left } = await press(() => {
      screen();
      sheet = presentOverlay('ion-modal');
    });

    expect(sheet!.dismiss).toHaveBeenCalledWith(undefined, 'backdrop');
    expect(goHome).not.toHaveBeenCalled();
    expect(left).toBe(false);
  });

  it('a dialog that cannot be dismissed: the screen stays, even on Home', async () => {
    let alert: FakeOverlay | undefined;
    const { goHome, left } = await press(
      () => {
        screen();
        alert = presentOverlay('ion-alert', { backdropDismiss: false });
      },
      { home: true },
    );

    expect(alert!.dismiss).not.toHaveBeenCalled();
    expect(goHome).not.toHaveBeenCalled();
    expect(left).toBe(false);
  });

  it('the drawer open: it closes, the screen stays', async () => {
    let menu: FakeMenu | undefined;
    const { goHome } = await press(() => {
      screen();
      menu = openMenu();
    });

    expect(menu!.close).toHaveBeenCalledTimes(1);
    expect(goHome).not.toHaveBeenCalled();
  });

  it('an app with its own sheet open says so with `erplora:back`: the screen stays', async () => {
    const onBack = (event: Event) => event.preventDefault();
    window.addEventListener(SHELL_BACK_EVENT, onBack);
    try {
      const { goHome, left } = await press(() => screen());

      expect(goHome).not.toHaveBeenCalled();
      expect(left).toBe(false);
    } finally {
      window.removeEventListener(SHELL_BACK_EVENT, onBack);
    }
  });

  it('a detail view: its topbar Back', async () => {
    let click: ReturnType<typeof vi.spyOn> | undefined;
    const { goHome } = await press(() => {
      click = vi.spyOn(screen({ back: true })!, 'click');
    });

    expect(click).toHaveBeenCalledTimes(1);
    expect(goHome).not.toHaveBeenCalled();
  });

  it('the root of an app: Home', async () => {
    const { goHome, left } = await press(() => screen());

    expect(goHome).toHaveBeenCalledTimes(1);
    expect(left).toBe(false);
  });

  it('Home: out of the app', async () => {
    const { goHome, left } = await press(() => screen(), { home: true });

    expect(goHome).not.toHaveBeenCalled();
    expect(left).toBe(true);
  });
});

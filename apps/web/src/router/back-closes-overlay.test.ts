// @vitest-environment happy-dom
//
// hub#1906 — Android's Back button, with the payment sheet open, threw the cashier out of the till.
//
// On the installed app the system Back button is a plain `history.back()` of the WebView: nobody in
// the shell listened for it, so the router left the screen and whatever was open on top of it
// (the payment sheet, a modal, the side menu) vanished with the screen. Android — and every POS on
// it (Square, Loyverse) — does the opposite: Back dismisses what is open on top FIRST, and only an
// empty screen navigates.
//
// The contract pinned here:
//   1. a presented Ionic overlay is dismissed (role `backdrop`, as Ionic's own hardware back does)
//      and the route does NOT change;
//   2. an overlay that cannot be dismissed (`backdropDismiss: false`, e.g. a loading) HOLDS the
//      back — it neither closes nor lets the page slide away underneath it;
//   3. a module that owns its own sheets hears `erplora:back`; calling `preventDefault()` means "I
//      closed something" and the route stays;
//   4. nothing open → Back navigates exactly as before (and a toast never holds it);
//   5. forward navigations (`push`) never consult any of this;
//   6. the REAL router is wired: the shell's own router honours it, not just a test double.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createMemoryHistory, createRouter, type Router } from 'vue-router';
import { SHELL_BACK_EVENT, closeTopmostLayer, installBackClosesOverlay } from './back-closes-overlay';

const Blank = { template: '<div />' };

async function tillRouter(): Promise<Router> {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/dashboard', component: Blank },
      { path: '/m/sales', component: Blank },
    ],
  });
  installBackClosesOverlay(router);
  await router.push('/dashboard');
  await router.push('/m/sales');
  return router;
}

/** Waits for the popstate navigation `router.back()` fires (memory history triggers it at once). */
async function pressBack(router: Router): Promise<void> {
  router.back();
  // The guard is async (menus answer through a promise): let the navigation — or its revert — settle.
  for (let i = 0; i < 10; i++) await new Promise((r) => setTimeout(r, 0));
}

type FakeOverlay = HTMLElement & { overlayIndex: number; backdropDismiss?: boolean; dismiss: ReturnType<typeof vi.fn> };

function presentOverlay(tag: string, opts: { backdropDismiss?: boolean; hidden?: boolean } = {}): FakeOverlay {
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

describe('hub#1906 — system Back closes what is open before leaving the screen', () => {
  it('dismisses a presented Ionic modal and stays on the screen', async () => {
    const router = await tillRouter();
    const modal = presentOverlay('ion-modal');

    await pressBack(router);

    expect(modal.dismiss).toHaveBeenCalledWith(undefined, 'backdrop');
    expect(router.currentRoute.value.path).toBe('/m/sales');
  });

  it('closes only the TOPMOST overlay, one per press', async () => {
    const router = await tillRouter();
    const below = presentOverlay('ion-modal');
    const top = presentOverlay('ion-alert');

    await pressBack(router);

    expect(top.dismiss).toHaveBeenCalledTimes(1);
    expect(below.dismiss).not.toHaveBeenCalled();
    expect(router.currentRoute.value.path).toBe('/m/sales');
  });

  it('a second Back, with nothing left open, navigates as before', async () => {
    const router = await tillRouter();
    presentOverlay('ion-modal');

    await pressBack(router);
    await pressBack(router);

    expect(router.currentRoute.value.path).toBe('/dashboard');
  });

  it('an overlay that cannot be dismissed holds the Back: it stays open and so does the screen', async () => {
    const router = await tillRouter();
    const loading = presentOverlay('ion-loading', { backdropDismiss: false });

    await pressBack(router);

    expect(loading.dismiss).not.toHaveBeenCalled();
    expect(router.currentRoute.value.path).toBe('/m/sales');
  });

  it('an inline overlay that is NOT presented does not count', async () => {
    const router = await tillRouter();
    const idle = presentOverlay('ion-modal', { hidden: true });

    await pressBack(router);

    expect(idle.dismiss).not.toHaveBeenCalled();
    expect(router.currentRoute.value.path).toBe('/dashboard');
  });

  it('a toast never holds the Back', async () => {
    const router = await tillRouter();
    const toast = presentOverlay('ion-toast', { backdropDismiss: false });

    await pressBack(router);

    expect(toast.dismiss).not.toHaveBeenCalled();
    expect(router.currentRoute.value.path).toBe('/dashboard');
  });

  it('closes an open side menu before leaving', async () => {
    const router = await tillRouter();
    const menu = document.createElement('ion-menu') as unknown as HTMLElement & { isOpen: () => Promise<boolean>; close: ReturnType<typeof vi.fn> };
    menu.isOpen = async () => true;
    menu.close = vi.fn(async () => true);
    document.body.appendChild(menu);

    await pressBack(router);

    expect(menu.close).toHaveBeenCalledTimes(1);
    expect(router.currentRoute.value.path).toBe('/m/sales');
  });

  it('a module that closes its own sheet on `erplora:back` keeps the cashier on the screen', async () => {
    const router = await tillRouter();
    let sheetOpen = true;
    const onBack = (e: Event) => {
      if (!sheetOpen) return;
      sheetOpen = false;
      e.preventDefault();
    };
    window.addEventListener(SHELL_BACK_EVENT, onBack);
    try {
      await pressBack(router);
      expect(sheetOpen).toBe(false);
      expect(router.currentRoute.value.path).toBe('/m/sales');

      // Nothing left open in the module: the next Back leaves the screen.
      await pressBack(router);
      expect(router.currentRoute.value.path).toBe('/dashboard');
    } finally {
      window.removeEventListener(SHELL_BACK_EVENT, onBack);
    }
  });

  it('the module hears a CANCELABLE event, so its "I closed something" can be read back', async () => {
    let seen: Event | undefined;
    const onBack = (e: Event) => {
      seen = e;
    };
    window.addEventListener(SHELL_BACK_EVENT, onBack);
    try {
      await expect(closeTopmostLayer(document, window)).resolves.toBe('none');
      expect(seen?.cancelable).toBe(true);
    } finally {
      window.removeEventListener(SHELL_BACK_EVENT, onBack);
    }
  });

  it('a forward navigation never dismisses anything', async () => {
    const router = await tillRouter();
    const modal = presentOverlay('ion-modal');

    await router.push('/dashboard');

    expect(modal.dismiss).not.toHaveBeenCalled();
    expect(router.currentRoute.value.path).toBe('/dashboard');
  });
});

describe('hub#1906 — the shell router is wired', () => {
  it("the shell's own router keeps the screen when the module closes its sheet on Back", async () => {
    const { router } = await import('./index');
    // Throwaway, session-free routes: this pins the WIRING, not the auth gate. The layer is a
    // module's (importing the shell registers the real Ionic elements, so no fake ion-modal here).
    router.addRoute({ path: '/__hub1906/from', component: Blank });
    router.addRoute({ path: '/__hub1906/till', component: Blank });
    await router.push('/__hub1906/from');
    await router.push('/__hub1906/till');
    let sheetOpen = true;
    const onBack = (e: Event) => {
      if (!sheetOpen) return;
      sheetOpen = false;
      e.preventDefault();
    };
    window.addEventListener(SHELL_BACK_EVENT, onBack);
    try {
      router.back();
      for (let i = 0; i < 100 && sheetOpen; i++) await new Promise((r) => setTimeout(r, 5));
      for (let i = 0; i < 10; i++) await new Promise((r) => setTimeout(r, 5));

      expect(sheetOpen).toBe(false);
      expect(router.currentRoute.value.path).toBe('/__hub1906/till');
    } finally {
      window.removeEventListener(SHELL_BACK_EVENT, onBack);
    }
  });
});

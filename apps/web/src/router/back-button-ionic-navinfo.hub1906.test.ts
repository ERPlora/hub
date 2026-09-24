// @vitest-environment happy-dom
//
// hub#1906 (rv-2042) — closing a layer with Back must leave Ionic's navigation state intact.
//
// The first fix aborted the Back's popstate navigation from a router guard. @ionic/vue-router
// records the direction of every popstate in its own `history.listen` and only clears it in an
// `afterEach` WITHOUT failure, so an aborted Back left "this was a Back to /a" behind: the next
// `router.push('/c')` reached IonRouterOutlet as a pop to /a (the reviewer's probe: `/a` instead of
// `/c`). In the till: Back closes the payment sheet, and the next screen picked from the menu
// paints the wrong view or animates backwards.
//
// Pinned here through the REAL shell router (Ionic's `createRouter`, wired by `./index`) and the
// Android button as Tauri delivers it:
//   1. Back with a sheet open closes it, keeps the screen, and the next push is a plain forward
//      push to where it was asked to go;
//   2. Back with nothing open goes back in history and Ionic sees a real pop;
//   3. the browser's own Back arrow is a plain navigation again: nobody intercepts popstate.
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import { createApp, inject } from 'vue';

type BackHandler = (payload: { canGoBack: boolean }) => Promise<void> | void;
const { tauri } = vi.hoisted(() => {
  const tauri: { handler?: BackHandler } = {};
  // `./index` installs the button at import time, so Tauri's global must exist BEFORE the import.
  (window as unknown as { __TAURI__: unknown }).__TAURI__ = {
    app: {
      onBackButtonPress: async (handler: BackHandler) => {
        tauri.handler = handler;
        return { unregister: async () => undefined };
      },
    },
    core: { invoke: async () => null },
  };
  return { tauri };
});

// The real ones POST to the runtime; in happy-dom that is a dangling fetch to nowhere.
vi.mock('../lib/error-report', () => ({ reportClientError: vi.fn(), installErrorReporting: vi.fn() }));

import { router } from './index';
import { SHELL_BACK_EVENT } from './back-closes-overlay';

type RouteInfo = { pathname: string; routerAction: string; routerDirection: string };
let nav: { getCurrentRouteInfo: () => RouteInfo } | undefined;

const Blank = { template: '<div />' };
const settle = async () => {
  for (let i = 0; i < 20; i++) await new Promise((r) => setTimeout(r, 5));
};

let sheetOpen = false;
let asked = 0;
const onBack = (e: Event) => {
  asked++;
  if (!sheetOpen) return;
  sheetOpen = false;
  e.preventDefault();
};

beforeAll(() => {
  // Throwaway, session-free routes: this pins the Back wiring, not the auth gate.
  for (const path of ['/__hub1906/a', '/__hub1906/b', '/__hub1906/c']) router.addRoute({ path, component: Blank });
  const app = createApp({ render: () => null });
  app.use(router);
  app.runWithContext(() => {
    nav = inject('navManager');
  });
  window.addEventListener(SHELL_BACK_EVENT, onBack);
});

afterAll(() => {
  window.removeEventListener(SHELL_BACK_EVENT, onBack);
});

describe('hub#1906 — the Android Back never leaves Ionic with a stale navigation', () => {
  it('the shell takes the Android button (Tauri stops doing goBack on its own)', () => {
    expect(tauri.handler, 'installed by the shell router at import').toBeTypeOf('function');
  });

  it('Back closes the open sheet, keeps the screen, and the next push is still a push', async () => {
    await router.push('/__hub1906/a');
    await router.push('/__hub1906/b');
    sheetOpen = true;

    await tauri.handler!({ canGoBack: true });
    await settle();

    expect(sheetOpen).toBe(false);
    expect(router.currentRoute.value.path).toBe('/__hub1906/b');

    await router.push('/__hub1906/c');
    await settle();
    const info = nav!.getCurrentRouteInfo();
    expect(info.pathname).toBe('/__hub1906/c');
    expect(info.routerAction).toBe('push');
    expect(info.routerDirection).toBe('forward');
  });

  it('Back with nothing open goes back, and Ionic sees a real pop', async () => {
    await tauri.handler!({ canGoBack: true });
    await settle();

    expect(router.currentRoute.value.path).toBe('/__hub1906/b');
    const info = nav!.getCurrentRouteInfo();
    expect(info.pathname).toBe('/__hub1906/b');
    expect(info.routerAction).toBe('pop');
    expect(info.routerDirection).toBe('back');
  });

  it("the browser's Back arrow is a plain navigation: nobody intercepts popstate", async () => {
    sheetOpen = true;
    asked = 0;

    router.back();
    await settle();

    expect(router.currentRoute.value.path).toBe('/__hub1906/a');
    expect(asked, 'popstate never asks the module').toBe(0);
    sheetOpen = false;
  });
});

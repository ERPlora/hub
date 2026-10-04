// @vitest-environment happy-dom
//
// hub#2325 — the side menu's screens, downloaded ahead of time, through the REAL router.
//
// A tap on the side menu used to be the moment the section's file left for the network; a blink
// right then and the tap went nowhere. The shell now downloads those screens once the app is idle.
// Two things only the real router can show: the download it does is the very one a later tap
// needs, and a download that failed sends that tap straight to a fresh document — the browser
// remembers the failed file for the life of this one (hub#2312), so asking again in place would
// only earn the person a "try again" toast they did nothing to deserve.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { toastErrorSpy } = vi.hoisted(() => ({ toastErrorSpy: vi.fn(() => Promise.resolve()) }));

vi.mock('../lib/toast', () => ({
  toast: vi.fn(() => Promise.resolve()),
  toastSuccess: vi.fn(() => Promise.resolve()),
  toastError: toastErrorSpy,
  toastInfo: vi.fn(() => Promise.resolve()),
  bootActionFeedback: vi.fn(),
}));

vi.mock('../lib/error-report', () => ({
  reportClientError: vi.fn(),
  installErrorReporting: vi.fn(),
}));

import { router } from './index';
import { prefetchSectionViews } from './prefetch-sections';

const CHUNK_ERROR = new TypeError(
  'Failed to fetch dynamically imported module: http://localhost:5173/src/views/SettingsPage.vue',
);

const HOME = '/hub2325-home';
const LAZY = '/hub2325-lazy';
const BROKEN = '/hub2325-broken';

let assign: ReturnType<typeof vi.fn>;
let lazyLoader: ReturnType<typeof vi.fn>;

beforeEach(() => {
  sessionStorage.clear();
  toastErrorSpy.mockClear();
  assign = vi.fn();
  vi.spyOn(window.location, 'assign').mockImplementation(assign as unknown as (url: string | URL) => void);
  vi.spyOn(window.location, 'reload').mockImplementation(() => {});

  lazyLoader = vi.fn(() => Promise.resolve({ render: () => null }));
  router.addRoute({ path: HOME, name: 'hub2325-home', component: { render: () => null } });
  router.addRoute({ path: LAZY, name: 'hub2325-lazy', component: lazyLoader as unknown as () => Promise<object> });
  // The blink hit the download: the browser now fails this file every time, without a request.
  router.addRoute({ path: BROKEN, name: 'hub2325-broken', component: () => Promise.reject(CHUNK_ERROR) });
});

afterEach(() => {
  for (const name of ['hub2325-home', 'hub2325-lazy', 'hub2325-broken']) router.removeRoute(name);
  vi.restoreAllMocks();
});

async function navigate(path: string): Promise<void> {
  await router.push(path).catch(() => undefined);
}

describe('hub#2325 · the side menu downloaded ahead of time', () => {
  it('downloads the screen behind a menu entry before anyone taps it', async () => {
    await navigate(HOME);

    await prefetchSectionViews(router, [LAZY]);

    expect(lazyLoader).toHaveBeenCalledTimes(1);
    await navigate(LAZY);
    expect(router.currentRoute.value.path).toBe(LAZY);
  });

  it('a download that failed opens the section on the FIRST tap, in a fresh document', async () => {
    await navigate(HOME);

    await prefetchSectionViews(router, [BROKEN]);
    await navigate(BROKEN);

    expect(assign).toHaveBeenCalledTimes(1);
    expect(assign).toHaveBeenCalledWith(new URL(BROKEN, window.location.href).href);
    expect(toastErrorSpy).not.toHaveBeenCalled();
  });
});

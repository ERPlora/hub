// @vitest-environment happy-dom
//
// hub#2312 — the regression, through the REAL router.
//
// A person with the hub open taps a section just as the network blinks (wifi hops to 4G, the
// router restarts). The section does not open and a toast says "check your connection and try
// again". They do, with the network back — and it fails again, every time, until the whole page
// is reloaded by hand.
//
// Why: per the HTML module map, a module URL that failed to fetch stays failed for the life of the
// DOCUMENT. The second tap re-runs the very same `import()`, which rejects without touching the
// network (measured in Chromium: 0 new requests; a document navigation fetches it fine). So the
// retry the toast invites has to be a document navigation to that section — and only when the
// person asks for that section again: the first failure keeps them on the screen they are on.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { toastErrorSpy, reportSpy } = vi.hoisted(() => ({
  toastErrorSpy: vi.fn(() => Promise.resolve()),
  reportSpy: vi.fn(),
}));

vi.mock('../lib/toast', () => ({
  toast: vi.fn(() => Promise.resolve()),
  toastSuccess: vi.fn(() => Promise.resolve()),
  toastError: toastErrorSpy,
  toastInfo: vi.fn(() => Promise.resolve()),
  bootActionFeedback: vi.fn(),
}));

vi.mock('../lib/error-report', () => ({
  reportClientError: reportSpy,
  installErrorReporting: vi.fn(),
}));

import { i18n } from '../i18n';
import { router } from './index';
import { VIEW_LOAD_FAILURE_ID } from './view-load-failure-notice';

/** Verbatim from the CI trace of hub#1518: the file behind the section never arrived. */
const CHUNK_ERROR = new TypeError(
  'Failed to fetch dynamically imported module: http://localhost:5173/src/views/SettingsPage.vue',
);

const HEALTHY = '/hub2312-healthy';
const BROKEN = '/hub2312-broken';
const OTHER_BROKEN = '/hub2312-other-broken';
const OFFLINE_BROKEN = '/hub2312-offline-broken';

let assign: ReturnType<typeof vi.fn>;
let reload: ReturnType<typeof vi.fn>;

beforeEach(() => {
  sessionStorage.clear();
  toastErrorSpy.mockClear();
  reportSpy.mockClear();
  assign = vi.fn();
  reload = vi.fn();
  vi.spyOn(window.location, 'assign').mockImplementation(assign as unknown as (url: string | URL) => void);
  vi.spyOn(window.location, 'reload').mockImplementation(reload as unknown as () => void);

  router.addRoute({ path: HEALTHY, name: 'hub2312-healthy', component: { render: () => null } });
  // Each broken section fails EVERY time, exactly like the browser's poisoned module map does.
  for (const path of [BROKEN, OTHER_BROKEN, OFFLINE_BROKEN]) {
    router.addRoute({ path, name: path.slice(1), component: () => Promise.reject(CHUNK_ERROR) });
  }
});

afterEach(() => {
  for (const name of ['hub2312-healthy', 'hub2312-broken', 'hub2312-other-broken', 'hub2312-offline-broken']) {
    router.removeRoute(name);
  }
  vi.restoreAllMocks();
});

async function navigate(path: string): Promise<void> {
  await router.push(path).catch(() => undefined);
}

describe('hub#2312 · a section that failed with the app open', () => {
  it('opens on the retry the toast asks for, in a fresh document', async () => {
    await navigate(HEALTHY);

    // 1 · The blink: the section does not open, the person stays put and is told to try again.
    await navigate(BROKEN);
    expect(router.currentRoute.value.path).toBe(HEALTHY);
    expect(toastErrorSpy).toHaveBeenCalledWith(i18n.global.t('viewLoad.failedToast'));
    expect(assign).not.toHaveBeenCalled();

    // 2 · They try again with the network back. Before the fix this was the same toast, forever.
    toastErrorSpy.mockClear();
    await navigate(`${BROKEN}#data`);

    expect(assign).toHaveBeenCalledTimes(1);
    expect(assign).toHaveBeenCalledWith(router.resolve(`${BROKEN}#data`).href);
    // A plain reload would land back on the screen they came FROM, not the one they asked for.
    expect(reload).not.toHaveBeenCalled();
    expect(toastErrorSpy).not.toHaveBeenCalled();
    expect(document.getElementById(VIEW_LOAD_FAILURE_ID)).toBeNull();
    // Recovered, but not hidden.
    expect(reportSpy).toHaveBeenCalledWith(
      expect.objectContaining({ component: 'router', message: expect.stringContaining('router.onError[reopen]') }),
    );
  });

  it('a first failure of ANOTHER section never throws away the screen the person is on', async () => {
    await navigate(HEALTHY);

    await navigate(OTHER_BROKEN);

    expect(assign).not.toHaveBeenCalled();
    expect(reload).not.toHaveBeenCalled();
    expect(toastErrorSpy).toHaveBeenCalledTimes(1);
    expect(router.currentRoute.value.path).toBe(HEALTHY);
  });

  it('stays in the app while the device is offline: the browser error page has no way back', async () => {
    vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(false);
    await navigate(HEALTHY);

    await navigate(OFFLINE_BROKEN);
    await navigate(OFFLINE_BROKEN);

    expect(assign).not.toHaveBeenCalled();
    expect(toastErrorSpy).toHaveBeenCalledTimes(2);
    expect(router.currentRoute.value.path).toBe(HEALTHY);
  });
});

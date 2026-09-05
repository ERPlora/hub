// @vitest-environment happy-dom
//
// hub#1518 — the regression, through the REAL router, at the place where the screen went blank.
//
// What CI caught (run 33787767992, trace of the ImportPanel e2e): the runner's network blinked
// (`net::ERR_NETWORK_CHANGED`), the files behind `/settings` never arrived, and the router threw
// `TypeError: Failed to fetch dynamically imported module: …/SettingsPage.vue` on its very first
// navigation. `main.ts` mounts the app inside `router.isReady().then(...)`, so that rejection left
// the app UNMOUNTED: a white page, no message, no way back — and an e2e waiting 30 s for an input
// that could never exist.
//
// The contract this file pins down is the recovery ladder, wired into the router itself:
//   1. first navigation → reload the target once (a fresh document is the only thing that clears
//      the browser's memory of a module URL that failed);
//   2. if it fails AGAIN after that reload → a visible message, never a blank page;
//   3. navigating inside the app → no reload (the half-typed order survives), but say it out loud.
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

// The real one POSTs to the runtime; in happy-dom that is a dangling fetch aborted at teardown.
// Mocked here so the run stays clean AND so the report itself can be asserted: a navigation that
// dies without leaving a trace is a failure nobody would ever see.
vi.mock('../lib/error-report', () => ({
  reportClientError: reportSpy,
  installErrorReporting: vi.fn(),
}));

import { router } from './index';
import { VIEW_LOAD_FAILURE_ID } from './view-load-failure-notice';
import { VIEW_LOAD_RECOVERY_KEY } from './view-load-recovery';

/** Verbatim from the CI trace. */
const CHUNK_ERROR = new TypeError(
  'Failed to fetch dynamically imported module: http://localhost:5173/src/views/SettingsPage.vue',
);

const BROKEN = '/hub1518-broken';
const HEALTHY = '/hub1518-healthy';

let reload: ReturnType<typeof vi.fn>;

beforeEach(() => {
  sessionStorage.clear();
  toastErrorSpy.mockClear();
  reportSpy.mockClear();
  document.getElementById(VIEW_LOAD_FAILURE_ID)?.remove();
  reload = vi.fn();
  vi.spyOn(window.location, 'reload').mockImplementation(reload as unknown as () => void);

  // A screen whose file never arrives, and one that loads fine.
  router.addRoute({
    path: BROKEN,
    name: 'hub1518-broken',
    component: () => Promise.reject(CHUNK_ERROR),
  });
  router.addRoute({
    path: HEALTHY,
    name: 'hub1518-healthy',
    component: { render: () => null },
  });
});

afterEach(() => {
  router.removeRoute('hub1518-broken');
  router.removeRoute('hub1518-healthy');
  vi.restoreAllMocks();
});

/** Push and swallow the rejection: a failed navigation rejects, and that is not what we assert on. */
async function navigate(path: string): Promise<void> {
  await router.push(path).catch(() => undefined);
}

describe('hub#1518 · a view whose file never arrives', () => {
  it('reloads once on the first navigation, and shows a message if that was not enough', async () => {
    // 1 · The first navigation of the document — exactly the CI case: nothing is mounted yet, so
    //     an abort here is a permanently blank page.
    await navigate(BROKEN);

    // A DOCUMENT reload — never `location.assign(to.fullPath)`. On the first navigation the tab is
    // already AT `to` (the router replays `window.location`), and assigning the URL a document
    // already has, differing at most in its fragment, is a fragment navigation per the HTML spec:
    // nothing reloads. The e2e that found this lands on `/settings#data` — measured in Chromium,
    // `assign('/settings#data')` = 1 document load (still blank), `reload()` = 2.
    expect(reload).toHaveBeenCalledTimes(1);
    expect(sessionStorage.getItem(VIEW_LOAD_RECOVERY_KEY)).toBe(BROKEN);
    expect(document.getElementById(VIEW_LOAD_FAILURE_ID)).toBeNull();
    // Recovered, but not hidden: the reload is reported so a hub that keeps doing this is visible.
    expect(reportSpy).toHaveBeenCalledWith(
      expect.objectContaining({ component: 'router', message: expect.stringContaining('router.onError[reload]') }),
    );

    // 2 · The reload happened and the very same screen failed again: give up reloading (a reload
    //     loop is worse) and SAY it. What must never happen is the white page.
    reload.mockClear();
    await navigate(BROKEN);

    expect(reload).not.toHaveBeenCalled();
    const notice = document.getElementById(VIEW_LOAD_FAILURE_ID);
    expect(notice).not.toBeNull();
    expect(notice?.textContent?.trim()).not.toBe('');
  });

  it('does not reload when the app is already open — it tells the person instead', async () => {
    // The mark a recovery reload leaves behind: landing anywhere must forget it, or the NEXT blink
    // on this screen finds the mark, skips the reload and goes straight to the wall of text.
    sessionStorage.setItem(VIEW_LOAD_RECOVERY_KEY, HEALTHY);
    await navigate(HEALTHY);
    expect(router.currentRoute.value.path).toBe(HEALTHY);
    // A landed navigation forgets the mark, so a later hiccup can still recover by reloading.
    expect(sessionStorage.getItem(VIEW_LOAD_RECOVERY_KEY)).toBeNull();

    await navigate(BROKEN);

    expect(reload).not.toHaveBeenCalled();
    expect(document.getElementById(VIEW_LOAD_FAILURE_ID)).toBeNull();
    expect(toastErrorSpy).toHaveBeenCalledTimes(1);
    // The person stays where they were, with whatever they had half-typed.
    expect(router.currentRoute.value.path).toBe(HEALTHY);
  });

  it('stays as loud as before for an error that is NOT a missing file', async () => {
    // Registering an error listener at all turns OFF vue-router's own `console.error`, so a bug
    // inside a view would go from noisy to silent the day this recovery landed. It must not: a
    // real bug is not recovered from, it is reported — and never mistaken for a network blink.
    const bug = new Error('ReferenceError: cart is not defined');
    router.addRoute({ path: '/hub1518-bug', name: 'hub1518-bug', component: () => Promise.reject(bug) });
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});

    await navigate('/hub1518-bug');

    expect(consoleError).toHaveBeenCalledWith(bug);
    expect(reload).not.toHaveBeenCalled();
    expect(sessionStorage.getItem(VIEW_LOAD_RECOVERY_KEY)).toBeNull();
    expect(toastErrorSpy).not.toHaveBeenCalled();
    router.removeRoute('hub1518-bug');
  });
});

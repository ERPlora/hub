// @vitest-environment happy-dom
//
// hub#1590 — the LAST silent corner of `router.onError`, through the REAL router.
//
// hub#1518 gave a screen whose FILE never arrived a toast; hub#1524 gave a screen whose own CODE
// throws the full-screen notice, but only on the FIRST navigation, where nothing is mounted and
// the alternative is a white page. With the app ALREADY open the same code failure fell through
// to a bare `console.error`: the person taps a section of the menu, the screen does not change and
// nothing is said. The button looks dead.
//
// The contract pinned here:
//   1. app open + a bug in the view → a short toast, so the failure is never mute;
//   2. in its OWN words — the connection copy is a lie here, and one that sends someone to reboot
//      a router that is working fine (the two causes must never share a string);
//   3. still no wall of text and still no reload: the person keeps the screen — and whatever was
//      half-typed on it — exactly where it was;
//   4. a genuine network failure keeps saying "check your connection", unchanged.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { toastErrorSpy, reportSpy } = vi.hoisted(() => ({
  // Typed with its argument on purpose: an untyped `vi.fn()` gives `mock.calls` an empty tuple,
  // and every assertion below is about WHICH string was said, not merely that something was.
  toastErrorSpy: vi.fn((_message: string) => Promise.resolve()),
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
vi.mock('../lib/error-report', () => ({
  reportClientError: reportSpy,
  installErrorReporting: vi.fn(),
}));

import { i18n } from '../i18n';
import { router } from './index';
import { VIEW_LOAD_FAILURE_ID } from './view-load-failure-notice';
import { VIEW_LOAD_RECOVERY_KEY } from './view-load-recovery';

/** A bug inside the view itself — NOT the browser failing to fetch it. */
const BUG = new Error('TypeError: Cannot read properties of undefined (reading "total")');
/** The other cause: the file behind the screen never arrived (hub#1518's wording, verbatim). */
const CHUNK = new Error('Failed to fetch dynamically imported module: /assets/OrdersPage-a1b2.js');

const BUGGY = '/hub1590-buggy';
const OFFLINE = '/hub1590-offline';
const OPEN = '/hub1590-open';

let reload: ReturnType<typeof vi.fn>;
let consoleError: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  sessionStorage.clear();
  toastErrorSpy.mockClear();
  reportSpy.mockClear();
  document.getElementById(VIEW_LOAD_FAILURE_ID)?.remove();
  reload = vi.fn();
  vi.spyOn(window.location, 'reload').mockImplementation(reload as unknown as () => void);
  // The listener re-raises it on purpose (hub#1518): silencing it here keeps the run readable.
  consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});

  router.addRoute({ path: BUGGY, name: 'hub1590-buggy', component: () => Promise.reject(BUG) });
  router.addRoute({ path: OFFLINE, name: 'hub1590-offline', component: () => Promise.reject(CHUNK) });
  router.addRoute({ path: OPEN, name: 'hub1590-open', component: { render: () => null } });
});

afterEach(() => {
  router.removeRoute('hub1590-buggy');
  router.removeRoute('hub1590-offline');
  router.removeRoute('hub1590-open');
  vi.restoreAllMocks();
});

/** Push and swallow the rejection: a failed navigation rejects, and that is not the assertion. */
async function navigate(path: string): Promise<void> {
  await router.push(path).catch(() => undefined);
}

/** Puts the shell in the state the issue describes: a hub that is already open and being used. */
async function withAppOpen(): Promise<void> {
  await navigate(OPEN);
  expect(router.currentRoute.value.path).toBe(OPEN);
  toastErrorSpy.mockClear();
  reportSpy.mockClear();
}

describe('hub#1590 · a section whose code throws while the hub is already open', () => {
  it('says it out loud instead of looking like a dead button', async () => {
    await withAppOpen();

    await navigate(BUGGY);

    expect(toastErrorSpy).toHaveBeenCalledTimes(1);
    const message = toastErrorSpy.mock.calls[0][0];
    expect(message).toBe(i18n.global.t('viewLoad.brokenToast'));
    // From the catalogue, never hardcoded, and never the raw key leaking through (ADR-0055).
    expect(message).not.toContain('viewLoad.');
    expect(message.trim()).not.toBe('');
  });

  it('never blames the connection for a bug in our own code', async () => {
    await withAppOpen();

    await navigate(BUGGY);

    // The whole reason this branch needed a string of its own: telling someone their connection
    // dropped when it did not sends them off to restart a router that is working fine.
    // Asserted BEFORE the comparison: with no toast at all, `calls[0]` is undefined and every
    // "is not the connection copy" below would pass without a single thing having been said.
    expect(toastErrorSpy).toHaveBeenCalledTimes(1);
    const message = toastErrorSpy.mock.calls[0][0];
    expect(message).not.toBe(i18n.global.t('viewLoad.failedToast'));
    for (const locale of ['en', 'es'] as const) {
      expect(i18n.global.t('viewLoad.brokenToast', {}, { locale })).not.toBe(
        i18n.global.t('viewLoad.failedToast', {}, { locale }),
      );
    }
  });

  it('keeps the screen, the half-typed order and the scroll exactly where they were', async () => {
    await withAppOpen();

    await navigate(BUGGY);

    // A toast, never the wall of text: covering a live till loses sight of the order being taken.
    expect(document.getElementById(VIEW_LOAD_FAILURE_ID)).toBeNull();
    expect(router.currentRoute.value.path).toBe(OPEN);
    // A code failure reloads into the identical code, so retrying it on its own is a boot loop.
    expect(reload).not.toHaveBeenCalled();
    expect(sessionStorage.getItem(VIEW_LOAD_RECOVERY_KEY)).toBeNull();
  });

  it('stays as loud in the console and in the report as hub#1518 left it', async () => {
    await withAppOpen();

    await navigate(BUGGY);

    // Registering ANY error listener switches off vue-router's own `console.error`, so adding the
    // toast must not become an excuse to swallow the bug that caused it.
    expect(consoleError).toHaveBeenCalledWith(BUG);
    expect(reportSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        component: 'router',
        message: expect.stringContaining('router.onError[ignored]'),
      }),
    );
  });

  it('leaves the genuine network failure saying "check your connection"', async () => {
    await withAppOpen();

    await navigate(OFFLINE);

    // hub#1518's branch, untouched: here the connection really is the cause, and its copy is the
    // useful one. If this ever swapped to the code wording the two causes would be indistinct.
    expect(toastErrorSpy).toHaveBeenCalledTimes(1);
    expect(toastErrorSpy.mock.calls[0][0]).toBe(i18n.global.t('viewLoad.failedToast'));
    expect(reportSpy).toHaveBeenCalledWith(
      expect.objectContaining({ message: expect.stringContaining('router.onError[notify]') }),
    );
  });
});

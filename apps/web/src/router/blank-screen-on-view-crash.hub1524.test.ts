// @vitest-environment happy-dom
//
// hub#1524 — the OTHER half of the blank page, through the REAL router.
//
// hub#1518 taught the shell to survive a screen whose FILE never arrived (the till hops wifi→4G,
// a chunk went stale after a deploy). It deliberately left the opposite cause alone: a screen
// whose own code throws while it is being evaluated. That one is not a fetch failure, so the
// ladder classifies it `ignored` and only writes to the console — and on the FIRST navigation
// `main.ts` mounts inside `router.isReady().then(...)`, so nothing ever mounts. The person is left
// looking at a white page with no message and no way out but closing the app.
//
// The contract pinned here:
//   1. first navigation + a bug in the view → the SAME notice, with its OWN words (saying "the
//      connection dropped" would send someone to reboot a router that is working fine);
//   2. nothing reloads on its own — a code failure reloads into itself, which is a boot loop;
//      the only retry is the one the person presses;
//   3. app already open → it keeps the screen it is on; no wall of text over a half-typed order.
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

const BUGGY = '/hub1524-buggy';
const HEALTHY = '/hub1524-healthy';

let reload: ReturnType<typeof vi.fn>;
let consoleError: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  sessionStorage.clear();
  toastErrorSpy.mockClear();
  reportSpy.mockClear();
  document.getElementById(VIEW_LOAD_FAILURE_ID)?.remove();
  reload = vi.fn();
  vi.spyOn(window.location, 'reload').mockImplementation(reload as unknown as () => void);
  // The listener re-raises it on purpose (hub#1518): silencing it here keeps the run readable
  // while still letting the assertions check it was raised.
  consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});

  router.addRoute({ path: BUGGY, name: 'hub1524-buggy', component: () => Promise.reject(BUG) });
  router.addRoute({ path: HEALTHY, name: 'hub1524-healthy', component: { render: () => null } });
});

afterEach(() => {
  router.removeRoute('hub1524-buggy');
  router.removeRoute('hub1524-healthy');
  vi.restoreAllMocks();
});

/** Push and swallow the rejection: a failed navigation rejects, and that is not the assertion. */
async function navigate(path: string): Promise<void> {
  await router.push(path).catch(() => undefined);
}

describe('hub#1524 · a screen whose own code throws on boot', () => {
  it('says so instead of leaving the page blank, in its own words', async () => {
    await navigate(BUGGY);

    const notice = document.getElementById(VIEW_LOAD_FAILURE_ID);
    expect(notice).not.toBeNull();
    expect(notice?.getAttribute('role')).toBe('alert');
    // Its OWN copy (ADR-0055: from the catalogue, never hardcoded). Blaming the connection here
    // would be a lie — and one that sends the person to restart a router that is working.
    expect(notice?.textContent).toContain(i18n.global.t('viewLoad.brokenTitle'));
    expect(notice?.textContent).toContain(i18n.global.t('viewLoad.brokenBody'));
    expect(notice?.textContent).not.toContain(i18n.global.t('viewLoad.blockedBody'));
    expect(notice?.textContent).not.toContain('viewLoad.');
  });

  it('never reloads on its own — a broken build would boot-loop the till', async () => {
    await navigate(BUGGY);

    // No rung 1 for this cause: the document would come back to the very same broken code.
    expect(reload).not.toHaveBeenCalled();
    // And no mark either: the recovery ladder is for fetch failures, and a leftover mark here
    // would rob the NEXT genuine network blink on this path of its one reload.
    expect(sessionStorage.getItem(VIEW_LOAD_RECOVERY_KEY)).toBeNull();

    // The only retry that exists is the one the person presses.
    const button = document.querySelector<HTMLButtonElement>(`#${VIEW_LOAD_FAILURE_ID} button`);
    expect(button?.textContent).toBe(i18n.global.t('viewLoad.brokenAction'));
    button?.click();
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('stays exactly as loud as hub#1518 left it', async () => {
    await navigate(BUGGY);

    // Registering ANY error listener switches off vue-router's own `console.error`, so painting
    // the notice must not become an excuse to swallow the bug that caused it.
    expect(consoleError).toHaveBeenCalledWith(BUG);
    expect(reportSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        component: 'router',
        message: expect.stringContaining('router.onError[ignored]'),
      }),
    );
  });

  it('does not cover the screen of an app that is already open', async () => {
    await navigate(HEALTHY);
    expect(router.currentRoute.value.path).toBe(HEALTHY);

    await navigate(BUGGY);

    // Nothing is blank here: the person keeps the screen — and the half-typed order — they had.
    // A full-screen wall of text over a live till would be a regression, not a fix.
    expect(document.getElementById(VIEW_LOAD_FAILURE_ID)).toBeNull();
    expect(router.currentRoute.value.path).toBe(HEALTHY);
    expect(reload).not.toHaveBeenCalled();
    expect(consoleError).toHaveBeenCalledWith(BUG);
  });
});

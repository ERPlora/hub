// @vitest-environment happy-dom
// The rule that tells «the network is gone» apart from «this broke» (hub#1743).
//
// Every screen of the shell talks to the runtime over `fetch`, so every screen can fail for two
// reasons that look identical once the error reaches a `catch`: the hub answered something bad, or
// nothing answered at all. Painting the first sentence over the second is what hub#1743 reported —
// a module screen telling the owner to check whether an app is still installed while the actual
// fault was a dead router.
//
// The fact that separates them is in the failure itself: a `fetch` that never reached anybody
// rejects with a `TypeError` whose wording every engine spells differently, and the browser also
// keeps a flag of its own. Both are read here, in one place, so no screen has to invent the rule
// again (the same shape `isViewLoadError` uses in `router/view-load-recovery.ts`).
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { isNetworkFailure, isOffline, isOfflineError, isOnline } from './offline';

function goOffline(): void {
  window.dispatchEvent(new Event('offline'));
}

function goOnline(): void {
  window.dispatchEvent(new Event('online'));
}

beforeEach(() => goOnline());
afterEach(() => goOnline());

describe('isNetworkFailure — what a fetch that reached nobody looks like', () => {
  // The wording is engine-specific and there is no code to branch on, so the list IS the contract.
  it.each([
    ['Chromium', new TypeError('Failed to fetch')],
    ['Firefox', new TypeError('NetworkError when attempting to fetch resource.')],
    ['Safari', new TypeError('Load failed')],
    ['iOS Safari', new TypeError('The network connection was lost.')],
  ])('recognises %s', (_engine, error) => {
    expect(isNetworkFailure(error)).toBe(true);
  });

  it.each([
    // What the shell itself throws when the hub DID answer: these keep their own sentence.
    ['a runtime status line', new Error('navigation → 500')],
    ['a module fault', new Error('module manifest is not readable')],
    ['a business code', Object.assign(new Error('cloud: cloud_unreachable'), { code: 'x' })],
    ['nothing at all', undefined],
    ['a bare string', 'Failed to fetch'],
  ])('does not claim the network for %s', (_case, error) => {
    expect(isNetworkFailure(error)).toBe(false);
  });

  // 🔴 The other half of the same defect, in reverse. A dynamic `import()` words a dead network and
  // a plain 404 EXACTLY the same, and Chromium's wording even contains «failed to fetch». In this
  // shell the 404 half is not an edge case: `ModuleView` only reaches the bundle after
  // `/api/navigation` already answered, so the hub is provably reachable, and a module that was
  // uninstalled (or a url left over from the version before an update, hub#935) 404s there every
  // time. Claiming the network for it prints «no internet connection» over the one fault whose own
  // sentence — «check that the module is still installed and active» — hub#1743 exists to protect.
  it.each([
    ['Chromium', new TypeError('Failed to fetch dynamically imported module: /modules/sales/x.js')],
    ['Firefox', new TypeError('error loading dynamically imported module: /modules/sales/x.js')],
    ['Safari', new TypeError('Importing a module script failed.')],
    ['Vite preload', new Error('Unable to preload CSS for /assets/OrdersPage.css')],
  ])('🔴 does not claim the network for a script that did not load (%s)', (_engine, error) => {
    expect(isNetworkFailure(error)).toBe(false);
  });
});

describe('isOnline — the browser flag, live', () => {
  it('follows the window events instead of being read once at boot', () => {
    expect(isOnline.value).toBe(true);

    goOffline();
    expect(isOnline.value, 'the shell never noticed the network go away').toBe(false);
    expect(isOffline.value).toBe(true);

    goOnline();
    expect(isOnline.value, 'the shell never noticed the network come back').toBe(true);
    expect(isOffline.value).toBe(false);
  });
});

describe('isOfflineError — the question a screen actually asks', () => {
  it('says yes when nothing reached the hub, even with the flag still up', () => {
    // `navigator.onLine === true` is not a promise of connectivity: it is true on a laptop attached
    // to a router with no uplink, which is the commonest way a shop loses the internet. The failed
    // fetch is the harder fact of the two, so it decides on its own.
    expect(isOnline.value).toBe(true);
    expect(isOfflineError(new TypeError('Failed to fetch'))).toBe(true);
  });

  it('says yes while the browser reports no network, whatever the failure was', () => {
    // The other direction: with the network down, any failure is at best unexplainable, and the
    // missing connection is the only thing anybody can act on.
    goOffline();
    expect(isOfflineError(new Error('navigation → 500'))).toBe(true);
  });

  it('🔴 says NO when the hub answered and there is a network', () => {
    // The half that keeps this from becoming «always blame the wifi». Without it the fix would
    // simply swap one wrong sentence for another.
    expect(isOfflineError(new Error('navigation → 500'))).toBe(false);
    expect(isOfflineError(new Error('module manifest is not readable'))).toBe(false);
  });

  it('🔴 says NO for a bundle that 404s, which is what an uninstalled module looks like', () => {
    // The 404 wears the wording of an outage. With a network up, it is not one — and this is the
    // exact fault the sentence hub#1743 protects («check that the module is still installed»).
    expect(
      isOfflineError(new TypeError('Failed to fetch dynamically imported module: /modules/x.js')),
    ).toBe(false);
  });

  it('…and says YES for that same failure once the browser reports no network', () => {
    // Ambiguous on its own, decided by the flag: with the network down, a script that did not load
    // is the outage, and the person needs to hear about the connection.
    goOffline();
    expect(
      isOfflineError(new TypeError('Failed to fetch dynamically imported module: /modules/x.js')),
    ).toBe(true);
  });
});

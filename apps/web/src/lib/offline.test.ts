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
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  isNetworkFailure,
  isOffline,
  isOfflineError,
  isOnline,
  makeHubProbe,
  offlineCause,
  reportNetworkFailure,
  startHubWatch,
} from './offline';

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

// hub#2085 — the half hub#1743 left open, and the commonest shape of the outage: the router is up,
// so `navigator.onLine` stays `true`, but nothing behind it answers. Until this block the band only
// listened to the flag, so a till on a router with no uplink looked perfectly healthy right up to
// the moment a sale would not go through. The shell now ASKS the hub, lightly, and believes the
// answer over the flag.
describe('hub#2085 — a hub that does not answer is an outage, whatever the browser flag says', () => {
  let stop: (() => void) | undefined;
  let visibility: DocumentVisibilityState = 'visible';

  beforeEach(() => {
    vi.useFakeTimers();
    visibility = 'visible';
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => visibility,
    });
  });

  afterEach(() => {
    stop?.();
    stop = undefined;
    vi.useRealTimers();
  });

  const unreachable = () => vi.fn<() => Promise<void>>().mockRejectedValue(new TypeError('Failed to fetch'));
  const answering = () => vi.fn<() => Promise<void>>().mockResolvedValue(undefined);

  async function flush(): Promise<void> {
    // Let the probe's promise settle without moving the clock.
    await vi.advanceTimersByTimeAsync(0);
  }

  it('one missed answer is not an outage; two in a row are', async () => {
    const probe = unreachable();
    stop = startHubWatch({ probe, intervalMs: 30_000, retryMs: 5_000 });
    await flush();

    expect(probe).toHaveBeenCalledTimes(1);
    // A single miss can be the hub restarting for a deploy; the band must not flash on that.
    expect(isOffline.value, 'one miss raised the band').toBe(false);

    await vi.advanceTimersByTimeAsync(5_000);
    expect(probe).toHaveBeenCalledTimes(2);
    expect(isOffline.value, 'two misses in a row and the till still looked healthy').toBe(true);
    expect(isOnline.value).toBe(false);
    expect(offlineCause.value).toBe('hub');
  });

  it('comes back on the first answer, and says nothing more', async () => {
    const probe = unreachable();
    stop = startHubWatch({ probe, intervalMs: 30_000, retryMs: 5_000 });
    await flush();
    await vi.advanceTimersByTimeAsync(5_000);
    expect(isOffline.value).toBe(true);

    probe.mockResolvedValue(undefined);
    await vi.advanceTimersByTimeAsync(5_000);
    expect(isOffline.value, 'the band outlived the outage').toBe(false);
    expect(offlineCause.value).toBeNull();
  });

  it('asks every 30 s while everything is fine, and not more often', async () => {
    const probe = answering();
    stop = startHubWatch({ probe, intervalMs: 30_000, retryMs: 5_000 });
    await flush();
    expect(probe).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(29_000);
    expect(probe).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1_000);
    expect(probe).toHaveBeenCalledTimes(2);
  });

  it('🔴 leaves a hidden tab alone, and asks the moment it is looked at again', async () => {
    // A till that is minimised is not a till anybody is reading; probing it is traffic for nobody.
    // The moment it is brought back the person IS reading it, and the first thing they need to know
    // is whether it still works.
    const probe = answering();
    stop = startHubWatch({ probe, intervalMs: 30_000, retryMs: 5_000 });
    await flush();
    expect(probe).toHaveBeenCalledTimes(1);

    visibility = 'hidden';
    document.dispatchEvent(new Event('visibilitychange'));
    await vi.advanceTimersByTimeAsync(90_000);
    expect(probe, 'the shell kept polling a tab nobody was looking at').toHaveBeenCalledTimes(1);

    visibility = 'visible';
    document.dispatchEvent(new Event('visibilitychange'));
    await flush();
    expect(probe).toHaveBeenCalledTimes(2);
  });

  it('a screen that just failed to reach the hub makes it ask at once', async () => {
    // `ModuleView` already knows when a load reached nobody (hub#1743). Waiting up to 30 s to
    // confirm what a failure just proved would leave the band behind the screen that failed.
    const probe = answering();
    stop = startHubWatch({ probe, intervalMs: 30_000, retryMs: 5_000 });
    await flush();
    expect(probe).toHaveBeenCalledTimes(1);

    reportNetworkFailure();
    await flush();
    expect(probe).toHaveBeenCalledTimes(2);
  });

  it('🔴 the browser flag keeps the first word: with no network at all, the cause is the network', async () => {
    // Two facts, one band. When the browser itself says there is no network, that is the sentence
    // the person can act on (the wifi), whatever the hub did or did not answer.
    const probe = unreachable();
    stop = startHubWatch({ probe, intervalMs: 30_000, retryMs: 5_000 });
    await flush();
    await vi.advanceTimersByTimeAsync(5_000);
    expect(offlineCause.value).toBe('hub');

    goOffline();
    expect(offlineCause.value).toBe('network');
    goOnline();
    expect(offlineCause.value).toBe('hub');
  });

  it('stopping the watch stops the asking and forgets the verdict', async () => {
    const probe = unreachable();
    const stopNow = startHubWatch({ probe, intervalMs: 30_000, retryMs: 5_000 });
    await flush();
    await vi.advanceTimersByTimeAsync(5_000);
    expect(isOffline.value).toBe(true);

    stopNow();
    expect(isOffline.value).toBe(false);
    await vi.advanceTimersByTimeAsync(120_000);
    expect(probe).toHaveBeenCalledTimes(2);
  });
  it('🔴 after an outage ends, one miss is one miss again, not a new outage', async () => {
    // The two-misses rule is about EVERY outage, not only the first: with the count never reset,
    // every hub restart after the first cut would flash the band the rule exists to keep down.
    const probe = unreachable();
    stop = startHubWatch({ probe, intervalMs: 30_000, retryMs: 5_000 });
    await flush();
    await vi.advanceTimersByTimeAsync(5_000);
    expect(isOffline.value).toBe(true);

    probe.mockResolvedValue(undefined);
    await vi.advanceTimersByTimeAsync(5_000);
    expect(isOffline.value).toBe(false);

    probe.mockRejectedValue(new TypeError('Failed to fetch'));
    await vi.advanceTimersByTimeAsync(30_000);
    expect(probe).toHaveBeenCalledTimes(4);
    expect(isOffline.value, 'a single miss after a recovery raised the band').toBe(false);
    await vi.advanceTimersByTimeAsync(5_000);
    expect(isOffline.value).toBe(true);
  });

  it('🔴 the browser saying «online» again makes it ask at once: the flag is not a promise', async () => {
    const probe = answering();
    stop = startHubWatch({ probe, intervalMs: 30_000, retryMs: 5_000 });
    await flush();
    expect(probe).toHaveBeenCalledTimes(1);

    goOffline();
    goOnline();
    await flush();
    expect(probe, 'the flag came back and nobody asked the hub').toHaveBeenCalledTimes(2);
  });
});

describe('hub#2085 — what «the hub answered» means for the probe', () => {
  // Reachability is a question about the NETWORK, not about the hub's health: a 500 is an answer,
  // and a hub that answers 500 is one the person can still be told about by the screen that got it.
  // Only «nothing came back» — the rejection every engine spells differently, or a request that
  // never finished — counts as not reaching it.
  it('any status is an answer, a 500 included', async () => {
    const fetchImpl = vi.fn(async () => new Response('boom', { status: 500 }));
    const probe = makeHubProbe('http://hub.test', { fetchImpl, timeoutMs: 10_000 });
    await expect(probe()).resolves.toBeUndefined();
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('http://hub.test/healthz');
    // No cache: a cached «ok» from before the router died is exactly the lie being fought here.
    expect(init.cache).toBe('no-store');
  });

  it('a fetch that reached nobody is not an answer', async () => {
    const fetchImpl = vi.fn(async () => {
      throw new TypeError('Failed to fetch');
    });
    const probe = makeHubProbe('http://hub.test', { fetchImpl, timeoutMs: 10_000 });
    await expect(probe()).rejects.toBeInstanceOf(TypeError);
  });

  it('🔴 a request that never finishes is not an answer either', async () => {
    // With a router that has no uplink the SYN goes nowhere: the browser's own timeout is over a
    // minute, and a band that takes a minute to rise is a band that rises after the cashier gave up.
    vi.useFakeTimers();
    try {
      const fetchImpl = vi.fn(
        (_url: string, init?: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
          }),
      );
      const probe = makeHubProbe('http://hub.test', {
        fetchImpl: fetchImpl as unknown as typeof fetch,
        timeoutMs: 10_000,
      });
      const verdict = probe();
      const outcome = verdict.then(
        () => 'answered',
        () => 'silent',
      );
      await vi.advanceTimersByTimeAsync(10_000);
      await expect(outcome).resolves.toBe('silent');
    } finally {
      vi.useRealTimers();
    }
  });
});

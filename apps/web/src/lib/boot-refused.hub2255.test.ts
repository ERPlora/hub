// @vitest-environment happy-dom
// hub#2255 — when the hub REFUSES at boot, the app must not send the person to check their wifi.
//
// On 27/09 the edge in front of the hubs answered every request with `403` and an empty body for
// hours (an address ban, infra#334), while the device had a perfectly good connection. The boot
// check of hub#2143 read any failure the same way and painted «ERPlora is not answering. Check that
// this device is connected to the internet», with a retry button that could never help.
//
// Two different facts, two different notices:
// - no answer at all (the request failed or timed out) → «cannot connect», check the connection;
// - an answer that is not the context (403, 5xx…) → «your business is not available right now»,
//   nothing to check on this device, and the app keeps trying on its own.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { BOOT_CONTEXT_TIMEOUT_MS, bootContextOutcome } from './runtime';
import { BOOT_REFUSED_RETRY_MS, bootUntilReachable, type BootOutcome } from './boot';

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('the boot check tells a refusal from no answer (hub#2255)', () => {
  for (const status of [403, 500, 502, 503]) {
    it(`an empty ${status} is a refusal, not a lost connection`, async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn(async () => new Response('', { status })),
      );

      expect(await bootContextOutcome()).toBe('refused');
    });
  }

  it('a request that fails before any answer is «unreachable»', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('Failed to fetch');
      }),
    );

    expect(await bootContextOutcome()).toBe('unreachable');
  });

  it('a request that never answers is «unreachable» once the wait runs out', async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      'fetch',
      vi.fn(
        (_url: string, init?: RequestInit) =>
          new Promise((_resolve, reject) => {
            init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
          }),
      ),
    );

    const outcome = bootContextOutcome();
    await vi.advanceTimersByTimeAsync(BOOT_CONTEXT_TIMEOUT_MS);

    expect(await outcome).toBe('unreachable');
  });

  it('an answer cut by the bounded wait while its body was being read is «unreachable»', async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url: string, init?: RequestInit) => ({
        ok: true,
        status: 200,
        // The headers came, the body never does: only the abort ends the read, as in a browser.
        json: () =>
          new Promise((_resolve, reject) => {
            init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
          }),
      })),
    );

    const outcome = bootContextOutcome();
    await vi.advanceTimersByTimeAsync(BOOT_CONTEXT_TIMEOUT_MS);

    expect(await outcome).toBe('unreachable');
  });

  it('an OK page that is not the context (a proxy answering HTML) is a refusal too', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('<html>blocked</html>', { status: 200 })),
    );

    expect(await bootContextOutcome()).toBe('refused');
  });

  it('the context answered is «answered»', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ hub_id: 'hub-1', user: null }), { status: 200 })),
    );

    expect(await bootContextOutcome()).toBe('answered');
  });
});

describe('a refusal at boot is retried on its own (hub#2255)', () => {
  function steps(answers: BootOutcome[]) {
    const failures: string[] = [];
    let retry: (() => void) | null = null;
    return {
      failures,
      retry: () => retry?.(),
      loadContext: vi.fn(async () => answers.shift() ?? 'unreachable'),
      showUnreachable: vi.fn((r: () => void, failure: string) => {
        failures.push(failure);
        retry = r;
      }),
      showProgress: vi.fn(),
    };
  }

  beforeEach(() => {
    vi.useFakeTimers();
  });

  it('the notice is told WHY: refused or unreachable', async () => {
    const s = steps(['refused', 'unreachable']);
    void bootUntilReachable(s);
    await vi.advanceTimersByTimeAsync(0);
    s.retry();
    await vi.advanceTimersByTimeAsync(0);

    expect(s.failures).toEqual(['refused', 'unreachable']);
  });

  it('asks again by itself after a while, and goes on once the hub lets it in', async () => {
    const s = steps(['refused', 'answered']);
    let done = false;
    void bootUntilReachable(s).then(() => (done = true));
    await vi.advanceTimersByTimeAsync(0);
    expect(s.loadContext).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(BOOT_REFUSED_RETRY_MS - 1);
    expect(s.loadContext).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(1);
    expect(s.showProgress).toHaveBeenCalledTimes(1);
    expect(s.loadContext).toHaveBeenCalledTimes(2);
    expect(done).toBe(true);
  });

  it('a press of «try again» replaces the automatic retry, it does not add a second one', async () => {
    const s = steps(['refused', 'refused', 'refused']);
    void bootUntilReachable(s);
    await vi.advanceTimersByTimeAsync(0);

    s.retry();
    await vi.advanceTimersByTimeAsync(0);
    expect(s.loadContext).toHaveBeenCalledTimes(2);

    // The timer of the FIRST notice must be gone: only the second notice's timer is left.
    await vi.advanceTimersByTimeAsync(BOOT_REFUSED_RETRY_MS);
    expect(s.loadContext).toHaveBeenCalledTimes(3);
  });

  it('pressing «try again» twice on the same notice asks once', async () => {
    const s = steps(['unreachable', 'unreachable']);
    void bootUntilReachable(s);
    await vi.advanceTimersByTimeAsync(0);

    s.retry();
    s.retry();
    await vi.advanceTimersByTimeAsync(0);

    expect(s.loadContext).toHaveBeenCalledTimes(2);
  });

  it('a lost connection is not retried behind the person’s back (hub#2143 keeps its one action)', async () => {
    const s = steps(['unreachable']);
    void bootUntilReachable(s);
    await vi.advanceTimersByTimeAsync(BOOT_REFUSED_RETRY_MS * 3);

    expect(s.loadContext).toHaveBeenCalledTimes(1);
  });

  it('waits long enough not to hammer a hub that refuses, short enough to notice it is back', () => {
    expect(BOOT_REFUSED_RETRY_MS).toBeGreaterThanOrEqual(15_000);
    expect(BOOT_REFUSED_RETRY_MS).toBeLessThanOrEqual(60_000);
  });
});

// @vitest-environment happy-dom
// hub#2143 — when the hub does not answer at boot, the person is told so and can try again.
//
// hub#2073 put a progress indicator in the served document while `main.ts` waits for
// `GET /api/hub/context` before mounting. That wait had no end: a hub that never answers (a request
// lost behind a router with no uplink, a proxy that holds the connection) kept the spinner turning
// for ever, with no word and no way out. And when the answer was an error, the shell mounted as if
// nothing had happened, with no hub id, no PIN users and no settings behind it.
//
// The answer is the one POS apps give at launch (Square, Toast, Lightspeed): a bounded wait, then
// «we cannot reach your business» with ONE action, try again.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { BOOT_CONTEXT_TIMEOUT_MS, bootHubContext } from './runtime';
import { bootUntilReachable } from './boot';

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('the boot context has a bounded wait (hub#2143)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  it('gives up on a hub that never answers, and aborts the request', async () => {
    let signal: AbortSignal | undefined;
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string, init?: RequestInit) => {
        signal = init?.signal ?? undefined;
        // Never settles on its own — only the abort can end it, as a real fetch does.
        return new Promise((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
        });
      }),
    );

    let settled: unknown = 'pending';
    void bootHubContext().then((ctx) => (settled = ctx));

    await vi.advanceTimersByTimeAsync(BOOT_CONTEXT_TIMEOUT_MS - 1);
    expect(settled).toBe('pending');

    await vi.advanceTimersByTimeAsync(1);
    expect(settled).toBeNull();
    expect(signal?.aborted).toBe(true);
  });

  it('is long enough for a hub that is waking up, not a flash', () => {
    expect(BOOT_CONTEXT_TIMEOUT_MS).toBeGreaterThanOrEqual(8_000);
    expect(BOOT_CONTEXT_TIMEOUT_MS).toBeLessThanOrEqual(20_000);
  });
});

describe('the boot waits for the hub, and offers a retry when it is not there (hub#2143)', () => {
  function steps(answers: Array<object | null>) {
    const calls: string[] = [];
    let retry: (() => void) | null = null;
    return {
      calls,
      retry: () => retry?.(),
      loadContext: vi.fn(async () => {
        calls.push('load');
        return answers.shift() ?? null;
      }),
      showUnreachable: vi.fn((r: () => void) => {
        calls.push('unreachable');
        retry = r;
      }),
      showProgress: vi.fn(() => {
        calls.push('progress');
      }),
    };
  }

  it('goes straight on when the hub answers, and never shows the notice', async () => {
    const s = steps([{ hub_id: 'hub-1' }]);

    await bootUntilReachable(s);

    expect(s.calls).toEqual(['load']);
    expect(s.showUnreachable).not.toHaveBeenCalled();
  });

  it('stops on the notice when the hub does not answer, and does not go on', async () => {
    const s = steps([null]);
    let done = false;

    void bootUntilReachable(s).then(() => (done = true));
    await vi.waitFor(() => expect(s.showUnreachable).toHaveBeenCalledTimes(1));
    await Promise.resolve();

    expect(done).toBe(false);
  });

  it('retrying shows progress again, asks again, and goes on once the hub answers', async () => {
    const s = steps([null, null, { hub_id: 'hub-1' }]);
    let done = false;

    void bootUntilReachable(s).then(() => (done = true));
    await vi.waitFor(() => expect(s.showUnreachable).toHaveBeenCalledTimes(1));

    s.retry();
    await vi.waitFor(() => expect(s.showUnreachable).toHaveBeenCalledTimes(2));
    expect(done).toBe(false);

    s.retry();
    await vi.waitFor(() => expect(done).toBe(true));

    expect(s.calls).toEqual(['load', 'unreachable', 'progress', 'load', 'unreachable', 'progress', 'load']);
  });
});

// @vitest-environment happy-dom
// hub#765: the export POST had NO timeout. If the runtime (or the cloud proxy in front of it)
// hung, the fetch stayed open forever and the spinner spun until the user gave up — exactly the
// "no download, no error after 30s" the demo reported. A backup that can't say it failed is worse
// than one that errors honestly, because the user walks away thinking a copy exists.
//
// This is the runtime counterpart of the `AbortController` pattern already in `cloud.ts`: every
// long fetch needs a deadline, and the export is the longest fetch in the app.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { exportHub } from './runtime';

/**
 * A `fetch` that settles ONLY when the caller's AbortSignal fires — simulating a runtime/proxy
 * that never answers on its own. Captures the signal so the test can assert the deadline aborted
 * it. The promise is REJECTED from the abort listener; the test awaits the export rejection so no
 * unhandled rejection leaks.
 */
function fetchBlockedUntilAbort(): { signal: AbortSignal | undefined } {
  let captured: AbortSignal | undefined;
  vi.stubGlobal(
    'fetch',
    vi.fn((_url: string, init?: RequestInit) => {
      const signal = init?.signal ?? undefined;
      captured = signal;
      return new Promise<never>((_resolve, reject) => {
        signal?.addEventListener('abort', () => {
          // A real browser rejects the fetch with a DOMException when its signal aborts.
          reject(new DOMException('The operation was aborted.', 'TimeoutError'));
        });
      });
    }),
  );
  return { get signal() { return captured; } };
}

/** A `fetch` that answers 200 with a zip blob + Content-Disposition filename. */
function fetchThatAnswersZip(filename: string): void {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: (name: string) => (name.toLowerCase() === 'content-disposition' ? `attachment; filename="${filename}"` : null) },
      blob: () => Promise.resolve(new Blob(['zip-bytes'], { type: 'application/zip' })),
      text: () => Promise.resolve(''),
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('exportHub · deadline (hub#765)', () => {
  it('aborts the POST when the runtime does not answer in time and throws an actionable error', async () => {
    vi.useFakeTimers();
    const spy = fetchBlockedUntilAbort();

    // Kick off the export; it returns a promise that should reject once the deadline aborts.
    // Caught here (not left to float) so the abort rejection is never an unhandled rejection.
    const pending = exportHub('hub', 'es', {
      users: false, settings: true, settings_items: null,
      fiscal: false, media: false, modules: [], purpose: 'backup',
    }).catch((e: unknown) => e);

    // Before the deadline the POST is still in flight and the signal is alive.
    await vi.advanceTimersByTimeAsync(1_000);
    expect(spy.signal?.aborted).toBe(false);

    // Cross the deadline (EXPORT_DEADLINE_MS = 120s): the AbortController fires, the fetch rejects,
    // and exportHub surfaces a HONEST, actionable message (not a hang, not a generic "network").
    await vi.advanceTimersByTimeAsync(120_000);
    const err = await pending;
    expect(err).toBeInstanceOf(Error);
    expect(String((err as Error).message).length).toBeGreaterThan(0);
    expect(spy.signal?.aborted).toBe(true);
  });

  it('returns the blob + filename when the runtime answers before the deadline', async () => {
    fetchThatAnswersZip('hub_es.blueprint.zip');
    const out = await exportHub('hub', 'es', {
      users: false, settings: true, settings_items: null,
      fiscal: false, media: false, modules: [], purpose: 'backup',
    });
    expect(out.filename).toBe('hub_es.blueprint.zip');
    expect(out.blob.type).toBe('application/zip');
  });
});

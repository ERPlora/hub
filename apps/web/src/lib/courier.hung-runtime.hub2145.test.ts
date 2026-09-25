// @vitest-environment happy-dom
//
// hub#2145 — entering from the ERPlora panel while the hub stops answering must not leave the
// shell spinning.
//
// `main.ts` only mounts the app once `bootCourier` settles, so an exchange with no deadline is a
// shell that never mounts. The deadline is the one every runtime POST already carries
// (`runtimePost` aborts at 8 s); nothing pinned it for the courier, so these tests drive the REAL
// `runtimeCourierSession` against a runtime that accepts the connection and never answers.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./device', () => ({
  getDeviceContext: vi.fn(async () => ({ id: 'device-1', clientType: 'hub-desktop' })),
}));

import { armCourierBoot, bootCourier, courierBootPending, settleCourierBoot } from './courier';

/** A runtime that keeps the socket open and never replies; only an abort ends the request. */
function hungRuntime(): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(
      (_url: string, init?: RequestInit) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () =>
            reject(new DOMException('The operation was aborted.', 'AbortError')),
          );
        }),
    ),
  );
}

describe('courier exchange against a hub that stops answering (hub#2145)', () => {
  beforeEach(() => {
    settleCourierBoot();
    localStorage.clear();
    vi.useFakeTimers();
    hungRuntime();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('gives up within the runtime deadline so main.ts can mount the login page', async () => {
    let outcome: 'pending' | 'resolved' | 'rejected' = 'pending';
    bootCourier('opaque-code').then(
      () => { outcome = 'resolved'; },
      () => { outcome = 'rejected'; },
    );

    await vi.advanceTimersByTimeAsync(7_900);
    expect(outcome).toBe('pending'); // a slow but alive hub still gets its chance

    await vi.advanceTimersByTimeAsync(200);
    expect(outcome).toBe('rejected'); // main.ts catches this and mounts on /login
  });

  it('releases the auth gate and opens no session when the exchange runs out of time', async () => {
    armCourierBoot(60_000); // longer than the runtime deadline: only the exchange can release it
    const gate = courierBootPending();
    let released = false;
    void gate!.then(() => { released = true; });

    let gaveUp = false;
    bootCourier('opaque-code').catch(() => { gaveUp = true; });
    await vi.advanceTimersByTimeAsync(8_100);

    expect(gaveUp).toBe(true);
    expect(released).toBe(true);
    expect(courierBootPending()).toBeNull();
    expect(localStorage.length).toBe(0); // no half-written tokens or hub session
  });
});

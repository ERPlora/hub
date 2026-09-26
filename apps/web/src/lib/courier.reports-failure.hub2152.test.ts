// @vitest-environment happy-dom
//
// hub#2152 — entering from the ERPlora panel when the pass cannot be redeemed must leave a trace.
//
// `main.ts` used to swallow the exchange's rejection with an empty `catch`, so a hub answering a
// proxy page, a broken body or nothing at all sent the person to the login with no word about it
// and nobody on the team ever learned the exchange was failing. `redeemShellCourier` is the boot's
// single entry point: it never throws (login must stay reachable), it reports the failure through
// the ordinary client-error channel with the runtime's CODE — never the pass (ADR-0159) — and it
// leaves a one-shot flag the login page turns into a short notice.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./device', () => ({
  getDeviceContext: vi.fn(async () => ({ id: 'device-1', clientType: 'hub-desktop' })),
}));

const reports = vi.hoisted(() => ({ calls: [] as Array<{ message: string; component?: string | null }> }));
vi.mock('./error-report', () => ({
  reportClientError: vi.fn((input: { message: string; component?: string | null }) => {
    reports.calls.push(input);
  }),
}));

import { redeemShellCourier, settleCourierBoot, takeCourierFailure } from './courier';

const PASS = 'opaque-one-time-pass-9f3a';

function runtimeAnswers(response: () => Promise<Response>): void {
  vi.stubGlobal('fetch', vi.fn(response));
}

function sessionBody(): Record<string, unknown> {
  return {
    ok: true,
    access: 'a',
    refresh: 'r',
    token: 't',
    credential_kind: 'password',
    user: { id: 'u1', role: 'admin' },
    cloud_user: { id: 'c1', name: 'Ana', email: 'ana@example.invalid' },
    permissions: [],
  };
}

describe('the boot reports a pass it could not redeem (hub#2152)', () => {
  beforeEach(() => {
    settleCourierBoot();
    takeCourierFailure();
    localStorage.clear();
    reports.calls.length = 0;
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('reports a broken answer with its code, never the pass, and does not throw', async () => {
    runtimeAnswers(async () => new Response('<html>proxy error</html>', { status: 200 }));

    await expect(redeemShellCourier(PASS)).resolves.toBe(false);

    expect(reports.calls).toHaveLength(1);
    expect(reports.calls[0].component).toBe('courier');
    expect(reports.calls[0].message).toContain('runtime_bad_response');
    expect(reports.calls[0].message).not.toContain(PASS);
  });

  it('reports the refusal code the hub sends back', async () => {
    runtimeAnswers(
      async () =>
        new Response(JSON.stringify({ ok: false, code: 'courier_expired', error: `pass ${PASS} expired` }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        }),
    );

    await expect(redeemShellCourier(PASS)).resolves.toBe(false);

    expect(reports.calls).toHaveLength(1);
    expect(reports.calls[0].message).toContain('courier_expired');
    // The runtime's prose is not trusted to be free of the pass: only the code travels.
    expect(reports.calls[0].message).not.toContain(PASS);
  });

  it('reports a hub that never answered as a timeout', async () => {
    vi.useFakeTimers();
    runtimeAnswers(
      () =>
        new Promise((_resolve, reject) => {
          const signal = (vi.mocked(fetch).mock.calls.at(-1)?.[1] as RequestInit | undefined)?.signal;
          signal?.addEventListener('abort', () =>
            reject(new DOMException('The operation was aborted.', 'AbortError')),
          );
        }),
    );

    const outcome = redeemShellCourier(PASS);
    await vi.advanceTimersByTimeAsync(8_100);

    await expect(outcome).resolves.toBe(false);
    expect(reports.calls).toHaveLength(1);
    expect(reports.calls[0].message).toContain('AbortError');
  });

  it('leaves a one-shot flag for the login page', async () => {
    runtimeAnswers(async () => new Response('<html>proxy error</html>', { status: 200 }));

    await redeemShellCourier(PASS);

    expect(takeCourierFailure()).toBe(true);
    expect(takeCourierFailure()).toBe(false);
  });

  it('reports nothing and flags nothing when the exchange succeeds', async () => {
    runtimeAnswers(
      async () =>
        new Response(JSON.stringify(sessionBody()), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
    );

    await expect(redeemShellCourier(PASS)).resolves.toBe(true);

    expect(reports.calls).toHaveLength(0);
    expect(takeCourierFailure()).toBe(false);
  });

  it('reports nothing when there was no pass to redeem', async () => {
    runtimeAnswers(async () => new Response('{}', { status: 200 }));

    await expect(redeemShellCourier(null)).resolves.toBe(false);

    expect(reports.calls).toHaveLength(0);
    expect(takeCourierFailure()).toBe(false);
  });
});

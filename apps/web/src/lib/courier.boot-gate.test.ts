// @vitest-environment happy-dom
//
// hub#858 — the shell courier is a RACE, not a missing credential.
//
// `main.ts` installs the router (`app.use(router)`) at module evaluation, which starts Vue
// Router's initial navigation immediately. The courier exchange, by contrast, is two network
// round trips that only finish later. So the auth gate answered "no session → /login" before the
// session it was about to receive existed, and nothing re-navigated afterwards: the user got the
// login form inside an already-authenticated shell.
//
// The fix is a BOOT GATE. Taking the code out of the fragment happens synchronously, before the
// router is installed, so that is where the gate is armed; the exchange settles it. These tests
// pin the two halves of that contract (the gate's effect on navigation lives in
// `src/router/auth-gate.test.ts`).
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { runtimeCourierSession, setTokens, setHubSession, setUser } = vi.hoisted(() => ({
  runtimeCourierSession: vi.fn(),
  setTokens: vi.fn(),
  setHubSession: vi.fn(),
  setUser: vi.fn(),
}));

vi.mock('./cloud', () => ({ runtimeCourierSession, setTokens }));
vi.mock('./device', () => ({
  getDeviceContext: vi.fn(async () => ({ id: 'device-1', clientType: 'hub-desktop' })),
}));
vi.mock('./session', () => ({ setHubSession, setUser }));

import {
  armCourierBoot,
  bootCourier,
  courierBootPending,
  settleCourierBoot,
  takeCourierCode,
} from './courier';

const GRANT = {
  access: 'access-jwt',
  refresh: 'refresh-jwt',
  token: 'local-session',
  user: { id: 'local-1', name: 'Ana', role: 'owner' },
  permissions: ['*'],
  cloud_user: { id: 'cloud-1', name: 'Ana', email: 'ana@example.com' },
};

describe('shell courier boot gate (hub#858)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    settleCourierBoot();
    window.history.replaceState(null, '', '/?shell=1');
  });

  it('is not armed when no courier is inbound (an ordinary boot must not wait for anything)', () => {
    expect(takeCourierCode()).toBeNull();
    expect(courierBootPending()).toBeNull();
  });

  it('arms synchronously while taking the code out of the fragment', () => {
    // This is the whole point: the gate has to exist BEFORE the router is installed, and taking
    // the code is the only step that already runs that early.
    window.history.replaceState(null, '', '/?shell=1#courier=opaque-code');
    expect(takeCourierCode()).toBe('opaque-code');
    expect(courierBootPending()).toBeInstanceOf(Promise);
  });

  it('stays pending until the exchange finishes, then settles', async () => {
    let release: (v: typeof GRANT) => void = () => {};
    runtimeCourierSession.mockReturnValue(new Promise((resolve) => { release = resolve; }));

    armCourierBoot();
    const gate = courierBootPending();
    expect(gate).not.toBeNull();

    let settled = false;
    void gate!.then(() => { settled = true; });

    const boot = bootCourier('opaque-code');
    await Promise.resolve();
    expect(settled).toBe(false); // still in flight — the gate must hold navigation back

    release(GRANT);
    await boot;
    await gate;
    expect(settled).toBe(true);
    expect(courierBootPending()).toBeNull(); // one-shot: later navigations never wait again
  });

  it('settles even when the exchange FAILS, so an expired code cannot wedge the app', async () => {
    runtimeCourierSession.mockRejectedValue(new Error('invalid or expired code'));
    armCourierBoot();
    const gate = courierBootPending();

    await expect(bootCourier('stale-code')).rejects.toThrow();
    await expect(gate).resolves.toBeUndefined();
    expect(courierBootPending()).toBeNull();
  });

  it('settles on its own watchdog if the exchange never answers at all', async () => {
    vi.useFakeTimers();
    try {
      armCourierBoot(50);
      const gate = courierBootPending();
      let settled = false;
      void gate!.then(() => { settled = true; });

      await vi.advanceTimersByTimeAsync(49);
      expect(settled).toBe(false);
      await vi.advanceTimersByTimeAsync(2);
      expect(settled).toBe(true); // login stays reachable; the app never hangs on a dead runtime
    } finally {
      vi.useRealTimers();
    }
  });
});

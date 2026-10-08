// @vitest-environment happy-dom
// hub#2537 — a till that must sign out when nobody touches it stayed signed in when the read of its
// dial failed.
//
// The dial («ask for a PIN: always / per shift / never») reaches the shell through two reads:
// `GET /api/device/mode` (every boot, also with a live session) and `GET /api/settings` (after
// sign-in). When a read fails the pinpad side falls to `per_shift` — right for the pinpad, which
// `per_shift` and `always` both paint — but the idle detector only arms on `always`, so the same
// fallback DISARMED it: a hub restarting at the wrong moment left the till open under the last
// person's name until the session's own one-hour cap, with nothing on screen to say so.
//
// What these tests hold (HUB_SHELL-F08):
//
//   - **An unreadable dial arms the idle sign-out** (fail closed), with the default window when the
//     minutes are unknown too, and with the known minutes when they are not.
//   - **A dial the hub DID answer still decides**: `per_shift` does not arm, `always` does.
//   - **The failure is visible**: the person at the till is told, once, that it will go back to the
//     pinpad after N minutes without use because the settings could not be read.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const resolveDeviceId = vi.fn<() => Promise<string | null>>();
vi.mock('./device', () => ({ resolveDeviceId: () => resolveDeviceId() }));
const toast = vi.fn<(message: string, color?: string, duration?: number) => Promise<void>>();
vi.mock('./toast', () => ({ toast: (...args: [string, string?, number?]) => toast(...args) }));
vi.mock('./theme', () => ({ setHubPalette: vi.fn() }));

import { i18n } from '../i18n';
import { deviceMode, loadDeviceMode } from './device-mode';
import { getHubSettings, hubSettings } from './hub-settings';
import { DEFAULT_IDLE_MINUTES, installIdleLogout } from './idle-logout';
import { setUser } from './session';

const MIN = 60_000;

/** `fetch` answering every call with `status` + `body`. */
function respondWith(status: number, body: unknown): void {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      json: () => Promise.resolve(body),
    }),
  );
}

/** `fetch` failing the way a hub that is restarting does. */
function hubUnreachable(): void {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
}

/** The device answer of a trusted shared till whose business set the dial to `policy`. */
function deviceAnswer(policy: string): unknown {
  return { data: { mode: 'shared', trusted: true, pin_policy: policy } };
}

const t = i18n.global.t as unknown as (key: string, named?: Record<string, unknown>) => string;

let uninstall: (() => void) | null = null;

beforeEach(() => {
  vi.useFakeTimers();
  resolveDeviceId.mockResolvedValue('till-1');
  setUser({ id: 'u1', name: 'Ana', email: 'ana@example.com' });
});

afterEach(() => {
  uninstall?.();
  uninstall = null;
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  setUser(null);
  hubSettings.value = null;
  deviceMode.value = 'shared';
});

describe('hub#2537: the dial cannot be read', () => {
  it('a 503 on the device read at boot still signs the till out after the default window', async () => {
    respondWith(503, { error: { code: 'unavailable' } });
    await loadDeviceMode();
    const onIdle = vi.fn();
    uninstall = installIdleLogout(onIdle);

    await vi.advanceTimersByTimeAsync(DEFAULT_IDLE_MINUTES * MIN);
    expect(onIdle).toHaveBeenCalledTimes(1);
  });

  it('a hub that cannot be reached at all is the same: the idle sign-out stays armed', async () => {
    hubUnreachable();
    await loadDeviceMode();
    const onIdle = vi.fn();
    uninstall = installIdleLogout(onIdle);

    await vi.advanceTimersByTimeAsync(DEFAULT_IDLE_MINUTES * MIN);
    expect(onIdle).toHaveBeenCalledTimes(1);
  });

  it('a failed re-read after a known `always` does not disarm it, and keeps the known minutes', async () => {
    respondWith(200, { pin_policy: 'always', pin_inactivity_minutes: 1 });
    await getHubSettings();
    const onIdle = vi.fn();
    uninstall = installIdleLogout(onIdle);

    respondWith(500, {});
    await loadDeviceMode();
    await vi.advanceTimersByTimeAsync(1 * MIN);
    expect(onIdle).toHaveBeenCalledTimes(1);
  });

  it('tells the person at the till, once, why it will go back to the pinpad', async () => {
    respondWith(503, {});
    await loadDeviceMode();
    uninstall = installIdleLogout(vi.fn());
    await vi.advanceTimersByTimeAsync(0);

    const expected = t('pinPolicy.unreadableIdleLock', { n: DEFAULT_IDLE_MINUTES });
    expect(expected).not.toBe('pinPolicy.unreadableIdleLock');
    expect(toast).toHaveBeenCalledTimes(1);
    expect(toast).toHaveBeenCalledWith(expected, 'warning', expect.any(Number));

    // A second failed read is the same failure, not a second notice.
    await loadDeviceMode();
    await vi.advanceTimersByTimeAsync(0);
    expect(toast).toHaveBeenCalledTimes(1);
  });

  it('re-arming while the dial is still unreadable takes the new minutes without repeating the notice', async () => {
    respondWith(503, {});
    await loadDeviceMode();
    const onIdle = vi.fn();
    uninstall = installIdleLogout(onIdle);
    await vi.advanceTimersByTimeAsync(0);
    expect(toast).toHaveBeenCalledTimes(1);

    // The settings arrive with minutes but a dial this build cannot read: still unknown, so still
    // armed — now with the hub's minutes — and it is the same failure, not a new one.
    respondWith(200, { pin_policy: 'ALWAYS', pin_inactivity_minutes: 10 });
    await getHubSettings();
    await vi.advanceTimersByTimeAsync(10 * MIN - 1);
    expect(onIdle).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(onIdle).toHaveBeenCalledTimes(1);
    expect(toast).toHaveBeenCalledTimes(1);
  });

  it('says nothing on a personal device or with nobody signed in: there is no idle lock there', async () => {
    respondWith(200, { data: { mode: 'personal', trusted: true } });
    await loadDeviceMode();
    uninstall = installIdleLogout(vi.fn());
    setUser(null);
    deviceMode.value = 'shared';
    await vi.advanceTimersByTimeAsync(0);
    expect(toast).not.toHaveBeenCalled();
  });
});

describe('hub#2537: a dial the hub did answer still decides', () => {
  it('`per_shift` read successfully does not arm, and says nothing', async () => {
    respondWith(200, deviceAnswer('per_shift'));
    await loadDeviceMode();
    const onIdle = vi.fn();
    uninstall = installIdleLogout(onIdle);

    await vi.advanceTimersByTimeAsync(60 * MIN);
    expect(onIdle).not.toHaveBeenCalled();
    expect(toast).not.toHaveBeenCalled();
  });

  it('a successful read after a failure disarms again and the next failure is announced again', async () => {
    respondWith(503, {});
    await loadDeviceMode();
    const onIdle = vi.fn();
    uninstall = installIdleLogout(onIdle);

    respondWith(200, deviceAnswer('per_shift'));
    await loadDeviceMode();
    await vi.advanceTimersByTimeAsync(60 * MIN);
    expect(onIdle).not.toHaveBeenCalled();

    respondWith(503, {});
    await loadDeviceMode();
    await vi.advanceTimersByTimeAsync(0);
    expect(toast).toHaveBeenCalledTimes(2);
  });

  it('`always` read successfully arms with the hub minutes, and says nothing', async () => {
    respondWith(200, deviceAnswer('always'));
    await loadDeviceMode();
    hubSettings.value = { pin_inactivity_minutes: 10 } as unknown as NonNullable<typeof hubSettings.value>;
    const onIdle = vi.fn();
    uninstall = installIdleLogout(onIdle);

    await vi.advanceTimersByTimeAsync(10 * MIN - 1);
    expect(onIdle).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(onIdle).toHaveBeenCalledTimes(1);
    expect(toast).not.toHaveBeenCalled();
  });
});

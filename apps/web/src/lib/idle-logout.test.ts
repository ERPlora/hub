// @vitest-environment happy-dom
// Idle sign-out (hub#628, the client half of hub#456's «bloqueo por inactividad»).
//
// With «Show PIN pad» on and the range at N minutes (`pin_policy = always` +
// `pin_inactivity_minutes`), a counter till that nobody has touched for N minutes signs the
// current user out and shows the pinpad — so the next sale is typed under the next person's name,
// not under whoever walked away. The hub cannot observe a hand leaving the till, so the DETECTOR
// lives here, in the shell; the runtime keeps its own session TTL as the backstop for a client
// that never comes back to enforce anything.
//
// Three boundaries these tests pin:
//
//   - **Only the counter till.** `personal` devices lock with the owner's OS, and the other two
//     policy positions have no idle window at all (hub#456 §1: solo aplica a `shared`).
//   - **Late timers still count.** Browsers throttle background timers, so the check re-measures
//     elapsed time instead of trusting one setTimeout to fire on schedule.
//   - **It fires once.** Sign-out tears the world down around the timer; a second firing would
//     race the login screen.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  createIdleTimer,
  idleMinutesOf,
  installIdleLogout,
  shouldArmIdleLogout,
} from './idle-logout';
import { hubSettings, type HubSettings } from './hub-settings';
import { pinPolicy } from './pin-policy';
import { deviceMode } from './device-mode';
import { setUser } from './session';

const MIN = 60_000;

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  setUser(null);
  hubSettings.value = null;
  pinPolicy.value = 'per_shift';
  deviceMode.value = 'shared';
});

describe('when the detector arms at all', () => {
  it('arms only on a signed-in SHARED device whose policy is `always`', () => {
    expect(shouldArmIdleLogout('always', 'shared', true)).toBe(true);
  });

  it('never arms on a personal device: that lock belongs to the OS', () => {
    expect(shouldArmIdleLogout('always', 'personal', true)).toBe(false);
  });

  it('never arms for the positions without an idle window', () => {
    expect(shouldArmIdleLogout('per_shift', 'shared', true)).toBe(false);
    expect(shouldArmIdleLogout('never', 'shared', true)).toBe(false);
  });

  it('never arms with nobody signed in: there is no session to end', () => {
    expect(shouldArmIdleLogout('always', 'shared', false)).toBe(false);
  });
});

describe('how many minutes the window is', () => {
  it('reads the hub setting', () => {
    expect(idleMinutesOf({ pin_inactivity_minutes: 10 } as Partial<HubSettings>)).toBe(10);
  });

  it('falls back to the default (5) when the settings have not arrived or are unreadable', () => {
    // Mirror of the runtime: an absent or corrupt row degrades to the DEFAULT, never to a bound.
    expect(idleMinutesOf(null)).toBe(5);
    expect(idleMinutesOf({} as Partial<HubSettings>)).toBe(5);
    expect(idleMinutesOf({ pin_inactivity_minutes: 0 } as Partial<HubSettings>)).toBe(5);
    expect(idleMinutesOf({ pin_inactivity_minutes: 31 } as Partial<HubSettings>)).toBe(5);
    expect(idleMinutesOf({ pin_inactivity_minutes: 2.5 } as Partial<HubSettings>)).toBe(5);
  });
});

describe('the timer', () => {
  it('fires after the window with no activity', () => {
    const onIdle = vi.fn();
    createIdleTimer({ minutes: 3, onIdle });

    vi.advanceTimersByTime(3 * MIN - 1);
    expect(onIdle).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(onIdle).toHaveBeenCalledTimes(1);
  });

  it('is pushed back by activity: the window measures since the LAST touch', () => {
    const onIdle = vi.fn();
    const timer = createIdleTimer({ minutes: 3, onIdle });

    vi.advanceTimersByTime(2 * MIN);
    timer.activity();
    vi.advanceTimersByTime(2 * MIN); // 4 min since start, 2 since the touch
    expect(onIdle).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1 * MIN); // 3 min since the touch
    expect(onIdle).toHaveBeenCalledTimes(1);
  });

  it('fires exactly once', () => {
    const onIdle = vi.fn();
    const timer = createIdleTimer({ minutes: 1, onIdle });

    vi.advanceTimersByTime(10 * MIN);
    timer.activity();
    vi.advanceTimersByTime(10 * MIN);
    expect(onIdle).toHaveBeenCalledTimes(1);
  });

  it('a stopped timer never fires', () => {
    const onIdle = vi.fn();
    const timer = createIdleTimer({ minutes: 1, onIdle });

    timer.stop();
    vi.advanceTimersByTime(10 * MIN);
    expect(onIdle).not.toHaveBeenCalled();
  });
});

describe('installed in the shell', () => {
  /** Signed-in shared till with the range at 1 minute: the arming state of every test below. */
  function armedWorld(): void {
    setUser({ id: 'u1', name: 'Ana', email: 'ana@example.com' });
    deviceMode.value = 'shared';
    pinPolicy.value = 'always';
    hubSettings.value = { pin_inactivity_minutes: 1 } as unknown as HubSettings;
  }

  it('signs out after the window on a shared till set to `always`', async () => {
    armedWorld();
    const onIdle = vi.fn();
    const uninstall = installIdleLogout(onIdle);
    await vi.advanceTimersByTimeAsync(1 * MIN);

    expect(onIdle).toHaveBeenCalledTimes(1);
    uninstall();
  });

  it('a touch on the screen pushes the window back', async () => {
    armedWorld();
    const onIdle = vi.fn();
    const uninstall = installIdleLogout(onIdle);

    await vi.advanceTimersByTimeAsync(30_000);
    window.dispatchEvent(new Event('pointerdown'));
    await vi.advanceTimersByTimeAsync(45_000); // 75s since install, 45 since the touch
    expect(onIdle).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(15_000); // 60s since the touch
    expect(onIdle).toHaveBeenCalledTimes(1);
    uninstall();
  });

  it('disarms the moment the world stops qualifying (e.g. the dial leaves `always`)', async () => {
    armedWorld();
    const onIdle = vi.fn();
    const uninstall = installIdleLogout(onIdle);

    pinPolicy.value = 'per_shift';
    await vi.advanceTimersByTimeAsync(10 * MIN);
    expect(onIdle).not.toHaveBeenCalled();
    uninstall();
  });

  it('does nothing on a personal device', async () => {
    armedWorld();
    deviceMode.value = 'personal';
    const onIdle = vi.fn();
    const uninstall = installIdleLogout(onIdle);

    await vi.advanceTimersByTimeAsync(10 * MIN);
    expect(onIdle).not.toHaveBeenCalled();
    uninstall();
  });

  it('uninstalling stops the detector for good', async () => {
    armedWorld();
    const onIdle = vi.fn();
    const uninstall = installIdleLogout(onIdle);

    uninstall();
    await vi.advanceTimersByTimeAsync(10 * MIN);
    expect(onIdle).not.toHaveBeenCalled();
  });
});

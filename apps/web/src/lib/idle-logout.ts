// Idle sign-out (hub#628) — the client half of hub#456's «bloqueo por inactividad».
//
// With «Show PIN pad» on and the idle range at N minutes (`pin_policy = always` +
// `pin_inactivity_minutes`), a counter till nobody has touched for N minutes signs the current
// user out and shows the pinpad, so the next sale is typed under the next person's name. The hub
// cannot observe a hand leaving the till — the DETECTOR has to live here in the shell — while the
// runtime keeps its own session TTL (`ALWAYS_SESSION_TTL_SECS`) as the backstop for a client that
// never comes back to enforce anything.
//
// Boundaries, all deliberate:
//
//   - **Only the counter till.** `shouldArmIdleLogout` demands `shared` + `always` + a signed-in
//     session. A `personal` device locks with its owner's OS (hub#456 §1), the other two policy
//     positions have no idle window, and with nobody signed in there is nothing to end.
//   - **Late timers still count.** Browsers throttle background-tab timers, so the expiry check
//     re-measures elapsed time from the last touch and re-arms for the remainder instead of
//     trusting one setTimeout to fire on schedule. Activity itself only stamps a timestamp —
//     no clearTimeout churn on every keystroke of a busy till.
//   - **It fires once.** The sign-out tears the world down around the timer (and flips
//     `isAuthed`, which disarms the watcher); a second firing would race the login screen.
import { watchEffect } from 'vue';

import { deviceMode, type DeviceMode } from './device-mode';
import { hubSettings, type HubSettings } from './hub-settings';
import { pinPolicy, type PinPolicy } from './pin-policy';
import { isAuthed } from './session';

/** Idle minutes assumed when the setting is absent or unreadable (mirror of the runtime, which
 *  degrades a corrupt row to its DEFAULT — never to a bound). */
export const DEFAULT_IDLE_MINUTES = 5;

/** Ceiling of the idle window (mirror of the runtime's `MAX_PIN_INACTIVITY_MINUTES`). */
const MAX_IDLE_MINUTES = 30;

/** Does this combination of dial, device and session get an idle detector at all? */
export function shouldArmIdleLogout(policy: PinPolicy, mode: DeviceMode, authed: boolean): boolean {
  return authed && policy === 'always' && mode === 'shared';
}

/** The idle window in force, from the hub's settings; unreadable → {@link DEFAULT_IDLE_MINUTES}. */
export function idleMinutesOf(settings: Partial<HubSettings> | null): number {
  const n = settings?.pin_inactivity_minutes;
  return typeof n === 'number' && Number.isInteger(n) && n >= 1 && n <= MAX_IDLE_MINUTES
    ? n
    : DEFAULT_IDLE_MINUTES;
}

/**
 * A one-shot idle timer: calls `onIdle` once the last recorded activity is `minutes` old.
 * `activity()` is cheap on purpose (a timestamp write) — the pending timeout re-measures on fire
 * and re-arms for the remainder, which also makes a throttled, late-firing timer count the time
 * that really passed.
 */
export function createIdleTimer(opts: { minutes: number; onIdle: () => void }): {
  activity(): void;
  stop(): void;
} {
  const windowMs = opts.minutes * 60_000;
  let last = Date.now();
  let handle: ReturnType<typeof setTimeout> | null = null;
  let done = false;

  const check = (): void => {
    if (done) return;
    const remaining = windowMs - (Date.now() - last);
    if (remaining <= 0) {
      done = true;
      handle = null;
      opts.onIdle();
    } else {
      handle = setTimeout(check, remaining);
    }
  };
  handle = setTimeout(check, windowMs);

  return {
    activity(): void {
      last = Date.now();
    },
    stop(): void {
      done = true;
      if (handle) {
        clearTimeout(handle);
        handle = null;
      }
    },
  };
}

/** What counts as «somebody is using this till». Discrete gestures only — `pointermove` would
 *  keep a session alive because a cat walked past a touchscreen's hover sensor. */
export const IDLE_ACTIVITY_EVENTS = ['pointerdown', 'keydown', 'wheel', 'touchstart'] as const;

/**
 * Wire the idle detector to the shell's reactive world. Arms/disarms itself as the policy, the
 * device mode, the session and the configured minutes change; returns an uninstaller (App.vue
 * calls this once and holds it for unmount).
 */
export function installIdleLogout(onIdle: () => void): () => void {
  let timer: ReturnType<typeof createIdleTimer> | null = null;
  const activity = (): void => timer?.activity();

  const disarm = (): void => {
    if (!timer) return;
    timer.stop();
    timer = null;
    for (const ev of IDLE_ACTIVITY_EVENTS) window.removeEventListener(ev, activity);
  };

  const stopWatch = watchEffect(() => {
    // Both reads happen before the early return so the effect tracks them all: a minutes change
    // re-arms with the fresh window, a disqualifying change disarms.
    const arm = shouldArmIdleLogout(pinPolicy.value, deviceMode.value, isAuthed.value);
    const minutes = idleMinutesOf(hubSettings.value);
    disarm();
    if (!arm) return;
    timer = createIdleTimer({ minutes, onIdle });
    for (const ev of IDLE_ACTIVITY_EVENTS) window.addEventListener(ev, activity, { passive: true });
  });

  return (): void => {
    stopWatch();
    disarm();
  };
}

// «Show PIN pad» (hub#628) — the pure mapping between the Settings card's two controls (a toggle
// + an idle range) and the wire the runtime already speaks.
//
// The redesign of hub#359's card changed the PRESENTATION, deliberately not the contract:
// `pin_policy` stays the closed `always | per_shift | never` set (lib/pin-policy, mirrored by
// `PinPolicy::parse` in the runtime), because the login screen reads it with no session and every
// spelling that reaches the wire has to be one the runtime is strict about. This module is the one
// place where the two controls meet that contract:
//
//   - toggle OFF             → `never`     (no pinpad; sales stop carrying a name)
//   - toggle ON              → `per_shift` (the runtime's own default — never a guess at whatever
//                                           idle window was configured before the pinpad went off)
//   - range at a minute stop → `always` + `pin_inactivity_minutes` (the shell's idle detector
//                                           signs out after that many minutes and shows the pinpad)
//   - range at the last stop → `per_shift` (no idle lock: the session lives until sign-out)
//
// Anything unreadable resolves TOWARDS the pinpad — same failure direction as lib/pin-policy.
import type { PinPolicy } from './pin-policy';

/** The minute stops of the idle range, in the order they are drawn. Presentation: the runtime
 *  validates a RANGE (1..=30), so a value between stops is legal on the wire — see
 *  {@link stopFromWire} for where such a value places the handle. */
export const IDLE_STOPS: readonly number[] = [1, 5, 10, 15, 30];

/** Index of the last stop, «until you sign out»: pinpad on, no idle lock. */
export const UNTIL_SIGN_OUT_STOP = IDLE_STOPS.length;

/** Idle minutes assumed when the stored value is unreadable (mirror of the runtime's default). */
const DEFAULT_IDLE_MINUTES = 5;

/** The partial `PUT /api/settings` body a control change means. */
export interface PinpadWire {
  pin_policy: PinPolicy;
  pin_inactivity_minutes?: number;
}

/**
 * The write a toggle flip means. ON is `per_shift` on purpose: turning the pinpad back on must
 * not resurrect a forgotten aggressive idle window — the safe position is the one the runtime
 * itself defaults to, and the owner tightens from there with the range.
 */
export function wireFromToggle(on: boolean): PinpadWire {
  return { pin_policy: on ? 'per_shift' : 'never' };
}

/**
 * The write a range stop means. A stop that is not one of the drawn positions (a fractional
 * value, an index from a future build) resolves to `per_shift` — the position that keeps asking
 * without inventing an idle window the owner never chose.
 */
export function wireFromStop(stop: number): PinpadWire {
  if (Number.isInteger(stop) && stop >= 0 && stop < IDLE_STOPS.length) {
    return { pin_policy: 'always', pin_inactivity_minutes: IDLE_STOPS[stop] };
  }
  return { pin_policy: 'per_shift' };
}

/**
 * Where the range handle sits for what the hub confirmed. Only `always` uses the minutes; the
 * other two positions have no idle lock and sit on «until you sign out». Minutes between stops
 * snap to the NEAREST stop, ties towards the stricter (shorter) one — the handle may not promise
 * a longer window than the hub enforces.
 */
export function stopFromWire(policy: PinPolicy, minutes: number): number {
  if (policy !== 'always') return UNTIL_SIGN_OUT_STOP;
  const m = Number.isFinite(minutes) && minutes > 0 ? minutes : DEFAULT_IDLE_MINUTES;
  let best = 0;
  for (let i = 1; i < IDLE_STOPS.length; i += 1) {
    if (Math.abs(IDLE_STOPS[i] - m) < Math.abs(IDLE_STOPS[best] - m)) best = i;
  }
  return best;
}

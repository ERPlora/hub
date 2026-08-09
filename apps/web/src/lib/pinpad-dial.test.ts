// «Show PIN pad» (hub#628) — the pure mapping between the card's two controls (a toggle + an idle
// range) and the wire the runtime already speaks (`pin_policy` + `pin_inactivity_minutes`).
//
// The wire contract does NOT change with the redesign: `pin_policy` stays the closed
// `always | per_shift | never` set the login screen reads with no session. What changed is the
// PRESENTATION — so this module is where the presentation meets the contract, and these tests pin
// that meeting point:
//
//   - toggle OFF          → `never`             (the pinpad disappears; sales stop carrying a name)
//   - toggle ON           → `per_shift`         (the runtime's own default: safe, asks once)
//   - range at a minute stop → `always` + the minutes (the shell's idle detector signs out)
//   - range at the last stop → `per_shift`      (no idle lock: the session lives until sign-out)
//
// Everything unreadable resolves TOWARDS the pinpad, same direction as lib/pin-policy.
import { describe, expect, it } from 'vitest';

import {
  IDLE_STOPS,
  UNTIL_SIGN_OUT_STOP,
  stopFromWire,
  wireFromStop,
  wireFromToggle,
} from './pinpad-dial';

describe('the stops the owner is shown', () => {
  it('are 1 · 5 · 10 · 15 · 30 minutes plus «until you sign out» at the end', () => {
    expect(IDLE_STOPS).toEqual([1, 5, 10, 15, 30]);
    expect(UNTIL_SIGN_OUT_STOP).toBe(5);
  });
});

describe('what a toggle flip writes', () => {
  it('OFF writes `never` and nothing else', () => {
    expect(wireFromToggle(false)).toEqual({ pin_policy: 'never' });
  });

  it('ON writes `per_shift` — the runtime default, never a guess at old minutes', () => {
    // Turning the pinpad back on must not resurrect a forgotten aggressive idle window: the safe
    // position is the one the runtime itself defaults to, and the owner tightens from there.
    expect(wireFromToggle(true)).toEqual({ pin_policy: 'per_shift' });
  });
});

describe('what a range stop writes', () => {
  it('a minute stop writes `always` plus the minutes of that stop', () => {
    expect(wireFromStop(0)).toEqual({ pin_policy: 'always', pin_inactivity_minutes: 1 });
    expect(wireFromStop(1)).toEqual({ pin_policy: 'always', pin_inactivity_minutes: 5 });
    expect(wireFromStop(4)).toEqual({ pin_policy: 'always', pin_inactivity_minutes: 30 });
  });

  it('the last stop writes `per_shift`: no idle lock, the session lives until sign-out', () => {
    expect(wireFromStop(UNTIL_SIGN_OUT_STOP)).toEqual({ pin_policy: 'per_shift' });
  });

  it('an out-of-range stop resolves to the position that keeps asking, not to a guess', () => {
    expect(wireFromStop(-1)).toEqual({ pin_policy: 'per_shift' });
    expect(wireFromStop(99)).toEqual({ pin_policy: 'per_shift' });
    expect(wireFromStop(2.5)).toEqual({ pin_policy: 'per_shift' });
  });
});

describe('where the handle sits for what the hub confirmed', () => {
  it('`always` places it on the stop of the stored minutes', () => {
    expect(stopFromWire('always', 1)).toBe(0);
    expect(stopFromWire('always', 5)).toBe(1);
    expect(stopFromWire('always', 30)).toBe(4);
  });

  it('minutes between stops snap to the NEAREST stop, ties towards the stricter one', () => {
    // The runtime validates a RANGE (1..=30), so a hub can hold minutes the range has no stop
    // for (an API write, a future numeric input). The handle still has to sit somewhere honest.
    expect(stopFromWire('always', 7)).toBe(1); // 7 → 5 (distance 2) beats 10 (distance 3)
    expect(stopFromWire('always', 3)).toBe(0); // tie between 1 and 5 → the stricter stop
    expect(stopFromWire('always', 22)).toBe(3); // 22 → 15 beats 30
  });

  it('`per_shift` and `never` sit on «until you sign out»', () => {
    expect(stopFromWire('per_shift', 5)).toBe(UNTIL_SIGN_OUT_STOP);
    expect(stopFromWire('never', 5)).toBe(UNTIL_SIGN_OUT_STOP);
  });

  it('unreadable minutes fall back to the default stop (5 min), never off the range', () => {
    expect(stopFromWire('always', Number.NaN)).toBe(1);
    // 0 is not a legal wire value (the runtime validates 1..=30 and DEGRADES a corrupt row to its
    // default, 5 — not to the nearest bound). The handle mirrors the server it reads from.
    expect(stopFromWire('always', 0)).toBe(1);
    expect(stopFromWire('always', 999)).toBe(4);
  });
});

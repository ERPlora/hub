// @vitest-environment happy-dom
// hub#359 — the web side of **"ask for a PIN: always / per shift / never"**.
//
// This module holds one value, and the value decides whether the till asks who is selling. So it is
// a security component wearing the clothes of a preference, and every rule here leans the same way
// as hub#358's device mode:
//
//   - **Anything that is not exactly one of the three spellings is the default**, and the default
//     is one of the two that keep asking. A network failure, a 500, a typo, a spelling from a newer
//     build: none of them may land on `never`, because `never` is the one that gives up the name on
//     every sale.
//   - **A `never` already read is given back on a later failure.** Otherwise one lucky answer would
//     outlive the decision behind it — the same reasoning that makes hub#358 revert a granted
//     `personal`.
//   - **It is never cached in `localStorage`.** A stored `never` would be a pinpad switch sitting
//     in devtools, editable by whoever is holding the tablet.
//   - **This client never writes it.** The write door is `PUT /api/settings` behind an admin
//     session; here there is only a reader and a publisher for what the hub answered.
import { beforeEach, describe, expect, it } from 'vitest';

import { asksForPin, parsePinPolicy, pinPolicy, publishPinPolicy, STRICT_PIN_POLICY } from './pin-policy';

beforeEach(() => {
  pinPolicy.value = STRICT_PIN_POLICY;
  localStorage.clear();
});

describe('the value it starts on', () => {
  it('starts on a position that keeps asking', () => {
    // Before the hub has answered, the screen has to assume the business identifies whoever sells.
    // Assuming the opposite would paint a till with no pinpad for one frame — and one frame is a
    // sale.
    expect(pinPolicy.value).toBe('per_shift');
    expect(asksForPin(pinPolicy.value)).toBe(true);
  });

  it('never starts on «never», whatever else changes', () => {
    expect(STRICT_PIN_POLICY).not.toBe('never');
  });
});

describe('parsePinPolicy', () => {
  it('accepts exactly the three spellings the hub knows', () => {
    expect(parsePinPolicy('always')).toBe('always');
    expect(parsePinPolicy('per_shift')).toBe('per_shift');
    expect(parsePinPolicy('never')).toBe('never');
  });

  it('refuses everything else instead of guessing', () => {
    // No trimming and no case folding, the same closed set as `PinPolicy::parse` in the runtime.
    // Two spellings on the wire would mean the one that slips through is always the lax one.
    for (const candidate of [
      'Never', 'never ', ' never', 'NEVER', 'nunca', 'per shift', 'pershift', 'shift',
      '', ' ', 'always ', null, undefined, 0, 1, true, false, {}, ['never'],
    ]) {
      expect(parsePinPolicy(candidate)).toBeNull();
    }
  });
});

describe('publishPinPolicy', () => {
  it('publishes what the hub said', () => {
    expect(publishPinPolicy('never')).toBe('never');
    expect(pinPolicy.value).toBe('never');

    expect(publishPinPolicy('always')).toBe('always');
    expect(pinPolicy.value).toBe('always');
  });

  it('takes a granted «never» back when the next answer is unreadable', () => {
    publishPinPolicy('never');

    // The hub went away, or answered something this build cannot read. Either way it did not say
    // «never» this time, so the till goes back to asking. A value that survived its own source
    // would be a decision nobody is making any more.
    expect(publishPinPolicy(undefined)).toBe('per_shift');
    expect(pinPolicy.value).toBe('per_shift');
  });

  it('lands on the strict value for anything it cannot read', () => {
    for (const unreadable of ['Never', 'off', '', null, undefined, 0, true, {}]) {
      publishPinPolicy('never');
      expect(publishPinPolicy(unreadable)).toBe('per_shift');
      expect(asksForPin(pinPolicy.value)).toBe(true);
    }
  });

  it('does not remember the answer anywhere the device can edit', () => {
    publishPinPolicy('never');

    // A `never` in `localStorage` would be a switch that removes the pinpad and that anybody
    // holding the tablet can flip in devtools. The hub is asked again, every time.
    expect(JSON.stringify(localStorage)).not.toContain('never');
    expect(localStorage.length).toBe(0);
  });
});

describe('asksForPin', () => {
  it('is false for exactly one position of the dial', () => {
    expect(asksForPin('always')).toBe(true);
    expect(asksForPin('per_shift')).toBe(true);
    expect(asksForPin('never')).toBe(false);
  });
});

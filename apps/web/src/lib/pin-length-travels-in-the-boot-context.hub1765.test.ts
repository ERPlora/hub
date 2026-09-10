// @vitest-environment happy-dom
// ERPlora/hub#1765 — **the login pinpad paints as many circles as THIS hub's PIN has**.
//
// hub#974 made the PIN length a per-hub setting (4 or 6, the same for everybody) and `pin-length.ts`
// reads it from `hubSettings.pin_length`. The catch is where that value came from: only from
// `GET /api/settings`, which needs a session — and the login screen is the one screen that has
// none. Measured on the PRE bench (`banco-pre.a.erplora.com/login`, 2026-09-10): `/api/settings`
// answered `401 falta sesión`, the boot context carried no `pin_length`, and the pinpad fell back
// to the default 4 while the hub's PIN was six digits.
//
// It is not a cosmetic count. `ok-pinpad` fires `ok-complete` on the LAST circle — that is the
// whole reason the length is fixed per hub (`pin-length.ts`: no "OK" key for the cashier to press
// dozens of times a day). Four circles on a six-digit hub therefore submits `2888` for `288806`
// and the hub cannot be signed into by PIN at all.
//
// The fix travels the value in the boot context, the one door the login screen can read with no
// session (`crates/server/tests/pin_length_reaches_the_login_screen_hub1765.rs` pins the other
// half). This file pins the client half: the context's answer reaches `hubSettings`, a hub that
// says nothing keeps the compatibility default, and an answer outside the closed set never
// becomes the pinpad's submit length.
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { hubSettings } from './hub-settings';
import { DEFAULT_PIN_LENGTH, PIN_LENGTHS, hubPinLength } from './pin-length';
import { bootHubContext } from './runtime';

/** The boot context exactly as `GET /api/hub/context` answers it, with `pin_length` overridable. */
function contextAnswers(pinLength: unknown): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        hub_id: 'hub-1',
        user: null,
        pin_users: [],
        currency: 'EUR',
        language: 'es',
        timezone: 'Europe/Madrid',
        ...(pinLength === undefined ? {} : { pin_length: pinLength }),
      }),
    })),
  );
}

beforeEach(() => {
  vi.unstubAllGlobals();
  hubSettings.value = null;
  localStorage.clear();
});

describe('hub#1765 — the login screen learns the PIN length without a session', () => {
  it.each(PIN_LENGTHS)('carries the hub that chose %d digits all the way to the pinpad', async (n) => {
    contextAnswers(n);

    await bootHubContext();

    expect(hubSettings.value?.pin_length).toBe(n);
    // What the pinpad is actually handed: the circles AND the digit it submits on.
    expect(hubPinLength.value).toBe(n);
  });

  it('keeps the compatibility default when the hub says nothing', async () => {
    contextAnswers(undefined);

    await bootHubContext();

    expect(hubPinLength.value).toBe(DEFAULT_PIN_LENGTH);
  });

  it.each([5, 8, 0, -6, '6', null, {}])(
    'never lets %s become the length the pinpad submits on',
    async (bogus) => {
      contextAnswers(bogus);

      await bootHubContext();

      // The set is CLOSED (mirror of `pin_policy::PIN_LENGTHS`). A length nobody can type would
      // leave the pinpad waiting for a digit that never comes, which is a till that cannot open.
      expect(PIN_LENGTHS).toContain(hubPinLength.value);
      expect(hubPinLength.value).toBe(DEFAULT_PIN_LENGTH);
    },
  );

  it('does not lose a length already known when a later context is silent', async () => {
    contextAnswers(6);
    await bootHubContext();
    expect(hubPinLength.value).toBe(6);

    // A second boot whose context could not read the settings row must not silently shorten the
    // PIN back to four: that is the same truncated-login bug wearing a different hat.
    contextAnswers(undefined);
    await bootHubContext();

    expect(hubPinLength.value).toBe(6);
  });
});

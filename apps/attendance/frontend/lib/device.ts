// The mode of THIS device for the time clock (ATTENDANCE-F03): `shared` is the counter POS, never asked
// for a location; `personal` is someone's own phone or laptop, which must be within the workplace
// radius when the business asks for it. Whether a device is one or the other is the platform's to say,
// with the PIN and the trusted device (`base`, phase 2): until it does, every device clocks as the
// shared one — the strict fallback of the old module (an unknown mode never asks for a location).
// The server decides the mode on its own (`services.device_source`), never from what a request says.
import type { Source } from '../operations';

export function deviceMode(): Source {
  return 'shared';
}

/**
 * Whether the Hub tells device modes apart. Not yet (phase 1): «Require location» has nothing to act on,
 * so Settings keeps it off and says why (review of 2026-10-15, finding 6).
 */
export function deviceModesKnown(): boolean {
  return false;
}

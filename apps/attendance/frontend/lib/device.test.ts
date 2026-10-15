// The mode of THIS device for the time clock: `shared` (the counter POS, never asked for a location) or
// `personal` (someone's own phone). Deciding it is the platform's, with the PIN and the trusted device
// (phase 2): until then every device clocks as the shared one, the strict fallback of the old module.
import { describe, expect, it } from 'vitest';

import { deviceMode, deviceModesKnown } from './device';

describe('deviceMode', () => {
  it('is the shared device until the platform knows better', () => {
    expect(deviceMode()).toBe('shared');
  });

  it('says the Hub does not know device modes yet, so asking for the location cannot apply', () => {
    expect(deviceModesKnown()).toBe(false);
  });
});

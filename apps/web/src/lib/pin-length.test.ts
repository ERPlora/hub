// PIN length is the HUB's, not the person's (hub#974).
//
// Market decision (9 references + forums, table in the issue): Clover's model wins — a FIXED length
// per account, 4 or 6, with 6 on new ones. The uniformity is what buys the auto-submitting keypad:
// every product that allows a variable length (Toast 3–8, Lightspeed K 4–6, Shopify 4–6) is forced
// to add a confirm button, and a cashier who signs in dozens of times a day pays that extra tap
// dozens of times a day.
//
// So the shell must ASK the hub instead of hardcoding 4 — which is what it did, in four places.
import { beforeEach, describe, expect, it } from 'vitest';

import { hubSettings } from './hub-settings';
import { hubPinLength, DEFAULT_PIN_LENGTH } from './pin-length';
import { localUserIssue } from './hub-users';

beforeEach(() => {
  hubSettings.value = null;
});

describe('the length the keypad asks for', () => {
  it('follows the hub', () => {
    hubSettings.value = { pin_length: 4 } as never;
    expect(hubPinLength.value).toBe(4);
    hubSettings.value = { pin_length: 6 } as never;
    expect(hubPinLength.value).toBe(6);
  });

  it('defaults to six before the settings land, and refuses a length no POS offers', () => {
    // Not four: a keypad that paints four boxes and then refuses the PIN is worse than one that
    // waits. Six is what a new hub gets, so it is also the honest guess while nothing is known.
    expect(hubPinLength.value).toBe(DEFAULT_PIN_LENGTH);
    expect(DEFAULT_PIN_LENGTH).toBe(6);
    for (const absurd of [1, 3, 5, 7, 8, 12, 0, -4, 4.5]) {
      hubSettings.value = { pin_length: absurd } as never;
      expect(hubPinLength.value, `${absurd} is not a length any POS offers`).toBe(
        DEFAULT_PIN_LENGTH,
      );
    }
  });
});

describe('Personal validates against that same length', () => {
  const person = { name: 'Ana Soto', role: 'employee' };

  it('accepts exactly what the hub asks for and nothing else', () => {
    hubSettings.value = { pin_length: 6 } as never;
    expect(localUserIssue({ ...person, pin: '258013' }, [])).toBe('');
    expect(localUserIssue({ ...person, pin: '2580' }, [])).toBe('pin_length');

    hubSettings.value = { pin_length: 4 } as never;
    expect(localUserIssue({ ...person, pin: '2580' }, [])).toBe('');
    expect(localUserIssue({ ...person, pin: '258013' }, [])).toBe('pin_length');
  });
});

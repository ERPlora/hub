// A phone on screen: the card keeps it in E.164 (`+34600111222`, CUSTOMER-F11) and a person reads it
// with its calling code apart and the digits in groups («+34 600 111 222»). What is not E.164 (an
// old value) is shown as stored.
import { describe, expect, it } from 'vitest';

import { formatPhone } from './phoneDisplay';

describe('formatPhone', () => {
  it('splits the calling code and groups the digits in threes', () => {
    expect(formatPhone('+34600111222')).toBe('+34 600 111 222');
    expect(formatPhone('+447700900123')).toBe('+44 770 090 0123');
    expect(formatPhone('+12025550123')).toBe('+1 202 555 0123');
    expect(formatPhone('+351912345678')).toBe('+351 912 345 678');
    expect(formatPhone('+390612345678')).toBe('+39 061 234 5678');
  });

  it('leaves what is not E.164 as stored, and nothing as nothing', () => {
    expect(formatPhone('600 111 222')).toBe('600 111 222');
    expect(formatPhone('')).toBe('');
    expect(formatPhone(null)).toBe('');
  });
});

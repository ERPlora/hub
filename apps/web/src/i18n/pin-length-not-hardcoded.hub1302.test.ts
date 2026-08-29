// @vitest-environment node
// GUARD for ERPlora/hub#1302 (zero-regression rule, root CLAUDE.md): the PIN's length is a
// per-hub SETTING — 4 or 6, `pin_policy::PIN_LENGTHS`, hub#974 — never a fixed number. A hub with
// `pin_length: 6` showed «Elige un PIN de 4 dígitos» / "Choose a 4-digit PIN" on the very first
// screen a new client sees: the pinpad already asked for six digits (`:length="hubPinLength"`),
// so somebody who typed exactly what the screen told them to got stuck after the fourth.
//
// The only source of truth for how many digits to show is `{n}`, interpolated from
// `hubPinLength` (`lib/pin-length.ts`). This test scans every string of both locales and fails,
// naming the key, if any of them states a digit count as a literal number instead of `{n}`.
import { describe, expect, it } from 'vitest';

import en from './locales/en';
import es from './locales/es';

/** Leaf strings of a locale tree, as `"a.b.c"` -> value. */
function flatten(node: unknown, prefix = ''): Record<string, string> {
  const out: Record<string, string> = {};
  if (node === null || typeof node !== 'object') return out;
  for (const [key, value] of Object.entries(node as Record<string, unknown>)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'string') {
      out[path] = value;
    } else if (value && typeof value === 'object') {
      Object.assign(out, flatten(value, path));
    }
  }
  return out;
}

/**
 * A literal digit count sitting right next to the word for "digit", in either language: `4
 * dígitos`, `4-digit`, `between 4 and 8 digits`. `{n}` never matches — it ends in `}`, not a
 * digit — which is the whole point: interpolation is the only way to say this.
 */
const HARDCODED_DIGIT_COUNT = /\d[\s-]?(?:d[ií]gitos?|digits?)/i;

/**
 * The 2FA email code (ERPlora/saas#994) is a DIFFERENT credential — a one-time OTP with a fixed
 * length of its own that has nothing to do with the hub's PIN policy. Its literal "6" is correct
 * and stays hardcoded on purpose.
 */
const EXEMPT = new Set(['login.twoFactorCodePlaceholder']);

describe('hub#1302 — no locale string hardcodes the PIN digit count', () => {
  it('only {n} may say how many digits THIS hub\'s PIN has', () => {
    for (const [lang, catalogue] of [['en', en], ['es', es]] as const) {
      const leaves = flatten(catalogue);
      for (const [key, value] of Object.entries(leaves)) {
        if (EXEMPT.has(key)) continue;
        expect(
          value,
          `${lang}.${key} hardcodes a PIN digit count: "${value}" — use {n} (hubPinLength), never a literal number`,
        ).not.toMatch(HARDCODED_DIGIT_COUNT);
      }
    }
  });

  it('the exemption is real, not a hole: the 2FA placeholder does hardcode a 6, on purpose', () => {
    // Proves the pattern above can actually catch a positive, and that EXEMPT is not silently
    // swallowing a PIN string too.
    const enLeaves = flatten(en);
    const esLeaves = flatten(es);
    expect(enLeaves['login.twoFactorCodePlaceholder']).toMatch(HARDCODED_DIGIT_COUNT);
    expect(esLeaves['login.twoFactorCodePlaceholder']).toMatch(HARDCODED_DIGIT_COUNT);
  });
});

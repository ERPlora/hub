// @vitest-environment node
// Regression test for ERPlora/hub#1214 — Personal reads the ACCESS-SYNC refusal by code.
//
// Every alta/baja of a user with email notifies the SaaS, which owns access (ADR-0157 §7). When
// that call fails, the runtime used to answer with the raw body of the other system inside a
// Spanish sentence, and Personal painted it:
//
//     el SaaS respondió 429: {"detail":"Request was throttled. Expected available in 2828 seconds."}
//
// The runtime now sends a stable code inside `error` and keeps the foreign body in its log. This
// file guards the OTHER half — the one a Rust test cannot see: that the screen recognises those
// codes and has a sentence for each of them in BOTH languages. Without it the fix would land and
// Personal would still fall back to the runtime's English line.
import { describe, expect, it } from 'vitest';

import en from '../i18n/locales/en';
import es from '../i18n/locales/es';
import { ACCESS_SYNC_ERRORS, HubUsersError, hubUserErrorKey } from './hub-users';

type Catalogue = { employeeForm: { errors: Record<string, string> } };

const CATALOGUES = [
  ['en', (en as unknown as Catalogue).employeeForm.errors],
  ['es', (es as unknown as Catalogue).employeeForm.errors],
] as const;

describe('access-sync refusals reach Personal as a translatable code (hub#1214)', () => {
  it('maps every access-sync code to its own i18n key', () => {
    for (const code of ACCESS_SYNC_ERRORS) {
      expect(hubUserErrorKey(new HubUsersError('plumbing', code)), code).toBe(code);
    }
  });

  it('tells a rate limit apart from a business rejection', () => {
    // Opposite actions for whoever is administering: «wait and retry» vs «fix what you typed».
    expect(hubUserErrorKey(new HubUsersError('x', 'cloud_rate_limited'))).toBe('cloud_rate_limited');
    expect(hubUserErrorKey(new HubUsersError('x', 'cloud_rejected'))).toBe('cloud_rejected');
  });

  it('still reads the business refusals of the core (`hub.users.*`)', () => {
    expect(hubUserErrorKey(new HubUsersError('x', 'hub.users.pin_in_use'))).toBe('pin_in_use');
  });

  it('leaves an unknown code alone, so the sentence that arrived still wins', () => {
    expect(hubUserErrorKey(new HubUsersError('x', 'something_new'))).toBeUndefined();
    expect(hubUserErrorKey(new Error('network'))).toBeUndefined();
  });

  for (const [language, errors] of CATALOGUES) {
    it(`\`${language}\` has a sentence for every access-sync code`, () => {
      for (const code of ACCESS_SYNC_ERRORS) {
        const sentence = errors[code];
        expect(sentence, `${language}.employeeForm.errors.${code} is missing`).toBeTruthy();
        // A sentence that is the code, or that quotes the plumbing, is the defect again.
        expect(sentence).not.toBe(code);
        expect(sentence, `${language}.${code} names the plumbing`).not.toMatch(
          /throttl|SaaS|429|X-Hub-Token|\bDRF\b/i,
        );
      }
    });
  }
});

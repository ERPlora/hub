// @vitest-environment happy-dom
// Regression test for ERPlora/hub#1258, rewritten for ERPlora/hub#1315.
//
// Personal (`EmployeesPage`/`EmployeeFormPage`) and Settings → Roles (`RolesPanel`) already
// translate `hub.users.*` (hub#355), the access-sync family (hub#1214) and `invalid_field`
// (hub#1190/#1241) — but every OTHER code the runtime's authenticated door can answer with
// (`db`, `io`, `wasm`, `native`, `schema`, `manifest`, `module_not_installed`, `module_inactive`,
// `missing_dependency`, `read_unavailable`) fell through to `error.message`, which is the fixed
// ENGLISH line `error_payload` writes for the six plumbing codes (`crates/server/src/lib.rs`,
// `REDACTED_MESSAGE`, hub#1074) or an authored sentence that never went through i18n for the other
// four. A hub in Spanish read English in the middle of Personal.
//
// hub#1258 fixed it by growing a SECOND, byte-identical copy of the two sentences
// `packages/module-sdk/src/index.ts` already had for a module's Web Component (`hub#1102`), keyed
// through vue-i18n instead of the SDK's own table. Two catalogues meant a wording tweak on either
// side would drift the other in silence — and the copy here was missing `manifest`, a code the SDK
// never had to answer before. hub#1315 removes the copy: this file now renders EXACTLY the SDK's
// sentence (`platformFailureMessage` from `@erplora/module-sdk`), so there is exactly one place
// these ten sentences are written. The `instanceof` gate stays the shell's own — the SDK's table
// answers ANY object shape (a module's raw envelope), and this screen only wants it for its own
// two error classes.
import { describe, expect, it } from 'vitest';
import { platformFailureMessage as sdkPlatformFailureMessage } from '@erplora/module-sdk';

import { HubUsersError, RoleActivationError } from './hub-users';
import { platformFailureMessage } from './platform-failure';

/** Every code this family answers — same ten `hub1258` named, now sourced from the SDK's table. */
const PLATFORM_FAILURE_CODES = [
  'db', 'io', 'wasm', 'native', 'schema', 'manifest',
  'module_not_installed', 'module_inactive', 'missing_dependency', 'read_unavailable',
  // hub#2428: an action over the hub's instruction budget — redacted, with its own sentence.
  'wasm_budget_exceeded',
  // hub#2431: an action over the hub's time limit — redacted, with its own sentence.
  'wasm_timeout',
] as const;

describe('platformFailureMessage (hub#1258, hub#1315)', () => {
  it.each(PLATFORM_FAILURE_CODES)(
    'the "%s" code renders EXACTLY the sentence the SDK table produces, in Spanish',
    (code) => {
      const error = new HubUsersError('x', code, undefined, undefined, 'taxes', 'taxes.rules.list');
      const expected = sdkPlatformFailureMessage({ code, module: 'taxes', query: 'taxes.rules.list' }, 'es');
      expect(expected).not.toBeNull();
      expect(platformFailureMessage(error, 'es')).toBe(expected);
    },
  );

  it('the six plumbing codes never leak the redacted English line', () => {
    const error = new HubUsersError(
      'the request could not be completed — the hub recorded the details',
      'db',
    );
    const message = platformFailureMessage(error, 'es');
    expect(message).not.toMatch(/could not be completed/);
  });

  // hub#2410: `reason` says why a `required` read did not resolve, and the SDK picks the sentence
  // by it. Dropping it on the way to the SDK told a screen «the app is missing» when the app was
  // installed and only the read had failed.
  it.each(['query_failed', 'module_inactive', 'module_not_installed'])(
    'passes the `reason` of a `read_unavailable` (%s) through to the SDK',
    (reason) => {
      const error = new HubUsersError('x', 'read_unavailable', undefined, reason, undefined, 'sales.get');
      expect(platformFailureMessage(error, 'es')).toBe(
        sdkPlatformFailureMessage({ code: 'read_unavailable', query: 'sales.get', reason }, 'es'),
      );
    },
  );

  it('names the missing app for `module_not_installed`', () => {
    const error = new HubUsersError('módulo no instalado', 'module_not_installed', undefined, undefined, 'taxes');
    expect(platformFailureMessage(error, 'es')).toBe(
      sdkPlatformFailureMessage({ code: 'module_not_installed', module: 'taxes' }, 'es'),
    );
  });

  it('names the missing app for `missing_dependency` (the envelope already normalises it into `module`)', () => {
    const error = new HubUsersError('falta dependencia', 'missing_dependency', undefined, undefined, 'inventory');
    expect(platformFailureMessage(error, 'es')).toBe(
      sdkPlatformFailureMessage({ code: 'missing_dependency', module: 'inventory' }, 'es'),
    );
  });

  it('falls back to the generic missing-app sentence when the runtime named none', () => {
    const error = new HubUsersError('no instalado', 'module_not_installed');
    expect(platformFailureMessage(error, 'es')).toBe(
      sdkPlatformFailureMessage({ code: 'module_not_installed' }, 'es'),
    );
  });

  it('names the switched-off app for `module_inactive`, a DIFFERENT sentence from "missing"', () => {
    const error = new HubUsersError('desactivado', 'module_inactive', undefined, undefined, 'taxes');
    const off = platformFailureMessage(error, 'es');
    expect(off).toBe(sdkPlatformFailureMessage({ code: 'module_inactive', module: 'taxes' }, 'es'));
    expect(off).not.toBe(sdkPlatformFailureMessage({ code: 'module_not_installed', module: 'taxes' }, 'es'));
  });

  it('derives the app of `read_unavailable` from the query when the envelope names no module', () => {
    const error = new HubUsersError('lectura no disponible', 'read_unavailable', undefined, undefined, undefined, 'taxes.rules.list');
    expect(platformFailureMessage(error, 'es')).toBe(
      sdkPlatformFailureMessage({ code: 'read_unavailable', query: 'taxes.rules.list' }, 'es'),
    );
  });

  it('works the same for RoleActivationError (Settings → Roles)', () => {
    const error = new RoleActivationError('the request could not be completed — the hub recorded the details', 'db');
    expect(platformFailureMessage(error, 'es')).toBe(sdkPlatformFailureMessage({ code: 'db' }, 'es'));
  });

  it('en is the source and es the translation (ADR-0055), not one string', () => {
    const error = new HubUsersError('x', 'db');
    expect(platformFailureMessage(error, 'en')).not.toBe(platformFailureMessage(error, 'es'));
  });

  it('an unmapped code keeps deciding nothing: the caller falls back to the message that arrived', () => {
    expect(platformFailureMessage(new HubUsersError('x', 'hub.users.pin_in_use'), 'es')).toBeUndefined();
    expect(platformFailureMessage(new HubUsersError('x', 'permission_denied'), 'es')).toBeUndefined();
    expect(platformFailureMessage(new Error('network down'), 'es')).toBeUndefined();
  });

  it('an object with a matching `.code` that is NOT one of the shell\'s own error classes is ignored', () => {
    // Unlike the SDK (which answers any object shape — a module's own deserialised envelope), the
    // shell only reads this family off `HubUsersError`/`RoleActivationError`: a coincidental
    // `.code` on an unrelated object must never paint a platform sentence it did not earn.
    expect(platformFailureMessage({ code: 'db' }, 'es')).toBeUndefined();
  });

  it('lists exactly the codes the issue names, so a new RuntimeError variant does not fall through unnoticed', () => {
    for (const code of PLATFORM_FAILURE_CODES) {
      expect(sdkPlatformFailureMessage({ code }, 'es')).not.toBeNull();
    }
  });

  // ── hub#1337 ────────────────────────────────────────────────────────────────────────────────
  //
  // `other` is not part of the ten above and never was: `may_reach_the_client`
  // (`crates/server/src/lib.rs`) lets `E::Other(_)` speak on purpose, and the two `Other(...)`
  // sites Personal can actually hit say «usuario no encontrado» (`crates/runtime/src/hub_users.rs`,
  // `user_profile.rs`). The SDK used to answer them with the generic plumbing line; now it steps
  // aside — but only if it can SEE the sentence, so this bridge has to hand it over. It did not.

  it('hub#1337: an authored `other` keeps the sentence the runtime deliberately let through', () => {
    const error = new HubUsersError('usuario no encontrado', 'other');

    expect(platformFailureMessage(error, 'es')).toBeUndefined();
  });

  it('hub#1337: a REDACTED `other` is still told in the language of whoever is reading', () => {
    // `carries_driver_text` fired: what arrived is the runtime's fixed ENGLISH log line, and the
    // screen must not paint it — the hub#1102 incident, for the one code nobody had covered.
    const error = new RoleActivationError(
      'the request could not be completed — the hub recorded the details',
      'other',
    );

    const message = platformFailureMessage(error, 'es');
    expect(message).toBe(sdkPlatformFailureMessage({ code: 'db' }, 'es'));
    expect(message).not.toMatch(/could not be completed/);
  });
});

// @vitest-environment happy-dom
// Regression test for ERPlora/hub#1258.
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
// `packages/module-sdk/src/index.ts` already solved this exact problem for a module's Web
// Component (`platformFailureMessage`, hub#1102) — but it bakes its two sentences into the SDK file
// itself, not the vue-i18n catalogues the shell already uses, so a screen that called it would
// bypass the parity guard (`locales.parity.test.ts`, hub#1241) and grow a second translation
// mechanism next to `invalidFieldMessage`. This is the shell's own, over `t`/`te`.
import { describe, expect, it } from 'vitest';
import { createI18n } from 'vue-i18n';

import en from '../i18n/locales/en';
import es from '../i18n/locales/es';
import { HubUsersError, RoleActivationError } from './hub-users';
import { PLATFORM_FAILURE_CODES, platformFailureMessage } from './platform-failure';

function translators(locale: 'es' | 'en') {
  const i18n = createI18n({ legacy: false, locale, fallbackLocale: 'en', messages: { es, en } });
  const g = i18n.global as unknown as {
    t: (key: string, params?: Record<string, unknown>) => string;
    te: (key: string) => boolean;
  };
  return { t: g.t.bind(g), te: g.te.bind(g) };
}

const ES = translators('es');
const EN = translators('en');

describe('platformFailureMessage (hub#1258)', () => {
  it.each(['db', 'io', 'wasm', 'native', 'schema', 'manifest'] as const)(
    'the "%s" plumbing code gets the same translated sentence, never the redacted English line',
    (code) => {
      const error = new HubUsersError(
        'the request could not be completed — the hub recorded the details',
        code,
      );
      const message = platformFailureMessage(error, ES.t, ES.te);
      expect(message).toBe(es.platformFailure.unavailable);
      expect(message).not.toMatch(/could not be completed/);
    },
  );

  it('names the missing app for `module_not_installed`', () => {
    const error = new HubUsersError('módulo no instalado', 'module_not_installed', undefined, undefined, 'taxes');
    expect(platformFailureMessage(error, ES.t, ES.te)).toBe(
      es.platformFailure.moduleMissing.replace('{app}', 'taxes'),
    );
  });

  it('names the missing app for `missing_dependency` (the envelope already normalises it into `module`)', () => {
    const error = new HubUsersError('falta dependencia', 'missing_dependency', undefined, undefined, 'inventory');
    expect(platformFailureMessage(error, ES.t, ES.te)).toBe(
      es.platformFailure.moduleMissing.replace('{app}', 'inventory'),
    );
  });

  it('falls back to the generic missing-app sentence when the runtime named none', () => {
    const error = new HubUsersError('no instalado', 'module_not_installed');
    expect(platformFailureMessage(error, ES.t, ES.te)).toBe(es.platformFailure.moduleMissingGeneric);
  });

  it('names the switched-off app for `module_inactive`, a DIFFERENT sentence from "missing"', () => {
    const error = new HubUsersError('desactivado', 'module_inactive', undefined, undefined, 'taxes');
    const off = platformFailureMessage(error, ES.t, ES.te);
    expect(off).toBe(es.platformFailure.moduleInactive.replace('{app}', 'taxes'));
    expect(off).not.toBe(es.platformFailure.moduleMissing.replace('{app}', 'taxes'));
  });

  it('derives the app of `read_unavailable` from the query when the envelope names no module', () => {
    const error = new HubUsersError('lectura no disponible', 'read_unavailable', undefined, undefined, undefined, 'taxes.rules.list');
    expect(platformFailureMessage(error, ES.t, ES.te)).toBe(
      es.platformFailure.moduleMissing.replace('{app}', 'taxes'),
    );
  });

  it('works the same for RoleActivationError (Settings → Roles)', () => {
    const error = new RoleActivationError('the request could not be completed — the hub recorded the details', 'db');
    expect(platformFailureMessage(error, ES.t, ES.te)).toBe(es.platformFailure.unavailable);
  });

  it('en is the source and es the translation (ADR-0055), not one string', () => {
    const error = new HubUsersError('x', 'db');
    expect(platformFailureMessage(error, EN.t, EN.te)).not.toBe(platformFailureMessage(error, ES.t, ES.te));
  });

  it('an unmapped code keeps deciding nothing: the caller falls back to the message that arrived', () => {
    expect(platformFailureMessage(new HubUsersError('x', 'hub.users.pin_in_use'), ES.t, ES.te)).toBeUndefined();
    expect(platformFailureMessage(new HubUsersError('x', 'permission_denied'), ES.t, ES.te)).toBeUndefined();
    expect(platformFailureMessage(new Error('network down'), ES.t, ES.te)).toBeUndefined();
  });

  it('lists exactly the codes the issue names, so a new RuntimeError variant does not fall through unnoticed', () => {
    expect([...PLATFORM_FAILURE_CODES].sort()).toEqual(
      [
        'db',
        'io',
        'wasm',
        'native',
        'schema',
        'manifest',
        'module_not_installed',
        'module_inactive',
        'missing_dependency',
        'read_unavailable',
      ].sort(),
    );
  });
});

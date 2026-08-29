// Translating the core's PLATFORM rejections — the family that is nobody's business rule (hub#1258).
//
// `EmployeesPage`/`EmployeeFormPage`/`RolesPanel` already translate by code for the core's own
// business refusals (`hub.users.*`, hub#355), the access-sync family (`cloud_rate_limited`…,
// hub#1214) and a refused field (`invalid_field`, hub#1190/#1241). What none of them handled is
// the PLATFORM family every authenticated door can answer with: the six codes `error_payload`
// (`crates/server/src/lib.rs`, `may_reach_the_client`) redacts to one fixed ENGLISH line —
// `db`, `io`, `wasm`, `native`, `schema`, `manifest` — plus the four whose remedy names an app —
// `module_not_installed`, `module_inactive`, `missing_dependency`, `read_unavailable`. Falling
// through to `error.message` painted that redacted English line, or an untranslated authored one,
// in the middle of a hub running in Spanish.
//
// `packages/module-sdk/src/index.ts` solved the SAME problem for a module's Web Component
// (`platformFailureMessage`, hub#1102) — but it bakes its two sentences into the SDK file itself,
// keyed by a raw `'en'`/`'es'` string, not the vue-i18n catalogues the shell already uses for every
// other rejection. Reusing it here would grow a second translation mechanism next to
// `invalidFieldMessage`, bypass the parity guard (`locales.parity.test.ts`, hub#1241), and still
// miss `manifest` — a code `may_reach_the_client` redacts exactly like the other five plumbing
// codes, but one the SDK's table never had to cover (it is a module-install-time error only). This
// is the shell's own half, over the same `t`/`te` contract as `invalidFieldMessage`.

import { HubUsersError, RoleActivationError } from './hub-users';

/** The six codes whose `message` is `REDACTED_MESSAGE` (hub#1074): plumbing, not a business rule. */
const PLUMBING_CODES = ['db', 'io', 'wasm', 'native', 'schema', 'manifest'] as const;

/** The four codes whose remedy names an app: install it, switch it back on, or go fetch it. */
const MISSING_APP_CODES = ['module_not_installed', 'missing_dependency', 'read_unavailable'] as const;

const INACTIVE_APP_CODE = 'module_inactive';

/** Every code this module knows how to translate — the exhaustive list `hub1258` proves against. */
export const PLATFORM_FAILURE_CODES: readonly string[] = [
  ...PLUMBING_CODES,
  ...MISSING_APP_CODES,
  INACTIVE_APP_CODE,
];

interface PlatformRejection {
  code: string;
  module?: string;
  query?: string;
}

/** The `(code, module, query)` of a PLATFORM refusal, or `undefined` when this is not one. */
function platformRejectionOf(error: unknown): PlatformRejection | undefined {
  if (!(error instanceof HubUsersError) && !(error instanceof RoleActivationError)) return undefined;
  if (!error.code || !PLATFORM_FAILURE_CODES.includes(error.code)) return undefined;
  return { code: error.code, module: error.module, query: error.query };
}

/**
 * The app id a sentence should send the user after, or `''` when the runtime named none.
 *
 * Mirrors `appOf` in `packages/module-sdk/src/index.ts` (hub#1102): `module` wins when the runtime
 * sent one, and `read_unavailable` falls back to the first segment of the query it could not
 * resolve (`taxes.rules.list` → `taxes`) — the query's OWNER, not the query itself, which is
 * exactly the internal name a person should never have to read (hub#701).
 */
function appOf(rejection: PlatformRejection): string {
  if (rejection.module) return rejection.module;
  return rejection.query?.split('.')[0] ?? '';
}

/**
 * What to TELL the user about a PLATFORM refusal, or `undefined` when this is not one.
 *
 * `undefined` is the answer for a module's own domain code (`hub.users.*`, an `invalid_field`,
 * anything unrecognised) and the caller then keeps trying the other steps of the same chain
 * (`invalidFieldMessage`, `hubUserErrorKey`) or the sentence that arrived — same contract as
 * those two helpers.
 */
export function platformFailureMessage(
  error: unknown,
  t: (key: string, params?: Record<string, unknown>) => string,
  te: (key: string) => boolean,
): string | undefined {
  const rejection = platformRejectionOf(error);
  if (!rejection) return undefined;

  if ((PLUMBING_CODES as readonly string[]).includes(rejection.code)) {
    return te('platformFailure.unavailable') ? t('platformFailure.unavailable') : undefined;
  }

  const app = appOf(rejection);
  const key =
    rejection.code === INACTIVE_APP_CODE
      ? app
        ? 'platformFailure.moduleInactive'
        : 'platformFailure.moduleInactiveGeneric'
      : app
        ? 'platformFailure.moduleMissing'
        : 'platformFailure.moduleMissingGeneric';
  return te(key) ? t(key, app ? { app } : undefined) : undefined;
}

// Bridges the shell's own PLATFORM-refusal error classes to the SDK's shared table
// (`packages/module-sdk/src/index.ts`, `platformFailureMessage`, hub#1102), which already answers
// every code the runtime's authenticated door can produce in this family: the six codes
// `error_payload` (`crates/server/src/lib.rs`, `may_reach_the_client`) redacts to one fixed
// ENGLISH line — `db`, `io`, `wasm`, `native`, `schema`, `manifest` — plus the four whose remedy
// names an app — `module_not_installed`, `module_inactive`, `missing_dependency`,
// `read_unavailable`.
//
// hub#1258 fixed this for `EmployeesPage`/`EmployeeFormPage`/`RolesPanel` by growing a SECOND,
// byte-identical copy of the SDK's two sentences here, keyed through vue-i18n instead of the SDK's
// own `Bilingual` table. Two catalogues meant a wording tweak on either side would drift the other
// in silence, and this copy was missing `manifest` — a code `may_reach_the_client` redacts exactly
// like its five siblings, which the SDK's table now also covers (hub#1315). Reusing the SDK
// directly — rather than mirroring its strings into `i18n/locales/*.ts` — leaves exactly one place
// these ten sentences are written; `locale` picks the language straight out of that table instead
// of round-tripping through `t`/`te`.
import { platformFailureMessage as sdkPlatformFailureMessage, type PlatformFailure } from '@erplora/module-sdk';

import { HubUsersError, RoleActivationError } from './hub-users';

/**
 * The `(code, module, query, message)` of a PLATFORM refusal, or `undefined` when this is not one.
 *
 * `instanceof`, not structural (unlike `fieldRefusalOf` in `invalid-field.ts`): the SDK's table
 * answers ANY object carrying one of its codes — it has to, a module's own deserialised envelope
 * is a plain object — and restricting the lookup to the shell's own error classes keeps an
 * unrelated `Error` with a coincidental `.code` from painting a platform sentence it never earned.
 *
 * hub#1337: the SENTENCE travels too. The ten codes above answer the same thing whatever arrived
 * with them, but `other` does not — `may_reach_the_client` (`crates/server/src/lib.rs`)
 * lets `E::Other(_)` speak on purpose, so the SDK shows the runtime's own sentence («usuario no
 * encontrado») and falls back to the plumbing line only when that sentence was redacted. Dropping
 * the message here left it deciding blind, and Personal painted the generic line over the useful
 * one. Typed wider than `PlatformFailure` (which does not declare `message`: it is part of the
 * frozen kernel surface, `contracts/kernel/sdk.d.ts`) and passed as-is — the SDK reads it.
 */
function platformRejectionOf(
  error: unknown,
): (PlatformFailure & { message: string }) | undefined {
  if (!(error instanceof HubUsersError) && !(error instanceof RoleActivationError)) return undefined;
  return { code: error.code, module: error.module, query: error.query, message: error.message };
}

/**
 * What to TELL the user about a PLATFORM refusal, or `undefined` when this is not one.
 *
 * `undefined` is the answer for a module's own domain code (`hub.users.*`, an `invalid_field`,
 * anything unrecognised) and the caller then keeps trying the other steps of the same chain
 * (`invalidFieldMessage`, `hubUserErrorKey`) or the sentence that arrived — same contract as
 * those two helpers.
 */
export function platformFailureMessage(error: unknown, locale: string): string | undefined {
  const rejection = platformRejectionOf(error);
  if (!rejection) return undefined;
  return sdkPlatformFailureMessage(rejection, locale) ?? undefined;
}

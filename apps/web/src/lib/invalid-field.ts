// Translating the core's `invalid_field` refusals (hub#1190, hub#1241).
//
// The core's own doors — staff, the role catalogue, one's own profile — refuse a field with
// `{code:"invalid_field", field, reason, message}` (hub#1070/#1185, ADR-0398 §6). The `message` is
// the English source: it is the honest fallback for a log, never what a hub in Spanish shows.
//
// The screens branch on `field` + `reason`, both closed sets, and NEVER parse the sentence. That
// is the whole reason #1185 put them on the envelope: a UI that reads prose breaks the day the
// prose is translated (ADR-0055).
//
// The SDK deliberately leaves `invalid_field` alone (`platformFailureMessage`, hub#1102): a module
// Web Component never calls these doors, and a sentence built out of `field` + `reason` in a place
// with no catalogue would say strictly less than the `detail` that arrived. This file is the
// shell's half of that split.

/** A refusal of ONE field, named by data. `reason` is closed; so is `field` per door. */
export interface FieldRefusal {
  field: string;
  reason: string;
}

/** The stable code the core uses for a refused field (ADR-0398 §6). */
const INVALID_FIELD = 'invalid_field';

/** i18n key of the sentence for a `(field, reason)` pair — the precise one. */
export function fieldReasonKey(refusal: FieldRefusal): string {
  return `invalidField.byField.${refusal.field}.${refusal.reason}`;
}

/** i18n key of the sentence for a reason alone — the fallback when the pair has none. */
export function reasonKey(refusal: FieldRefusal): string {
  return `invalidField.byReason.${refusal.reason}`;
}

/**
 * The `(field, reason)` of an `invalid_field` refusal, or `undefined` when this is not one.
 *
 * Structural on purpose (`code`/`field`/`reason`), not `instanceof`: the same envelope reaches the
 * shell through `HubUsersError`, `RoleActivationError` and the SDK's `ErploraError`, and a reader
 * that had to know all three would grow a fourth branch every time a door gets its own client.
 */
export function fieldRefusalOf(error: unknown): FieldRefusal | undefined {
  if (error === null || typeof error !== 'object') return undefined;
  const e = error as { code?: unknown; field?: unknown; reason?: unknown };
  if (e.code !== INVALID_FIELD) return undefined;
  if (typeof e.field !== 'string' || typeof e.reason !== 'string') return undefined;
  if (!e.field || !e.reason) return undefined;
  return { field: e.field, reason: e.reason };
}

/**
 * What to TELL the user about a refused field, or `undefined` when nothing translates it.
 *
 * `undefined` is the honest answer for an unknown reason and the caller then keeps the sentence the
 * runtime sent — same rule as `platformFailureMessage` (hub#1102). Inventing a sentence out of the
 * two words we do recognise would say less than the `detail`, which names the role, the length or
 * the accepted values.
 *
 * `params` covers what the SENTENCE needs and the refusal does not carry — today only the PIN
 * length, which is a setting of the hub (hub#974) and not a property of the refusal.
 */
export function invalidFieldMessage(
  error: unknown,
  t: (key: string, params?: Record<string, unknown>) => string,
  te: (key: string) => boolean,
  params: Record<string, unknown> = {},
): string | undefined {
  const refusal = fieldRefusalOf(error);
  if (!refusal) return undefined;
  for (const key of [fieldReasonKey(refusal), reasonKey(refusal)]) {
    if (te(key)) return t(key, params);
  }
  return undefined;
}

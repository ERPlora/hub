// Where a refusal of the server is painted. `fieldErrors` of the SDK reads a 422 only; the customer
// app also refuses with a 409 that names its field (a group, tag or field name already taken,
// CUSTOMER-F27–F29; a type that cannot change, F29), which belongs under that field too.
import { ApiError } from '@erplora/ui/sdk';

/** Per-field messages of a 422, or of a 409 that names its field; `{}` for anything else. */
export function refusalFields(err: unknown): Record<string, string> {
  if (err instanceof ApiError && (err.status === 422 || err.status === 409) && err.fields) return { ...err.fields };
  return {};
}

/** The message of a refusal no field on screen (`shown`) can carry; `''` when they all can. */
export function refusalOutsideFields(err: unknown, shown: readonly string[]): string {
  if (!err) return '';
  const fields = Object.keys(refusalFields(err));
  if (fields.length && fields.every((field) => shown.includes(field))) return '';
  return err instanceof Error ? err.message : String(err);
}

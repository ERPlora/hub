// The per-field messages of a refused command. The SDK's `fieldErrors` reads only a 422; inventory's
// domain 409s also name their field (a SKU or an EAN-13 taken, a quantity off the unit's step, a unit
// that cannot change while there is stock, not enough stock), and they belong under it too.
import { ApiError } from '@erplora/ui/sdk';

/** Field → message of a 422 or a 409; a nested field («items.0.qty») is also filed under its name. */
export function errorFields(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError) || (error.status !== 422 && error.status !== 409) || !error.fields) return {};
  const out: Record<string, string> = { ...error.fields };
  for (const [path, message] of Object.entries(error.fields)) {
    const name = path.split('.').at(-1) ?? path;
    if (!(name in out)) out[name] = message;
  }
  return out;
}

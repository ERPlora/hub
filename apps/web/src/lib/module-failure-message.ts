// What the person is told when a module action fails (hub#673).
//
// Every install failure looked identical — «No se pudo iniciar la instalación de {name}» — whether
// the machine token was missing, the signature was wrong, the version did not exist, a dependency
// could not be resolved, the SHA-256 did not match or a migration blew up. The runtime says which
// one it was, in the body, with a stable code; the screen threw that away and reached for its own
// line. It is what made the fleet-wide install breakage of 2026-08-09 (saas#1352) invisible: every
// till in the field said «no se puede instalar» and nobody could tell six causes apart.
//
// The rule, and the reason this is not simply «show `e.message`»: show what the SERVER said, and
// only that. When the body could not be read there is no server sentence — only a technical string
// we made up for the logs («request-install sales → 500»), and putting THAT in front of somebody
// running a shop is worse than the generic line.
//
// This also replaces the private `reasonOf` that lived inside `AppsPage`. That helper already knew
// the rule for deactivate/uninstall (hub#314) and install never got it, precisely because it was
// private to one function. One rule, one place, three callers.

import { ModuleActionError } from './runtime';

/** The sentence the runtime sent, or `null` when it did not speak. */
function serverSentence(error: unknown): string | null {
  if (!error || typeof error !== 'object') return null;

  // Install / update: `detail` is set only when the response body could be parsed. `message` is not
  // usable here — it falls back to a technical string on purpose, so the logs keep the status code.
  const detail = (error as { detail?: unknown }).detail;
  if (typeof detail === 'string') return detail;

  // Activate / deactivate / uninstall (hub#314): the convention of `ModuleActionError` is that a
  // `code` means the runtime gave a business reason a person can act on. Without one it is a 500 or
  // a broken connection, and there is nothing to show.
  if (error instanceof ModuleActionError && error.code) return error.message;

  return null;
}

/**
 * The reason a module action failed, in the runtime's own words, or `fallback` when it gave none.
 *
 * A blank or whitespace-only sentence counts as none: an empty toast is a worse answer than a vague
 * one.
 */
export function moduleFailureMessage(error: unknown, fallback: string): string {
  const sentence = serverSentence(error);
  return sentence && sentence.trim() ? sentence : fallback;
}

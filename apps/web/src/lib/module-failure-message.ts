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
import { runtimeErrorKey, type Translator } from './runtime-error-sentence';

/** The facts a translated sentence interpolates, when the error carries them (hub#1620). */
function paramsOf(error: unknown): Record<string, string> | null {
  if (!error || typeof error !== 'object') return null;
  const params = (error as { params?: unknown }).params;
  return params && typeof params === 'object' ? (params as Record<string, string>) : null;
}

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
 *
 * hub#1693: a STABLE CODE comes first. With erplora.com down, installing answers
 * `{"code":"install_cloud_unavailable","error":"cloud: cloud_unreachable"}` — `detail` is
 * sentence-shaped but it is not a sentence, and the toast used to read «cloud: cloud_unreachable».
 * The translator is required, not optional: an optional argument is exactly the silent path a code
 * escapes through.
 */
export function moduleFailureMessage(error: unknown, fallback: string, i18n: Translator): string {
  const key = runtimeErrorKey(error, i18n);
  if (key) {
    // hub#1620: some sentences name facts the runtime sent as data (`core_version_too_old` → the
    // version the app needs and the one this hub runs). That line lives apart, in
    // `runtimeErrorFacts`, so the shared one still reads whole when a door sends the bare code.
    const params = paramsOf(error);
    const withFacts = key.replace(/^runtimeErrors\./, 'runtimeErrorFacts.');
    if (params && withFacts !== key && i18n.te(withFacts)) return i18n.t(withFacts, params);
    return i18n.t(key);
  }

  const sentence = serverSentence(error);
  return sentence && sentence.trim() ? sentence : fallback;
}

/** The stable reason of a download that ran out of time (`install_error_response`, hub#2556). */
const CLOUD_TIMEOUT = 'install_cloud_timeout';

/**
 * `UPDATE_KEPT_PREVIOUS` of `./runtime`, spelled here on purpose: screen tests mock `./runtime`
 * and a mock without that export would throw the moment this module read it.
 */
const KEPT_PREVIOUS = 'module.update_failed_kept_previous';

/**
 * What the person reads when updating `name` did not work (hub#2556).
 *
 * An update the runtime rolled back (`UpdateKeptPreviousError`) is told apart by its CODE, not by
 * `instanceof`: screens mock `./runtime`, and the rule must not depend on which class the mock
 * kept. Its English `message` is for the log; the screen says whether erplora.com ran out of time
 * (try again) or, for any other reason, the honest generic line. Every other failure goes through
 * `moduleFailureMessage`, with the generic line as fallback.
 */
export function updateFailureMessage(error: unknown, name: string, i18n: Translator): string {
  if (error && typeof error === 'object' && (error as { code?: unknown }).code === KEPT_PREVIOUS) {
    const reason = (error as { reason?: unknown }).reason;
    return i18n.t(reason === CLOUD_TIMEOUT ? 'apps.updateTimedOut' : 'apps.updateError', { name });
  }
  return moduleFailureMessage(error, i18n.t('apps.updateError', { name }), i18n);
}

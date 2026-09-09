// The sentence a person reads when the runtime refuses (hub#1693).
//
// Since hub#1689 the cloud-facing doors answer a short STABLE CODE (`cloud_unreachable`) instead of
// `reqwest`'s own Display, which carried the control plane's address. That was the right fix for the
// leak and it moved the problem one floor up: the body stopped being a leaked address and became an
// English word with an underscore, which the back-office screens painted verbatim. `cloud_unreachable`
// is a word the engine and the shell agree on — not something somebody running a shop can act on.
//
// The rule, and the reason this is NOT «always translate»: a code gets a sentence, prose keeps its
// own words. «el SaaS contestó 404 al resolver el blueprint» or «checksum mismatch» say WHICH thing
// broke, and no generic line of ours says more. Only what is SHAPED like a code is replaced, and
// only when the catalogue really has a sentence for it — a code invented next year has no entry, so
// it falls back to the generic line instead of reaching the screen.
//
// The shape follows `retryErrorKey` in `lib/import-retry.ts` (the lib decides the key, the screen
// translates), with the translator injected so no caller has to repeat the `te`/`t` dance.

/** The slice of `vue-i18n` this needs: ask whether a key exists, then read it. */
export type Translator = { t: (key: string) => string; te: (key: string) => boolean };

/** What a stable code looks like: `cloud_unreachable`, `install_cloud_unavailable`, `a.b-c`. */
const CODE_SHAPE = /^[a-z][a-z0-9_.-]*$/;

const NAMESPACE = 'runtimeErrors';

/** The generic line, for when there is nothing honest to show. */
export const RUNTIME_ERROR_DEFAULT_KEY = `${NAMESPACE}.default`;

function trimmed(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const text = value.trim();
  return text ? text : null;
}

/**
 * The text the error carries.
 *
 * `detail` first because that is what the SERVER said; `message` is ours and falls back to a
 * technical line for the logs («request-install sales → 502»).
 */
function textOf(error: unknown): string | null {
  if (typeof error === 'string') return trimmed(error);
  if (!error || typeof error !== 'object') return null;
  return (
    trimmed((error as { detail?: unknown }).detail) ?? trimmed((error as { message?: unknown }).message)
  );
}

/** The stable code the runtime sent, or `null` when what arrived is prose (or nothing). */
function stableCode(error: unknown): string | null {
  if (error && typeof error === 'object') {
    // An explicit `code` beats the message: `InstallFailedError` keeps the status line in
    // `message` for the logs and the branchable fact in `code`.
    const code = trimmed((error as { code?: unknown }).code);
    if (code && CODE_SHAPE.test(code)) return code;
  }
  const text = textOf(error);
  return text && CODE_SHAPE.test(text) ? text : null;
}

/**
 * The catalogue key for the code the runtime sent, or `null` when there is nothing to translate.
 *
 * `null` covers the two cases the caller must treat differently: real prose (keep it) and a code
 * this shell has never heard of (never paint it).
 */
export function runtimeErrorKey(error: unknown, i18n: Translator): string | null {
  const code = stableCode(error);
  if (!code) return null;
  const key = `${NAMESPACE}.${code}`;
  return i18n.te(key) ? key : null;
}

/** The prose the server actually wrote, or `null` when all it sent was a code. */
function serverProse(error: unknown): string | null {
  const text = textOf(error);
  return text && !CODE_SHAPE.test(text) ? text : null;
}

/**
 * What to put on the screen: the translated sentence, else the server's own prose, else the
 * caller's line, else the generic one. Never the code.
 */
export function runtimeErrorSentence(error: unknown, i18n: Translator, fallback?: string): string {
  const key = runtimeErrorKey(error, i18n);
  if (key) return i18n.t(key);
  return serverProse(error) ?? fallback ?? i18n.t(RUNTIME_ERROR_DEFAULT_KEY);
}

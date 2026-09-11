// Why the runtime session ended, when the runtime knows (hub#1801).
//
// `401` is the answer to two different events: a session that ran out of time, and one the plan
// displaced because a second device signed in where the plan covers one. The runtime tells them
// apart with a stable CODE in the body of the refusal (`crates/server/src/auth.rs`), and this is
// the shell's single home for that code — the boundary where an engine fact becomes something a
// screen can explain, and the reason `lib/runtime.ts`, `main.ts` and `LoginPage.vue` all say the
// same word instead of three spellings of it.
//
// The sentence is NOT here (ADR-0055): it lives in `i18n/locales/{en,es}.ts`, so the code travels
// as data and the person reads their own language.

/** The plan covers one device and another one took it over. */
export const SESSION_EVICTED_DEVICE_LIMIT = 'session_evicted_device_limit';

/**
 * The reasons this shell knows how to EXPLAIN. Deliberately a closed list, the same rule
 * `runtime-error-sentence.ts` follows: a code invented for a later release has no sentence in the
 * catalogue, so treating it as a reason would put an English word with underscores on the login
 * screen of somebody running a shop. Unknown means «ordinary expiry» — the hub#846 behaviour,
 * which explains less but never says something false.
 */
const EXPLAINABLE: readonly string[] = [SESSION_EVICTED_DEVICE_LIMIT];

/**
 * The reason inside a refusal body, or `null` when there is nothing to explain.
 *
 * `null` covers all the honest silences: an expiry (`code: "unauthorized"`), a hub older than this
 * shell that answers no code at all, a body that is not even JSON. None of them may become an
 * eviction: the whole point of hub#1801 is that «you were thrown out» and «it's been a while» stop
 * looking alike, and inventing the first one would send somebody to pay for a plan that was never
 * the problem.
 */
export function sessionEndReason(body: unknown): string | null {
  if (!body || typeof body !== 'object') return null;
  const code = (body as { code?: unknown }).code;
  return typeof code === 'string' && EXPLAINABLE.includes(code) ? code : null;
}

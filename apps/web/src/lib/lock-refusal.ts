// hub#2285 — **the brute-force lock says the same thing at every door**: how many minutes to wait.
//
// One lock, four doors: the login pinpad, the badge, the hand-over overlay and the manager's
// approval all spend tries against the runtime's `login_throttle` (per name or badge, and per
// address since hub#2282), and all get the same `429 too_many_attempts` with `retry_after_secs`.
// The sentence is the pinpad's (hub#2283). It deliberately offers no other way in: when the lock is
// on the address, the PIN is locked too, and the refusal cannot tell which lock it was.

/** A sentence a refusal earns: its i18n key and, for the keys that name them, the minutes. */
export interface Refusal {
  key: string;
  /** Whole minutes to wait, for the keys that name them. */
  minutes?: number;
}

/**
 * The sentence for a `too_many_attempts` refusal. The wait is read off `retryAfterSecs`
 * (`RuntimeError`, hub#2283) and rounded UP — never 0 — so nobody retries into a lock that is
 * still on. No usable wait keeps «wait a few minutes».
 */
export function lockRefusal(err: unknown): Refusal {
  const secs = (err as { retryAfterSecs?: unknown } | null)?.retryAfterSecs;
  if (typeof secs !== 'number') return { key: 'login.pinTooManyAttemptsNoWait' };
  return { key: 'login.pinTooManyAttempts', minutes: Math.max(1, Math.ceil(secs / 60)) };
}

/** The two shapes of vue-i18n's `t` this file calls — any catalogue's `t` fits. */
interface Translate {
  (key: string): string;
  (key: string, named: Record<string, unknown>, plural: number): string;
}

/** A {@link Refusal} in words, pluralised by its minutes when it names them. */
export function sayRefusal(t: Translate, { key, minutes }: Refusal): string {
  return minutes === undefined ? t(key) : t(key, { minutes }, minutes);
}

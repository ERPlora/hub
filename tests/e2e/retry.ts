// One more try when a dev server refused the connection. The browser PoC drives runserver (:8000)
// and the SaaS (:8001), and both restart whenever any session saves a `.py` file: a navigation in
// that window fails with `net::ERR_CONNECTION_REFUSED` (PoC report of 2026-10-13). That is retried,
// once by default; an assertion, a timeout or any other error never is, so a real failure still
// fails the first time.

export interface RetryOptions {
  /** Attempts in total, the first included (default 2: one retry). */
  attempts?: number;
  /** Whether a failure deserves another attempt (default `isConnectionRefused`). */
  isRetryable?: (error: unknown) => boolean;
  /** Waits between attempts (default a timer). */
  sleep?: (ms: number) => Promise<void>;
  /** Pause before another attempt, in ms (default 1000: a restarting server is back by then). */
  delayMs?: number;
  /** Told about each failed attempt that is about to be retried (`attempt` starts at 1). */
  onRetry?: (error: unknown, attempt: number) => void;
}

/** Chromium's network errors (`net::ERR_…`) and Node's refused socket (`ECONNREFUSED`). */
const REFUSED = /net::ERR_|ERR_CONNECTION_REFUSED|ECONNREFUSED/;

/** An `Error` from the network, never an assertion (Playwright's carry `matcherResult`). */
export function isConnectionRefused(error: unknown): boolean {
  if (!(error instanceof Error) || error.name === 'AssertionError' || 'matcherResult' in error) return false;
  return REFUSED.test(error.message);
}

const timer = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

/** `fn()`, tried again after `delayMs` while it fails with a retryable error and attempts remain. */
export async function withRetry<T>(fn: (attempt: number) => Promise<T>, options: RetryOptions = {}): Promise<T> {
  const { attempts = 2, isRetryable = isConnectionRefused, sleep = timer, delayMs = 1000, onRetry } = options;
  for (let attempt = 1; ; attempt += 1) {
    try {
      return await fn(attempt);
    } catch (error) {
      if (attempt >= attempts || !isRetryable(error)) throw error;
      onRetry?.(error, attempt);
      await sleep(delayMs);
    }
  }
}

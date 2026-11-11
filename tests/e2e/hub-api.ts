// The hub's API for the e2e helpers (setup and server-side evidence, never the check), and a hub busy for a moment.
// The stack's businesses run with Free's limits (one transaction at once, `base.tenancy.limits`): with the machine
// loaded, the page a spec just opened can hold that place past the server's wait, and the hub answers 503
// `base.hub_busy` («Too many requests. Try again in a moment.»). That answer ran nothing (`HubBusy` is refused before
// any statement: `OperationError.retry_after`), so the same request goes again after the server's `Retry-After`, a few
// times; a hub that stays busy fails, saying so (hub#795). Any other answer is the caller's to check.
import type { BrowserContext } from '@playwright/test';

import { withRetry } from './retry';

/** Tries in all, the first included: about 15 s at most (each try waits up to 2 s for a place, then the pause). */
const HUB_BUSY_TRIES = 6;
/** The pause before another try: the server's `Retry-After` (`RETRY_AFTER_SECONDS`, `base.tenancy.limits`). */
const HUB_BUSY_PAUSE_MS = 1000;

/** The hub still had no place for the request after every try. */
class HubStillBusy extends Error {
  override name = 'HubStillBusy';
}

/** The hub's 503 `base.hub_busy`: its error envelope, never another 503 (a business being moved, a database down). */
function isHubBusy(status: number, data: unknown): boolean {
  return status === 503 && (data as { error?: { code?: unknown } } | null)?.error?.code === 'base.hub_busy';
}

/** The demo's API with the context's session (setup and server-side evidence, never the check). */
export async function api<T>(
  context: BrowserContext,
  origin: string,
  method: 'GET' | 'POST',
  path: string,
  body?: unknown,
): Promise<{ status: number; data: T }> {
  // The context also holds the SaaS's cookies (host `localhost`), and Playwright hands them to
  // `a.localhost` too: the token is the hub host's own.
  const host = new URL(origin).hostname;
  const cookies = await context.cookies(origin);
  const csrf = cookies.find((c) => c.name === 'csrftoken' && c.domain === host)?.value ?? '';
  const url = `${origin}/api${path}`;
  const headers = { 'X-CSRFToken': csrf, Accept: 'application/json' };
  const route = `${method} /api${path}`;
  return withRetry(
    async (attempt) => {
      const res =
        method === 'GET'
          ? await context.request.get(url, { headers })
          : await context.request.post(url, { headers, data: body ?? {} });
      const text = await res.text();
      const answer = { status: res.status(), data: (text ? JSON.parse(text) : null) as T };
      if (isHubBusy(answer.status, answer.data)) {
        throw new HubStillBusy(`${route}: the hub was still busy after ${attempt} tries, ${HUB_BUSY_PAUSE_MS} ms apart: ${answer.status} ${text}`);
      }
      return answer;
    },
    {
      attempts: HUB_BUSY_TRIES,
      isRetryable: (error) => error instanceof HubStillBusy,
      delayMs: HUB_BUSY_PAUSE_MS,
      onRetry: (_error, attempt) =>
        console.warn(`${route}: the hub is busy (503 base.hub_busy); trying again in ${HUB_BUSY_PAUSE_MS} ms (${attempt + 1} of ${HUB_BUSY_TRIES})`),
    },
  );
}

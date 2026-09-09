/**
 * **Dead-letter signal for the topbar bell** (hub#660). The shell's notification bell already
 * existed as a stub reading `notificationCount` — it was waiting for a backend signal. This is it.
 *
 * The bell answers one question — "did something fail that an admin needs to look at?" — by polling
 * `GET /api/hub/events/dead/count`, the cheap number (no payloads). When it is > 0, the operator
 * clicks through to the System → Events tab, where the queue, the retry (one and all) and discard
 * live. The hub never stays silently stuck behind an event nothing can move.
 *
 * Polling, not a socket: the count is a coarse health signal, not live data, and the dead-letter is
 * the slow lane (a row only dies after 8 retries over minutes). A 60 s cadence catches it well
 * before a human would, without keeping a channel open for a number that barely moves.
 */
import { isAuthed, isAdmin } from './session';
import { runtimeHeaders } from './runtime';
import { setNotificationCount } from './shell';

/** Poll cadence. Coarse on purpose — see module docs. */
const POLL_MS = 60_000;

/** Last count seen, so the bell survives navigation without an extra fetch. */
let lastCount = 0;

/**
 * Ask the runtime how many dead-letters this hub has and feed the bell. Never throws: a fetch that
 * fails (runtime restarting, tab offline) leaves the bell at its last known value rather than
 * flashing zero — a transient network blip must not read as "all clear".
 */
export async function refreshDeadLetterCount(): Promise<void> {
  // Only an admin can do anything about a dead-letter, so only an admin sees the badge. The runtime
  // revalidates the role on the endpoint, so this is a UI guard, not a security one.
  if (!isAuthed.value || !isAdmin.value) {
    if (lastCount !== 0) {
      lastCount = 0;
      setNotificationCount(0);
    }
    return;
  }
  try {
    const res = await fetch('/api/hub/events/dead/count', { headers: runtimeHeaders() });
    const body = (await res.json()) as { ok?: boolean; data?: { count?: number } };
    const n = body?.data?.count ?? 0;
    lastCount = n;
    setNotificationCount(n);
  } catch {
    // Leave the bell where it was: a dead runtime is not a clean bill of health.
  }
}

let watching = false;
let timer: ReturnType<typeof setInterval> | null = null;

/**
 * Start polling: once now, then every {@link POLL_MS} while the tab is visible. Idempotent, so the
 * `isAuthed` watcher re-entering on navigation does not start a second clock. Started from
 * `App.vue`'s `gateAndRefresh`, exactly like `bootAppUpdateWatch`.
 */
export function bootDeadLetterWatch(): void {
  if (watching) return;
  watching = true;
  void refreshDeadLetterCount();
  timer = setInterval(() => {
    // No point hammering the runtime from a background tab the operator is not looking at — the
    // first switch back refreshes immediately.
    if (document.visibilityState === 'visible') void refreshDeadLetterCount();
  }, POLL_MS);
  document.addEventListener('visibilitychange', onVisible);
}

function onVisible(): void {
  if (document.visibilityState === 'visible') void refreshDeadLetterCount();
}

/** Stop polling and clear the badge (e.g. on logout). Leaves `watching` so a re-boot is a no-op. */
export function stopDeadLetterWatch(): void {
  if (timer) clearInterval(timer);
  timer = null;
  document.removeEventListener('visibilitychange', onVisible);
  watching = false;
  lastCount = 0;
  setNotificationCount(0);
}

// ── The queue + the three operator gestures (hub#660) ────────────────────────────────────────
//
// The bell only signals trouble; the System → Events tab is where an operator decides what to do.
// These wrap the same REST endpoints: list the dead-letters (with their payload, so the operator
// can tell a lost invoice from noise), retry one back to the relay, retry all at once (the case a
// transient outage killed several), or discard one for good. The runtime revalidates admin on each.

/** A dead-letter row, as returned by `GET /api/hub/events/dead`. */
export interface DeadEvent {
  id: string;
  event_name: string;
  module_id: string;
  user_id: string;
  payload: unknown;
  last_error: string;
  attempts: number;
  depth: number;
  created_at: string;
  /**
   * Why the row is terminal, when the answer is not "it burnt its eight attempts" (hub#827).
   * Empty for an ordinary dead-letter; `flow.release_revoked` when the owner withdrew a flow's
   * authorisation while the message was still queued.
   */
  failure_kind: string;
  /**
   * Whether `POST …/retry` can do anything with this row. **The screen must not offer a button
   * that cannot work**: retrying a revoked release answered `200`, reset the attempts and died
   * again for the same reason — a loop with no exit, drawn as the remedy. When this is `false`
   * the row is shown with what WOULD help instead (grant the permission again and run the flow).
   */
  retryable: boolean;
}

/** Generic envelope unwrap for the dead-letter endpoints (all return `{ ok, data }` on success). */
/**
 * The refusal a door gave, with its code (hub#1697).
 *
 * The code is the only part a screen can show: the `message` beside it is written for whoever
 * debugs («this dead-letter cannot be replayed: the authorisation that produced it was
 * withdrawn…»), and it mixes languages because it was never meant for a shop owner.
 */
export class DeadLetterError extends Error {
  readonly code?: string;

  constructor(message: string, code?: string) {
    super(message);
    this.name = 'DeadLetterError';
    this.code = code;
  }
}

async function unwrap<T>(res: Response): Promise<T> {
  const body = (await res.json()) as {
    ok?: boolean;
    data?: T;
    error?: { message?: string; code?: string };
  };
  if (!res.ok || !body.ok) {
    const msg = body?.error?.message ?? `error ${res.status}`;
    throw new DeadLetterError(msg, body?.error?.code);
  }
  return body.data as T;
}

/** The dead-letter queue of this hub, newest first. */
export async function fetchDeadLetters(): Promise<DeadEvent[]> {
  const res = await fetch('/api/hub/events/dead', { headers: runtimeHeaders() });
  return unwrap<DeadEvent[]>(res);
}

/** Retry one dead-letter back onto the relay. Throws on a non-dead id / auth failure. */
export async function retryDeadLetter(id: string): Promise<void> {
  const res = await fetch(`/api/hub/events/${encodeURIComponent(id)}/retry`, {
    method: 'POST',
    headers: runtimeHeaders(),
  });
  await unwrap<unknown>(res);
}

/** Retry EVERY dead-letter of this hub at once. Returns how many moved. */
export async function retryAllDeadLetters(): Promise<number> {
  const res = await fetch('/api/hub/events/retry-all', {
    method: 'POST',
    headers: runtimeHeaders(),
  });
  const data = await unwrap<{ retried: number }>(res);
  return data.retried;
}

/** Close a dead-letter for good (the row is kept, auditable — never deleted). */
export async function discardDeadLetter(id: string): Promise<void> {
  const res = await fetch(`/api/hub/events/${encodeURIComponent(id)}/discard`, {
    method: 'POST',
    headers: runtimeHeaders(),
  });
  await unwrap<unknown>(res);
}

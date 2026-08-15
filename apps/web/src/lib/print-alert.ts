/**
 * **Undrained printing, on the bell** (hub#987, market decision of hub#457).
 *
 * The runtime has known this for a while: `print_hosts::coverage` reports, per station, how much is
 * waiting and how many hosts are live, and `waiting > 0` with `liveHosts: 0` means exactly one
 * thing since stations became rows — the till is off. What was missing was anybody being told.
 * `lib/print-coverage.ts` paints it beautifully in **Settings › Receipts**, which is a tab nobody
 * opens in the middle of a service; meanwhile the POS keeps charging, the sale closes with a 200,
 * and the only symptom is paper that never comes out in another room.
 *
 * So this is the same fact, on the surface that is visible from every screen. Toast prints to every
 * station rather than lose a ticket, Simphony flashes when it gets no confirmation, and Square
 * stopped bleeding customers the day it started saying "this receipt may not have printed". The
 * silent version is Clover's and Loyverse's, and their forums are the documentation of why.
 *
 * ## Why the bell and not the setup checklist
 *
 * ADR-0067 split the two surfaces by asking what kind of thing the warning is. "You have not
 * configured X" is derived state that self-heals by configuring, and it belongs on the dashboard
 * checklist. This is not that: the hub *is* configured, and what is wrong is happening **now**. It
 * is the same shape as the dead-letter count (hub#660) that already lives on the bell — something
 * failed, somebody has to go and do something, and it clears itself when they do.
 *
 * It does keep the checklist's honesty about dismissal: there is no "mark as read", because the
 * state IS the notification. You clear it by turning the till back on.
 *
 * ## Not admin-only, and that is the substantive difference with the dead-letter
 *
 * A dead event needs an admin. A queue nobody is draining needs whoever is standing at the counter:
 * they are the one who can switch the till back on, and they are the one about to hand a customer
 * no receipt. The runtime endpoint is a plain user session for the same reason.
 */
import { isAuthed } from './session';
import { runtimeHeaders } from './runtime';
import { setNotificationCount } from './shell';
import { ref } from 'vue';

/**
 * Poll cadence. Faster than the dead-letter's 60 s, and deliberately: a dead-letter is the slow
 * lane (a row only dies after 8 retries over minutes), while an unprinted kitchen order is measured
 * against a customer who is already waiting. Still a poll and not a socket — it is a coarse health
 * signal, not live data.
 */
const POLL_MS = 30_000;

/** A station that is stuck, as `GET /api/print/undrained` reports it. */
export interface UndrainedStation {
  /** The station's wire key (`kitchen`). */
  role: string;
  /** Jobs still `pending` there. */
  waiting: number;
  /** Always `0` for a row that reaches here — kept so the row reads on its own. */
  liveHosts: number;
  /** How long the OLDEST of them has been waiting. What the screen turns into "for 4 minutes". */
  waitingSeconds: number;
}

/**
 * The stalled stations, for the popover row. Separate from the count because the badge needs a
 * number and the row needs to name the kitchen: "3 tickets waiting" is a fact the operator can act
 * on, "1 notification" is not.
 */
export const undrainedStations = ref<UndrainedStation[]>([]);

const str = (v: unknown): string => (typeof v === 'string' ? v : '');
const num = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : 0);

/**
 * Ask the runtime what is not draining and feed the bell. **Never throws**: a fetch that fails
 * (runtime restarting, tab offline) leaves the bell at its last known value rather than flashing
 * zero. A transient blip must not read as "all clear" — the same rule `fetchPrintHosts` follows,
 * and the reason it throws rather than resolving empty.
 */
export async function refreshUndrainedPrinting(): Promise<void> {
  if (!isAuthed.value) {
    undrainedStations.value = [];
    setNotificationCount(0, 'printing');
    return;
  }
  try {
    const res = await fetch('/api/print/undrained', { headers: runtimeHeaders() });
    const body = (await res.json()) as {
      ok?: boolean;
      count?: number;
      stations?: Record<string, unknown>[];
    };
    if (body?.ok !== true) return; // a refusal is not news; leave the bell where it was
    undrainedStations.value = (body.stations ?? []).map((s) => ({
      role: str(s.role),
      waiting: num(s.waiting),
      liveHosts: num(s.liveHosts),
      waitingSeconds: num(s.waitingSeconds),
    }));
    setNotificationCount(body.count ?? 0, 'printing');
  } catch {
    // Leave it: a runtime we cannot reach is not a hub whose printers are fine.
  }
}

let watching = false;
let timer: ReturnType<typeof setInterval> | null = null;

/**
 * Start polling: once now, then every {@link POLL_MS} while the tab is visible. Idempotent, so the
 * `isAuthed` watcher re-entering on navigation does not start a second clock. Started from
 * `App.vue`, exactly like `bootDeadLetterWatch`.
 */
export function bootUndrainedPrintingWatch(): void {
  if (watching) return;
  watching = true;
  void refreshUndrainedPrinting();
  timer = setInterval(() => {
    // No point hammering the runtime from a background tab nobody is looking at — switching back
    // refreshes immediately.
    if (document.visibilityState === 'visible') void refreshUndrainedPrinting();
  }, POLL_MS);
  document.addEventListener('visibilitychange', onVisible);
}

function onVisible(): void {
  if (document.visibilityState === 'visible') void refreshUndrainedPrinting();
}

/** Stop polling and clear this source's badge (e.g. on logout). */
export function stopUndrainedPrintingWatch(): void {
  if (timer) clearInterval(timer);
  timer = null;
  document.removeEventListener('visibilitychange', onVisible);
  watching = false;
  undrainedStations.value = [];
  setNotificationCount(0, 'printing');
}

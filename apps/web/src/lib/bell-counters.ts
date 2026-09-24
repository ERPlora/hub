/**
 * **Module counters on the bell** (hub#1678).
 *
 * The bell knew two sources, each wired into the shell by hand: dead letters (hub#660) and stalled
 * printing (hub#987). With «I review them first» on WhatsApp, an appointment a customer asked for
 * sat as pending and the owner only found out by opening the diary — the customer waited for a
 * confirmation that came whenever somebody happened to look.
 *
 * Wiring appointments in by hand would teach the core what an appointment is. So the bell reads
 * a manifest block instead, the same way the dashboard reads `widgets` (ADR-0054): a module
 * declares, under `bell`, a query of its own whose first row carries `count`, and the tab it
 * leads to. The shell runs it, sums the counts into the `modules` source and paints one row per
 * counter. Reservations, purchasing or anyone else can raise their own without touching the core.
 *
 * Same rules as the other two sources: derived state with no read/dismiss (ADR-0067 — it clears
 * when the cause is dealt with), a poll and not a socket, and a failed fetch keeps the last known
 * value instead of flashing zero.
 */
import { ref, watch, type WatchStopHandle } from 'vue';
import type { BellManifestDef, ModuleManifest } from '@erplora/module-types';

import { normalizeRows } from './dashboard-widgets';
import { loadInstalledManifests } from './module-loader';
import { getClient } from './runtime';
import { hasPermission, isAuthed, user } from './session';
import { setNotificationCount } from './shell';

/** Poll cadence: the same as stalled printing — a customer is waiting on the other end. */
const POLL_MS = 30_000;

/** One row of the bell, as the popover paints it. */
export interface BellCounter {
  /** Full id of the counter in the manifest (`appointments.to_confirm`). */
  key: string;
  /** Already translated to the active language. */
  label: string;
  icon?: string;
  count: number;
  /** Where the row leads: always a tab of the module that raised it. */
  path: string;
}

/** The counters with something waiting, for the popover. */
export const bellCounters = ref<BellCounter[]>([]);

/** Last count seen per counter, so a failed query keeps its value instead of reading as zero. */
let lastCounts = new Map<string, number>();

/**
 * Bumped by every refresh. A pass that was overtaken (the cashier changed while its queries were in
 * flight) drops its result: it was filtered with the previous person's permissions.
 */
let generation = 0;

function countOf(result: unknown): number {
  const raw = normalizeRows(result)[0]?.count;
  const n = typeof raw === 'string' && raw.trim() !== '' ? Number(raw) : raw;
  return typeof n === 'number' && Number.isFinite(n) ? Math.max(0, Math.trunc(n)) : 0;
}

function publish(counters: BellCounter[]): void {
  bellCounters.value = counters;
  setNotificationCount(
    counters.reduce((sum, c) => sum + c.count, 0),
    'modules',
  );
}

/**
 * Run every `bell` counter the session may see and feed the bell. **Never throws.**
 */
export async function refreshBellCounters(): Promise<void> {
  const pass = ++generation;
  if (!isAuthed.value) {
    lastCounts = new Map();
    publish([]);
    return;
  }
  let mods;
  try {
    mods = await loadInstalledManifests();
  } catch {
    return; // no manifests is not "nothing waiting"
  }
  if (pass !== generation) return;
  const client = getClient();
  const next = new Map<string, number>();
  const counters: BellCounter[] = [];

  for (const mod of mods) {
    const block = (mod.manifest as ModuleManifest).bell;
    if (!block) continue;
    for (const [key, def] of Object.entries(block) as [string, BellManifestDef][]) {
      if (!def?.label || !def.query) continue;
      // A module counts ITS data. Another module's query would let one app surface (and point
      // the bell at) what belongs to another.
      if (!def.query.startsWith(`${mod.moduleId}.`)) continue;
      if (def.permission && !hasPermission(def.permission)) continue;

      let count: number;
      try {
        count = countOf(await client.query(def.query, def.params ?? {}));
      } catch {
        count = lastCounts.get(key) ?? 0;
      }
      if (pass !== generation) return;
      next.set(key, count);
      if (count === 0) continue;

      const base = `/m/${encodeURIComponent(mod.moduleId)}`;
      counters.push({
        key,
        label: mod.locale?.bell?.[key]?.label ?? def.label,
        icon: def.icon,
        count,
        path: def.nav ? `${base}/${encodeURIComponent(def.nav)}` : base,
      });
    }
  }
  lastCounts = next;
  publish(counters);
}

let watching = false;
let timer: ReturnType<typeof setInterval> | null = null;
let stopUserWatch: WatchStopHandle | null = null;

function onVisible(): void {
  if (document.visibilityState === 'visible') void refreshBellCounters();
}

/**
 * Start polling: once now, then every {@link POLL_MS} while the tab is visible. Idempotent, like
 * `bootUndrainedPrintingWatch`, and started from the same place in `App.vue`.
 */
export function bootBellCountersWatch(): void {
  if (watching) return;
  watching = true;
  void refreshBellCounters();
  timer = setInterval(() => {
    if (document.visibilityState === 'visible') void refreshBellCounters();
  }, POLL_MS);
  document.addEventListener('visibilitychange', onVisible);
  // A PIN hand-over swaps the user without a logout (`user-switch.ts`): repaint for the one who
  // arrived now, not at the next poll.
  stopUserWatch = watch(
    () => user.value?.id,
    () => void refreshBellCounters(),
  );
}

/** Stop polling and clear this source (e.g. on logout). */
export function stopBellCountersWatch(): void {
  if (timer) clearInterval(timer);
  timer = null;
  document.removeEventListener('visibilitychange', onVisible);
  stopUserWatch?.();
  stopUserWatch = null;
  watching = false;
  generation++;
  lastCounts = new Map();
  publish([]);
}

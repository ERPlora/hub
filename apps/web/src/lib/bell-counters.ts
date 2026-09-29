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
 *
 * **A counter that goes UP is also announced** (hub#2303): the bell only works for whoever looks at
 * it, and a tablet propped on the counter or a phone in a pocket never does. Every rise between two
 * polls reaches the {@link onBellCounterRise} listeners — `lib/bell-notice.ts` turns it into a
 * system notice. What was already waiting at the first poll of a session is the backlog, not news,
 * and is never announced.
 */
import { ref, watch, type WatchStopHandle } from 'vue';
import type { BellManifestDef, ModuleManifest } from '@erplora/module-types';

import { normalizeRows } from './dashboard-widgets';
import { loadInstalledManifests, type InstalledManifest } from './module-loader';
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

/** A counter that went up between two polls (hub#2303). */
export interface BellCounterRise extends BellCounter {
  /** The module that declared the counter. */
  moduleId: string;
  /** The count at the previous poll, lower than {@link BellCounter.count}. */
  previous: number;
}

const riseListeners = new Set<(rise: BellCounterRise) => void>();

/** Be told of every counter that goes up. Returns the function that stops it. */
export function onBellCounterRise(listener: (rise: BellCounterRise) => void): () => void {
  riseListeners.add(listener);
  return () => {
    riseListeners.delete(listener);
  };
}

function announce(rise: BellCounterRise): void {
  for (const listener of riseListeners) {
    try {
      listener(rise);
    } catch (e) {
      // A listener's failure is its own: the bell and the other listeners carry on.
      console.warn('[bell-counters]', e);
    }
  }
}

/** Last count seen per counter, so a failed query keeps its value instead of reading as zero. */
let lastCounts = new Map<string, number>();

/**
 * Bumped by every refresh. A pass that was overtaken (the cashier changed while its queries were in
 * flight) drops its result: it was filtered with the previous person's permissions.
 */
let generation = 0;

/**
 * A counter the bell will run: it has words to paint and a query of its own. A module counts ITS
 * data — another module's query would let one app surface (and point the bell at) what belongs to
 * another.
 */
function isRunnableCounter(moduleId: string, def: BellManifestDef | undefined): def is BellManifestDef {
  return Boolean(def?.label && def.query && def.query.startsWith(`${moduleId}.`));
}

/**
 * The modules that put at least one counter on the bell (hub#2306), by the same rule the poll uses
 * to run them. Whatever the session may see: this answers «does this DEVICE have anything that
 * would ever send a notice», which is asked before knowing who will be standing at it.
 */
export function bellCounterModuleIds(mods: readonly InstalledManifest[]): Set<string> {
  const ids = new Set<string>();
  for (const mod of mods) {
    const block = (mod.manifest as ModuleManifest).bell;
    if (!block) continue;
    if (Object.values(block).some((def) => isRunnableCounter(mod.moduleId, def as BellManifestDef))) {
      ids.add(mod.moduleId);
    }
  }
  return ids;
}

/** {@link bellCounterModuleIds} of what is installed now. **Never throws**: unread is «none». */
export async function loadBellCounterModuleIds(): Promise<Set<string>> {
  try {
    return bellCounterModuleIds(await loadInstalledManifests());
  } catch {
    return new Set();
  }
}

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
  const rises: BellCounterRise[] = [];

  for (const mod of mods) {
    const block = (mod.manifest as ModuleManifest).bell;
    if (!block) continue;
    for (const [key, def] of Object.entries(block) as [string, BellManifestDef][]) {
      if (!isRunnableCounter(mod.moduleId, def)) continue;
      if (def.permission && !hasPermission(def.permission)) continue;

      const previous = lastCounts.get(key);
      let count: number;
      let known = true;
      try {
        count = countOf(await client.query(def.query, def.params ?? {}));
      } catch {
        count = previous ?? 0;
        // Nothing known yet stays unknown: the backlog this recovers into is not a rise.
        known = previous !== undefined;
      }
      if (pass !== generation) return;
      if (known) next.set(key, count);
      if (count === 0) continue;

      const base = `/m/${encodeURIComponent(mod.moduleId)}`;
      const counter: BellCounter = {
        key,
        label: mod.locale?.bell?.[key]?.label ?? def.label,
        icon: def.icon,
        count,
        path: def.nav ? `${base}/${encodeURIComponent(def.nav)}` : base,
      };
      counters.push(counter);
      // A counter this session had not read before (first poll, a login, a permission just
      // gained) sets the baseline; only a rise against a count already read is news.
      if (previous !== undefined && count > previous) {
        rises.push({ ...counter, moduleId: mod.moduleId, previous });
      }
    }
  }
  lastCounts = next;
  publish(counters);
  rises.forEach(announce);
}

let watching = false;
let timer: ReturnType<typeof setInterval> | null = null;
let stopUserWatch: WatchStopHandle | null = null;

function onVisible(): void {
  if (document.visibilityState === 'visible') void refreshBellCounters();
}

/**
 * Start polling: once now, then every {@link POLL_MS}. Idempotent, like
 * `bootUndrainedPrintingWatch`, and started from the same place in `App.vue`.
 *
 * Unlike the other two sources it keeps polling with the window HIDDEN (hub#2303): a minimised
 * window or the app in the background is exactly when a rise has to become a system notice. A
 * browser throttles a hidden tab's timers on its own; coming back still refreshes at once.
 */
export function bootBellCountersWatch(): void {
  if (watching) return;
  watching = true;
  void refreshBellCounters();
  timer = setInterval(() => void refreshBellCounters(), POLL_MS);
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

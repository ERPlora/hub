/**
 * **«N apps have a new version» on the bell** (hub#1172).
 *
 * A hub ran 9 apps behind the marketplace and the owner had no way of knowing: the one place that
 * said «Update to X» was Apps → «My apps», per row, and nobody opens that screen to check. The bell
 * is where the shell already says «something here needs you» from any screen, so the pending
 * updates go there as ONE aggregated row that leads to «My apps», where each update is one tap.
 *
 * Same rules as the other sources (`dead-letter.ts`, `bell-counters.ts`):
 *  - **derived state, no read/dismiss** (ADR-0067): it clears when the apps are updated;
 *  - **only what can be acted on**: only an admin can update an app, so only an admin sees it, and
 *    an update that needs a newer ERPlora (hub#2082) is not counted — the owner could never clear it;
 *  - **a failed check keeps the last known count**: «I don't know» is neither news nor all-clear.
 *    A check the runtime answered with apps it could not ask the marketplace about (`checked:
 *    false`, hub#2336) is a failed check too, and the bell says so ({@link moduleUpdatesUnknown})
 *    with a «Check again» ({@link retryModuleUpdateNotice}).
 *
 * **Hours apart, never a fast poll.** `GET /api/modules/updates` asks the marketplace once per
 * installed app (hub#516). It is checked when the admin session starts, on a PIN hand-over, and
 * every {@link RECHECK_MS} while the tab is visible — module releases are counted in days. The Apps
 * screen publishes what it learns through {@link publishModuleUpdates}, so updating there clears
 * the notice at once instead of at the next check.
 */
import { readonly, ref, watch, type WatchStopHandle } from 'vue';

import { hasUncheckedUpdates, updateNeedsNewerHub, type ModuleUpdateInfo } from './module-updates';
import { listModuleUpdates } from './runtime';
import { isAdmin, isAuthed, user } from './session';
import { notificationCountOf, setNotificationCount } from './shell';
import { fetchSystemInfo } from './system';

/** Where the notice leads: the «My apps» tab of the Apps screen. */
export const MODULE_UPDATES_ROUTE = '/apps#mine';

/** Re-check cadence while the tab is visible. See the module docs for why it is hours. */
const RECHECK_MS = 6 * 60 * 60_000;

/**
 * Bumped by every refresh (and by stop). A check that was overtaken — the admin handed over to a
 * cashier while it was in flight — drops its result instead of painting it for the wrong person.
 */
let generation = 0;

/** How many installed apps have an update this hub can apply today. */
export function actionableUpdateCount(
  updates: readonly ModuleUpdateInfo[],
  hubVersion: string | null | undefined,
): number {
  return updates.filter((u) => u.update_available && !updateNeedsNewerHub(u, hubVersion)).length;
}

function publish(n: number): void {
  setNotificationCount(n, 'moduleUpdates');
}

const unknown = ref(false);
const checking = ref(false);
/** Checks still out. An overtaken check still gives «Check again» back when it lands. */
let inFlight = 0;

/**
 * The last check could not say whether the apps are up to date (hub#2336): the runtime or the
 * marketplace did not answer. The bell says so instead of «All caught up». Only ever `true` for an
 * admin — the only one who could act on it.
 */
export const moduleUpdatesUnknown = readonly(unknown);

/** A check is out: «Check again» is off and reads «Checking…». */
export const moduleUpdatesChecking = readonly(checking);

/**
 * Paint one answer. A fully answered check replaces the count; one with apps the marketplace was
 * not asked about keeps the last known count — raised, never lowered, by the updates it did find.
 */
function paint(updates: readonly ModuleUpdateInfo[], hubVersion: string | null | undefined): void {
  const known = actionableUpdateCount(updates, hubVersion);
  if (hasUncheckedUpdates(updates)) {
    unknown.value = true;
    publish(Math.max(known, notificationCountOf('moduleUpdates')));
    return;
  }
  unknown.value = false;
  publish(known);
}

/**
 * What the Apps screen just learnt from `GET /api/modules/updates`. It replaces the notice at once,
 * so an update applied there clears the bell without waiting for the next check.
 */
export function publishModuleUpdates(
  updates: readonly ModuleUpdateInfo[],
  hubVersion: string | null | undefined,
): void {
  if (!isAdmin.value) {
    unknown.value = false;
    publish(0);
    return;
  }
  generation++;
  paint(updates, hubVersion);
}

/**
 * The Apps screen's own check failed outright (hub#2336): the bell keeps its count and says it
 * could not check. Overtakes a background check still in flight, like {@link publishModuleUpdates}.
 */
export function markModuleUpdatesUnknown(): void {
  if (!isAdmin.value) {
    unknown.value = false;
    return;
  }
  generation++;
  unknown.value = true;
}

/** Ask the runtime which installed apps are behind and feed the bell. **Never throws.** */
export async function refreshModuleUpdateNotice(): Promise<void> {
  const pass = ++generation;
  if (!isAuthed.value || !isAdmin.value) {
    unknown.value = false;
    publish(0);
    return;
  }
  let updates: ModuleUpdateInfo[];
  let hubVersion: string | null | undefined;
  inFlight++;
  checking.value = true;
  try {
    [updates, hubVersion] = await Promise.all([
      listModuleUpdates(),
      fetchSystemInfo().then((info) => info?.hubVersion),
    ]);
  } catch {
    // A runtime that did not answer is not «all up to date»: keep the last count, and say it.
    if (pass === generation) unknown.value = true;
    return;
  } finally {
    inFlight = Math.max(0, inFlight - 1);
    checking.value = inFlight > 0;
  }
  if (pass !== generation || !isAuthed.value || !isAdmin.value) return;
  paint(updates, hubVersion);
}

/** «Check again» on the bell (hub#2336). A check already out is not asked twice. */
export function retryModuleUpdateNotice(): void {
  if (checking.value) return;
  checkNow();
}

let watching = false;
let timer: ReturnType<typeof setInterval> | null = null;
let stopUserWatch: WatchStopHandle | null = null;
let lastCheck = 0;

function checkNow(): void {
  lastCheck = Date.now();
  void refreshModuleUpdateNotice();
}

function onVisible(): void {
  // Coming back to a tab left open overnight: check, but only if the last check is stale.
  if (document.visibilityState === 'visible' && Date.now() - lastCheck >= RECHECK_MS) checkNow();
}

/**
 * Start watching: once now, then every {@link RECHECK_MS} while the tab is visible, and again when
 * the person at the till changes. Idempotent, started from `App.vue` like the other bell sources.
 */
export function bootModuleUpdateNoticeWatch(): void {
  if (watching) return;
  watching = true;
  checkNow();
  timer = setInterval(() => {
    if (document.visibilityState === 'visible') checkNow();
  }, RECHECK_MS);
  document.addEventListener('visibilitychange', onVisible);
  // A PIN hand-over swaps the user without a logout (`user-switch.ts`): an admin arriving sees the
  // notice now, a cashier arriving stops seeing it now.
  stopUserWatch = watch(
    () => user.value?.id,
    () => checkNow(),
  );
}

/** Stop watching and clear this source (e.g. on logout). */
export function stopModuleUpdateNoticeWatch(): void {
  if (timer) clearInterval(timer);
  timer = null;
  document.removeEventListener('visibilitychange', onVisible);
  stopUserWatch?.();
  stopUserWatch = null;
  watching = false;
  generation++;
  lastCheck = 0;
  unknown.value = false;
  publish(0);
}

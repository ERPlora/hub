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
 *
 * **Hours apart, never a fast poll.** `GET /api/modules/updates` asks the marketplace once per
 * installed app (hub#516). It is checked when the admin session starts, on a PIN hand-over, and
 * every {@link RECHECK_MS} while the tab is visible — module releases are counted in days. The Apps
 * screen publishes what it learns through {@link publishModuleUpdates}, so updating there clears
 * the notice at once instead of at the next check.
 */
import { watch, type WatchStopHandle } from 'vue';

import { updateNeedsNewerHub, type ModuleUpdateInfo } from './module-updates';
import { listModuleUpdates } from './runtime';
import { isAdmin, isAuthed, user } from './session';
import { setNotificationCount } from './shell';
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

/**
 * What the Apps screen just learnt from `GET /api/modules/updates`. It replaces the notice at once,
 * so an update applied there clears the bell without waiting for the next check.
 */
export function publishModuleUpdates(
  updates: readonly ModuleUpdateInfo[],
  hubVersion: string | null | undefined,
): void {
  if (!isAdmin.value) {
    publish(0);
    return;
  }
  generation++;
  publish(actionableUpdateCount(updates, hubVersion));
}

/** Ask the runtime which installed apps are behind and feed the bell. **Never throws.** */
export async function refreshModuleUpdateNotice(): Promise<void> {
  const pass = ++generation;
  if (!isAuthed.value || !isAdmin.value) {
    publish(0);
    return;
  }
  let updates: ModuleUpdateInfo[];
  let hubVersion: string | null | undefined;
  try {
    [updates, hubVersion] = await Promise.all([
      listModuleUpdates(),
      fetchSystemInfo().then((info) => info?.hubVersion),
    ]);
  } catch {
    return; // a runtime that did not answer is not «all up to date»: keep the last count
  }
  if (pass !== generation || !isAuthed.value || !isAdmin.value) return;
  publish(actionableUpdateCount(updates, hubVersion));
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
  publish(0);
}

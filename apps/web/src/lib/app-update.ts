// **Is the app on this counter the one we publish?** — the update channel of the installed app
// (hub#400, ADR-0196/0160/0180).
//
// Until this file the fleet was one-way. We ship `com.erplora.app` to a till and then have no way
// of telling it that a newer build exists: no updater is configured (the Tauri one needs the
// signing key of hub#394), and the S3 side-channel is a folder nobody looks at. Publishing on Play
// and on Microsoft Store without this is what leaves the fleet orphaned — the stores update their
// own installs, but a Windows till that took the NSIS installer from the Cloud never hears again.
//
// **Where this code runs is the whole design.** The web app is NOT bundled in the app: the shell
// packages a fallback page and the real UI is served by the hub (ADR-0154/0159). So a check written
// here reaches every app ALREADY INSTALLED on the next hub deploy, while the same check written as
// a new Tauri command would only ever reach builds made after it — which is the very problem. That
// is also why the installed version is read first with `plugin:app|version`: it belongs to
// `core:app`, which the apps installed before hub#2658 grant the hub PWA. From hub#2658 on they do
// not — Tauri's `app` plugin answers every page under erplora.com and no gate can stand in front of
// it — and the linked hub reads the same version through `erplora_bridge_status`, one of the app's
// own commands, behind the gate.
//
// **Three sentences, and the third one is silence.** The states are the ones `lib/system-health.ts`
// already defines, for the same reason: `unknown` is not `ok` and not an alarm. A till with no
// network — an ordinary morning in a bar — must not be told anything, must not be interrupted, and
// must certainly not be told it is up to date when nobody checked.
//
// **This never updates in place, and that is deliberate, not a limitation we hide.** With no
// signing key there is no Tauri updater (hub#394), so the honest action is to hand the user their
// own browser at the download the Cloud decides. Nothing here reloads the page, closes the window
// or restarts the app: a waiter halfway through an order keeps their order, and the moment the
// installer runs is a moment *they* choose. `app-update-does-not-interrupt.test.ts` holds that.
import { computed, ref, type ComputedRef } from 'vue';

import { config } from './config';
import { getDeviceContext, invokeTauri, isTauri, type DeviceContext } from './device';
import { ADMINISTER_PERMISSION } from './management-link';
import { RUNTIME_URL, runtimeHeaders } from './runtime';
import { hasPermission } from './session';
import type { HealthState } from './system-health';

/**
 * The command that answers "which build am I?" on an app installed before hub#2658.
 *
 * `core:app` ships it in its default set, and those apps grant `core:default` to
 * `https://*.erplora.com/*`, so this works on apps built long before hub#400: the tills that most
 * need to hear about an update are exactly the ones running an old binary.
 */
export const APP_VERSION_COMMAND = 'plugin:app|version';

/**
 * The same question on an app built from hub#2658 on, which keeps `core:app` from the pages under
 * erplora.com: the app's own command, answered only to the linked hub. It carries the version the
 * release sealed in `tauri.conf.json` (hub#862).
 */
export const GATED_APP_VERSION_COMMAND = 'erplora_bridge_status';

/** Where the runtime proxies "which is the latest published build?" (`crates/server`). */
export const APP_RELEASE_ENDPOINT = '/api/app/release';

/** Platforms the Cloud has a download for. macOS is absent on purpose: nothing publishes one. */
export type DownloadPlatform = 'windows' | 'linux' | 'android';

/** What we could learn about the app installed on this device. Same three states as the hub's health. */
export type AppUpdateState = HealthState;

export interface AppUpdate {
  state: AppUpdateState;
  /** The build running here, or `null` when the shell would not say. */
  installed: string | null;
  /** The build the Cloud publishes, or `null` when we could not read it. */
  latest: string | null;
}

/** Nothing known yet — the value the app boots with, and the one every failure falls back to. */
export const UNKNOWN_UPDATE: AppUpdate = { state: 'unknown', installed: null, latest: null };

/**
 * The three numbers of a release, or `null` when the text is not one.
 *
 * Strict on purpose. Our tags are `vX.Y.Z` and nothing else; accepting more would mean deciding how
 * `1.2.3-beta` orders against `1.2.3`, and getting that wrong points a till at an installer that
 * does not exist. Refusing produces `unknown` upstream, which is silence — the safe direction.
 */
export function parseVersion(raw: string | null | undefined): number[] | null {
  if (typeof raw !== 'string') return null;
  const match = /^v?(\d+)\.(\d+)\.(\d+)$/.exec(raw.trim());
  if (!match) return null;
  return [Number(match[1]), Number(match[2]), Number(match[3])];
}

/**
 * Is `latest` strictly newer than `installed`?
 *
 * `false` whenever either side is unreadable, and `false` when they are equal. Both are the same
 * rule: only a version we are sure is ahead earns the right to interrupt someone.
 */
export function isNewerVersion(
  latest: string | null | undefined,
  installed: string | null | undefined,
): boolean {
  const a = parseVersion(latest);
  const b = parseVersion(installed);
  if (!a || !b) return false;
  for (let i = 0; i < a.length; i += 1) {
    // Number by number. Compared as text, `1.10.0` sorts BELOW `1.9.0` and the fleet stops being
    // offered updates at x.9 — silently, which is how this kind of bug survives a release.
    //
    // ⚠️ Equivalent mutant, on purpose: `>=` here behaves exactly like `>`, because the guard on the
    // same line has already established that the two differ. It is written `>` because that is the
    // sentence ("strictly ahead"); no test can tell them apart and none should try.
    if (a[i] !== b[i]) return a[i] > b[i];
  }
  return false;
}

/** The Cloud's download for this device's platform, or `null` when there is not one. */
export function downloadPlatform(
  platform: DeviceContext['platform'] | undefined,
): DownloadPlatform | null {
  switch (platform) {
    case 'windows':
    case 'linux':
    case 'android':
      return platform;
    default:
      // macOS is built locally only — no Apple Developer ID cert, so the Cloud publishes no macOS
      // installer. `cloud`/`desktop` are not an operating system. In every one of these cases the
      // honest answer is "nowhere to send you", and the button simply does not appear.
      return null;
  }
}

/**
 * The address of the newest installer for `platform` — the Cloud's, never the bucket's.
 *
 * Two things ride on this being an `erplora.com` URL and not a signed Object Storage one. The Cloud
 * is what turns this into a STORE listing the day one goes live (`store_url_for` in the SaaS), so
 * one button stays correct on Play, on Microsoft Store and on the raw installer. And it is an
 * address the shell will actually open: `external_browser_url` (ADR-0255) accepts the apex and
 * would refuse a signed bucket URL — correctly, which is why hub#480 exists.
 *
 * It carries no version. A page that baked `v1.2.3` into a link keeps handing out 1.2.3 forever;
 * "the latest" is a decision the Cloud makes per request, at the moment of the click.
 */
export function appDownloadUrl(platform: DownloadPlatform): string {
  const base = config.cloudApiUrl.replace(/\/+$/, '');
  return `${base}/app/download/${platform}/`;
}

/** The build running on this device, or `null` — in a browser, or when the shell will not say. */
async function installedVersion(): Promise<string | null> {
  if (!isTauri()) return null;
  try {
    const version = await invokeTauri<string>(APP_VERSION_COMMAND);
    if (typeof version === 'string' && version.trim()) return version.trim();
  } catch {
    // An app built from hub#2658 on refuses it to every page: ask the gated command below.
  }
  try {
    const status = await invokeTauri<{ version?: unknown }>(GATED_APP_VERSION_COMMAND, {});
    const version = status?.version;
    return typeof version === 'string' && version.trim() ? version.trim() : null;
  } catch {
    // An app built before hub#400, or a page that is not the linked hub (`not_the_linked_hub`). It
    // cannot compare, so it says nothing at all — never that it is up to date.
    return null;
  }
}

/** The build the Cloud publishes, asked of the RUNTIME (same origin — see the CSP note below). */
async function latestVersion(): Promise<string | null> {
  try {
    // Same origin, always. The page is served under `connect-src 'self' ipc:`, so a fetch straight
    // at erplora.com is killed by the CSP — and killed silently, which would look exactly like
    // "no update available".
    const res = await fetch(`${RUNTIME_URL}${APP_RELEASE_ENDPOINT}`, { headers: runtimeHeaders() });
    if (!res.ok) return null;
    const body = (await res.json()) as { version?: unknown } | null;
    const version = body?.version;
    return typeof version === 'string' && version.trim() ? version.trim() : null;
  } catch {
    return null; // no network, no Cloud, or an answer that is not JSON. All the same silence.
  }
}

/**
 * Ask both sides once and say which of the three sentences is true.
 *
 * Never throws and never blocks anything: a failed check is a morning without internet, not an
 * incident, and the till has a queue at the counter.
 */
export async function checkAppUpdate(): Promise<AppUpdate> {
  // A browser has no installed app to update — it is served fresh by the hub on every deploy. It
  // does not even ask: a request per browser tab, for an answer that can never mean anything.
  //
  // ⚠️ Equivalent mutant, on purpose: removing this line changes nothing observable today, because
  // `installedVersion()` also answers `null` outside the shell and the early return below stops
  // before the fetch. It stays because it makes "a browser never asks the runtime" true BY
  // CONSTRUCTION rather than as a consequence of the order of two questions — and the day somebody
  // reorders them to fetch first, this line is what stops every open tab in the shop from polling.
  if (!isTauri()) return UNKNOWN_UPDATE;

  const installed = await installedVersion();
  if (!installed) return UNKNOWN_UPDATE;

  const latest = await latestVersion();
  if (!latest) return { state: 'unknown', installed, latest: null };

  return {
    state: isNewerVersion(latest, installed) ? 'attention' : 'ok',
    installed,
    latest,
  };
}

/**
 * Where THIS device would get the newer build, or `null` when there is nowhere to send it.
 *
 * **A store install has nowhere to go, and saying otherwise is a policy breach** (hub#757). Google
 * Play forbids an app it distributed from fetching an APK elsewhere, and Microsoft updates its own
 * installs too: for those two the store IS the channel, so the honest answer is silence. It is not
 * a cosmetic choice — a reviewer opening the app and finding a link to `/app/download/android/` is
 * what fails the submission, and that is the only place this notice ever renders.
 *
 * Everything else keeps its download, and that is the half worth protecting: a Linux till or a
 * Windows one that took the installer from the Cloud has no store watching over it, so taking the
 * notice away from them is exactly the orphaned fleet this module was written to prevent.
 */
export async function updateDestination(): Promise<string | null> {
  return (await updateTarget())?.url ?? null;
}

/** {@link updateDestination} together with the platform it was resolved for. */
async function updateTarget(): Promise<{ platform: DownloadPlatform; url: string } | null> {
  if (!isTauri()) return null;
  const context = await getDeviceContext();
  if (context?.distribution === 'play' || context?.distribution === 'msstore') return null;
  const platform = downloadPlatform(context?.platform);
  return platform ? { platform, url: appDownloadUrl(platform) } : null;
}

// ── What the chrome reads ──────────────────────────────────────────────────────────────────────

/** What the last check concluded. Boots as `unknown`: nothing has been checked yet. */
export const appUpdate = ref<AppUpdate>(UNKNOWN_UPDATE);

/** Where this device would get it, resolved once — `null` while unknown or unreachable. */
export const appUpdateDestination = ref<string | null>(null);

/**
 * The platform {@link appUpdateDestination} was resolved for — `null` whenever the destination is.
 *
 * The confirmation reads it (hub#1898): on Android the Cloud's page hands over to Google Play, so
 * there is no file to download and nothing to open afterwards, and the desktop sentence would leave
 * the owner waiting for a download that never arrives.
 */
export const appUpdatePlatform = ref<DownloadPlatform | null>(null);

/**
 * Whether THIS session is the one this task belongs to.
 *
 * A filter, not a wall (ADR-0248, hub#435): reinstalling the till is not a waiter's job mid-service,
 * and a greyed-out button would only make them ask why. The permission is the core's own
 * `hub.administer` — nothing new is minted here.
 */
export const canUpdateApp: ComputedRef<boolean> = computed(() =>
  hasPermission(ADMINISTER_PERMISSION),
);

/** Where the till remembers which version it already mentioned, so it mentions it once. */
const ANNOUNCED_STORAGE_KEY = 'erplora.app_update.announced';

/** Six hours: a till stays open for days, and a shop does not need to be asked more often than that. */
export const CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000;

function alreadyAnnounced(version: string): boolean {
  try {
    return localStorage.getItem(ANNOUNCED_STORAGE_KEY) === version;
  } catch {
    return false; // storage refused: at worst the same toast twice, never a missed update.
  }
}

function rememberAnnounced(version: string): void {
  try {
    localStorage.setItem(ANNOUNCED_STORAGE_KEY, version);
  } catch {
    /* storage refused; nothing here is worth failing a check over. */
  }
}

/**
 * Check once and publish the answer, saying it out loud the first time a version shows up.
 *
 * Said **once per version**, and only to whoever can act on it: a toast on every six-hour tick
 * would be exactly the kind of noise that trains people to dismiss the till without reading it.
 */
export async function refreshAppUpdate(): Promise<void> {
  const update = await checkAppUpdate();
  appUpdate.value = update;
  const target = update.state === 'attention' ? await updateTarget() : null;
  appUpdateDestination.value = target?.url ?? null;
  appUpdatePlatform.value = target?.platform ?? null;

  const version = update.latest;
  if (
    update.state !== 'attention' ||
    !version ||
    !appUpdateDestination.value ||
    !canUpdateApp.value ||
    alreadyAnnounced(version)
  ) {
    return;
  }
  rememberAnnounced(version);
  // Imported here and not at the top: `toast.ts` pulls in Ionic's controllers, and this module is
  // also read by tests and by code paths that never paint anything.
  const { toastInfo } = await import('./toast');
  const { i18n } = await import('../i18n');
  void toastInfo(i18n.global.t('appUpdate.available', { version }));
}

let watching = false;

/**
 * Start asking: once at boot, then every {@link CHECK_INTERVAL_MS}.
 *
 * In a browser it never starts at all — there is no installed app to update, and the web hub
 * updates itself with every deploy. A failure never surfaces: a check that could not be made is not
 * an incident, and there is a queue at the counter.
 */
export function bootAppUpdateWatch(): void {
  if (watching || !isTauri()) return;
  watching = true;
  void refreshAppUpdate();
  setInterval(() => void refreshAppUpdate(), CHECK_INTERVAL_MS);
}

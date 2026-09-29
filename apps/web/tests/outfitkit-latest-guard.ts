// hub#2259 — the local bench must test the OutfitKit customers run.
//
// Production (docker/Dockerfile), PRE and CI (test-web.yml, visual-baselines.yml) all run
// `pnpm --filter @erplora/web add @erplora/outfitkit@latest` and ignore the pin; the local bench
// resolves whatever `pnpm-lock.yaml` pinned, which falls behind with every OutfitKit release. On
// 2026-09-27 the pin was 0.1.84 and `latest` 0.1.105, and hub#2253 chased a bug customers had not
// seen since 0.1.98. This is Playwright's `globalSetup`: it fails the run BEFORE any spec when
// node_modules is behind the published `latest`, with the command that fixes it.
//
// Chosen over "the bench installs @latest itself" because it keeps the lockfile reproducible: the
// bench never rewrites node_modules behind the developer's back, it tells them to bump the pin.
//
// CI and the pre-push gate install `latest` right before building, so they pass — except for a
// release in the minutes between that install and Playwright (13 releases on 2026-09-26). That
// race is not drift (rv-2265): the guard only fails when the install was ALREADY behind when it
// was made — some version newer than the installed one had been published at or before the moment
// pnpm wrote node_modules. A newer release after the install is OUTFITKIT_LATEST_NEWER_THAN_INSTALL,
// a warning. Offline, the latest version cannot be known: the bench runs and prints
// OUTFITKIT_LATEST_UNKNOWN instead of blocking someone without network.
//
// hub#2304 — the one deliberate exception: a pull request's CI bench compares screenshots with
// baselines drawn with ONE OutfitKit (apps/web/tests/e2e/baselines-outfitkit.txt), so it installs
// that version and exports it as HUB_BENCH_OUTFITKIT. With a pin the guard checks the install IS the
// pinned version (OUTFITKIT_NOT_PINNED_VERSION otherwise) and does not ask the registry.
//
// hub#2321 — the run an OutfitKit release triggers pins too: it tests the version the notice
// ANNOUNCED (scripts/ci/install-published-outfitkit.sh exports it), so a second release minutes
// later does not turn the run of the first one red for being behind.
import { statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { resolveOutfitkitVersion } from '../outfitkit-version';

// The FULL document (~750 KB): only it carries `time`, the publish date of every version.
export const OUTFITKIT_REGISTRY_URL = 'https://registry.npmjs.org/@erplora/outfitkit';
export const WEB_DIR = resolve(fileURLToPath(new URL('.', import.meta.url)), '..');
const WORKSPACE_DIR = resolve(WEB_DIR, '..', '..');
const FIX_COMMAND = 'pnpm -F @erplora/web add @erplora/outfitkit@latest';
const REGISTRY_TIMEOUT_MS = 10_000;

export type OutfitkitVersionState = 'behind' | 'current' | 'ahead' | 'unknown';
export type OutfitkitGuardResult = Exclude<OutfitkitVersionState, 'behind'> | 'newer-than-install' | 'pinned';

export interface OutfitkitRegistry {
  latest: string;
  /** Publish time (ISO) per version, as the registry's `time` map gives it. */
  published: Record<string, string>;
}

function parseVersion(v: string): number[] | null {
  const m = /^(\d+)\.(\d+)\.(\d+)$/.exec(v.trim());
  return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : null;
}

export function compareOutfitkitVersions(installed: string, latest: string): OutfitkitVersionState {
  const a = parseVersion(installed);
  const b = parseVersion(latest);
  if (!a || !b) return 'unknown';
  for (let i = 0; i < 3; i++) {
    if (a[i] < b[i]) return 'behind';
    if (a[i] > b[i]) return 'ahead';
  }
  return 'current';
}

export async function fetchOutfitkitRegistry(fetchImpl: typeof fetch = fetch): Promise<OutfitkitRegistry> {
  const res = await fetchImpl(OUTFITKIT_REGISTRY_URL, {
    signal: AbortSignal.timeout(REGISTRY_TIMEOUT_MS),
  });
  if (!res.ok) throw new Error(`npm registry answered ${res.status} for ${OUTFITKIT_REGISTRY_URL}`);
  const doc = (await res.json()) as { 'dist-tags'?: { latest?: unknown }; time?: unknown };
  const latest = doc['dist-tags']?.latest;
  if (typeof latest !== 'string') {
    throw new Error(`npm registry document for ${OUTFITKIT_REGISTRY_URL} has no dist-tags.latest`);
  }
  const published = doc.time && typeof doc.time === 'object' ? (doc.time as Record<string, string>) : {};
  return { latest, published };
}

/** When pnpm last wrote the workspace's node_modules: `install` and `add` both rewrite this file. */
export function readInstallTime(workspaceDir: string): Date | null {
  try {
    return statSync(join(workspaceDir, 'node_modules', '.modules.yaml')).mtime;
  } catch {
    return null;
  }
}

/** True when some version newer than `installed` existed at or before `installedAt`. */
function wasBehindAtInstall(installed: string, installedAt: Date | null, registry: OutfitkitRegistry): boolean {
  if (!installedAt) return true;
  const newer = [registry.latest, ...Object.keys(registry.published)].filter(
    (v) => compareOutfitkitVersions(installed, v) === 'behind',
  );
  return newer.some((v) => {
    const at = Date.parse(registry.published[v] ?? '');
    return Number.isNaN(at) || at <= installedAt.getTime();
  });
}

export class OutfitkitBehindLatestError extends Error {
  readonly code = 'OUTFITKIT_BEHIND_LATEST';
  constructor(
    readonly installed: string,
    readonly latest: string,
  ) {
    super(
      `OUTFITKIT_BEHIND_LATEST: the bench has @erplora/outfitkit ${installed} but production, ` +
        `PRE and CI run ${latest}. Run \`${FIX_COMMAND}\` and commit the lockfile (hub#2259).`,
    );
    this.name = 'OutfitkitBehindLatestError';
  }
}

export class OutfitkitNotPinnedError extends Error {
  readonly code = 'OUTFITKIT_NOT_PINNED_VERSION';
  constructor(
    readonly installed: string,
    readonly pinned: string,
  ) {
    super(
      `OUTFITKIT_NOT_PINNED_VERSION: HUB_BENCH_OUTFITKIT pins @erplora/outfitkit ${pinned} but the ` +
        `bench has ${installed}. Run \`pnpm -F @erplora/web add @erplora/outfitkit@${pinned}\` (hub#2304).`,
    );
    this.name = 'OutfitkitNotPinnedError';
  }
}

export interface OutfitkitGuardDeps {
  readInstalled: () => string;
  readInstalledAt: () => Date | null;
  fetchRegistry: () => Promise<OutfitkitRegistry>;
  warn: (message: string) => void;
  /** HUB_BENCH_OUTFITKIT: the version this bench runs on purpose (hub#2304); empty = latest. */
  pinned?: string;
}

export async function assertOutfitkitIsLatest(deps: OutfitkitGuardDeps): Promise<OutfitkitGuardResult> {
  const installed = deps.readInstalled();
  const pinned = deps.pinned?.trim() ?? '';
  if (pinned) {
    if (installed !== pinned) throw new OutfitkitNotPinnedError(installed, pinned);
    deps.warn(
      `OUTFITKIT_PINNED: the bench runs @erplora/outfitkit ${pinned} on purpose (HUB_BENCH_OUTFITKIT, ` +
        `the version the visual baselines were drawn with), not the published latest (hub#2304).`,
    );
    return 'pinned';
  }
  let registry: OutfitkitRegistry;
  try {
    registry = await deps.fetchRegistry();
  } catch (e) {
    deps.warn(
      `OUTFITKIT_LATEST_UNKNOWN: could not read the published @erplora/outfitkit version ` +
        `(${e instanceof Error ? e.message : String(e)}); the bench runs with ${installed} unchecked.`,
    );
    return 'unknown';
  }
  const { latest } = registry;
  const state = compareOutfitkitVersions(installed, latest);
  if (state === 'behind') {
    const installedAt = deps.readInstalledAt();
    if (wasBehindAtInstall(installed, installedAt, registry)) {
      throw new OutfitkitBehindLatestError(installed, latest);
    }
    deps.warn(
      `OUTFITKIT_LATEST_NEWER_THAN_INSTALL: @erplora/outfitkit ${latest} was published after this ` +
        `install (${installedAt?.toISOString()}, which had the then-latest ${installed}); the bench ` +
        `runs with ${installed}. Reinstall to test ${latest}.`,
    );
    return 'newer-than-install';
  }
  if (state === 'unknown') {
    deps.warn(
      `OUTFITKIT_LATEST_UNKNOWN: cannot compare installed ${JSON.stringify(installed)} with ` +
        `published ${JSON.stringify(latest)}; the bench runs unchecked.`,
    );
  }
  return state;
}

export default function outfitkitLatestGuard(): Promise<OutfitkitGuardResult> {
  return assertOutfitkitIsLatest({
    // The same resolution the image's build stamp uses (hub#1588): app first, then workspace root.
    readInstalled: () => resolveOutfitkitVersion(WEB_DIR),
    readInstalledAt: () => readInstallTime(WORKSPACE_DIR),
    fetchRegistry: () => fetchOutfitkitRegistry(),
    warn: (message) => console.warn(message),
    pinned: process.env.HUB_BENCH_OUTFITKIT,
  });
}

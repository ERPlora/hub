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
// In CI the workflow has just installed `latest`, so this passes by construction. Offline, the
// latest version cannot be known: the bench runs and prints OUTFITKIT_LATEST_UNKNOWN instead of
// blocking someone without network.
import { readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const OUTFITKIT_LATEST_URL = 'https://registry.npmjs.org/@erplora/outfitkit/latest';
export const WEB_DIR = resolve(fileURLToPath(new URL('.', import.meta.url)), '..');
const FIX_COMMAND = 'pnpm -F @erplora/web add @erplora/outfitkit@latest';
const REGISTRY_TIMEOUT_MS = 10_000;

export type OutfitkitVersionState = 'behind' | 'current' | 'ahead' | 'unknown';

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

export function readInstalledOutfitkitVersion(webDir: string): string {
  const pkg = JSON.parse(
    readFileSync(join(webDir, 'node_modules', '@erplora', 'outfitkit', 'package.json'), 'utf8'),
  ) as { version?: unknown };
  return typeof pkg.version === 'string' ? pkg.version : '';
}

export async function fetchLatestOutfitkitVersion(fetchImpl: typeof fetch = fetch): Promise<string> {
  const res = await fetchImpl(OUTFITKIT_LATEST_URL, {
    signal: AbortSignal.timeout(REGISTRY_TIMEOUT_MS),
  });
  if (!res.ok) throw new Error(`npm registry answered ${res.status} for ${OUTFITKIT_LATEST_URL}`);
  const doc = (await res.json()) as { version?: unknown };
  if (typeof doc.version !== 'string') {
    throw new Error(`npm registry document for ${OUTFITKIT_LATEST_URL} has no version`);
  }
  return doc.version;
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

export interface OutfitkitGuardDeps {
  readInstalled: () => string;
  fetchLatest: () => Promise<string>;
  warn: (message: string) => void;
}

export async function assertOutfitkitIsLatest(deps: OutfitkitGuardDeps): Promise<OutfitkitVersionState> {
  const installed = deps.readInstalled();
  let latest: string;
  try {
    latest = await deps.fetchLatest();
  } catch (e) {
    deps.warn(
      `OUTFITKIT_LATEST_UNKNOWN: could not read the published @erplora/outfitkit version ` +
        `(${e instanceof Error ? e.message : String(e)}); the bench runs with ${installed} unchecked.`,
    );
    return 'unknown';
  }
  const state = compareOutfitkitVersions(installed, latest);
  if (state === 'behind') throw new OutfitkitBehindLatestError(installed, latest);
  if (state === 'unknown') {
    deps.warn(
      `OUTFITKIT_LATEST_UNKNOWN: cannot compare installed ${JSON.stringify(installed)} with ` +
        `published ${JSON.stringify(latest)}; the bench runs unchecked.`,
    );
  }
  return state;
}

export default function outfitkitLatestGuard(): Promise<OutfitkitVersionState> {
  return assertOutfitkitIsLatest({
    readInstalled: () => readInstalledOutfitkitVersion(WEB_DIR),
    fetchLatest: () => fetchLatestOutfitkitVersion(),
    warn: (message) => console.warn(message),
  });
}

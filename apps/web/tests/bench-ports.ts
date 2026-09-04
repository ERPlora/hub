// Port allocation for the e2e bench (ERPlora/hub#1517).
//
// `ci-runner-1` (cx53) serves SIX runner slots on ONE machine, so two `e2e` jobs overlap as a
// matter of routine. The bench used to pin `127.0.0.1:8787` (runtime), `5173 --strictPort` (Vite)
// and `8791` (the runtime the assistant spec starts itself), while `reuseExistingServer` is
// `false` in CI on purpose — so the second job did not reuse the busy port, it DIED on it, and the
// red landed on whatever PR happened to be second. The same fix already exists one file over:
// `test-web.yml` gave its Postgres service a dynamic host port in hub#898, for this exact reason.
//
// Outside CI the classic ports stay: `reuseExistingServer: !CI` is what lets a developer keep
// their own `pnpm dev` running, and that only works if the bench looks for it where it lives.
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

export interface BenchPorts {
  runtime: number;
  web: number;
  assistant: number;
}

/** Environment as a plain map: this app's tsconfig has no `types: ["node"]`. */
export type BenchEnv = Record<string, string | undefined>;

/** The ports a developer's `pnpm dev` uses, and therefore the ones the local bench must reuse. */
export const CLASSIC_BENCH_PORTS: BenchPorts = { runtime: 8787, web: 5173, assistant: 8791 };

// A window of our own, well clear of the ephemeral range (macOS 49152+, Linux 32768+): a bench
// port must not collide with a socket the OS hands out to some unrelated process mid-run.
export const BENCH_WINDOW_FIRST = 8800;
export const BENCH_WINDOW_LAST = 9799;

const PROBE = fileURLToPath(new URL('./free-port-probe.mjs', import.meta.url));

// The probe RELEASES the ports before the bench binds them (`cargo run` needs seconds, the assistant
// spec binds its own port minutes later), so two scans that START on the same ports can still hand
// out the same one. Runner slots share the machine — `ci-runner-1` serves its slots as
// `ci-runner-1a` … `ci-runner-1f`, one job at a time each — so the window is split into one
// sub-window per slot letter: a scan that starts inside its own sub-window cannot begin on a
// neighbour slot's ports. Past a busy port (a zombie of the slot's previous job) the scan moves
// on, and past the sub-window it wraps into the rest of the window.
export const SLOT_LETTERS = 26;
export const SLOT_SPAN = Math.floor((BENCH_WINDOW_LAST - BENCH_WINDOW_FIRST + 1) / SLOT_LETTERS);

/** Slot index of a `<machine><digit><letter>` runner name (`ci-runner-1d` → 3); undefined otherwise. */
export function runnerSlot(runnerName: string | undefined): number | undefined {
  const match = /\d([a-z])$/.exec(runnerName ?? '');
  if (match === null) return undefined;
  return match[1].charCodeAt(0) - 'a'.charCodeAt(0);
}

/**
 * Where this job starts scanning the window: its slot's own sub-window when the runner name carries
 * a slot letter; otherwise (GitHub-hosted runner, a local `CI=1` run) a spread over the whole window
 * derived from the job identity, so two concurrent jobs at least begin far apart.
 */
export function scanStart(env: BenchEnv, pid: number): number {
  const slot = runnerSlot(env.RUNNER_NAME);
  if (slot !== undefined) return BENCH_WINDOW_FIRST + slot * SLOT_SPAN;

  const seed = [
    env.GITHUB_RUN_ID ?? '',
    env.GITHUB_JOB ?? '',
    env.GITHUB_RUN_ATTEMPT ?? '',
    env.RUNNER_NAME ?? '',
    String(pid),
  ].join(':');

  // FNV-1a, 32-bit: no dependency, and stable across Node versions (unlike a hash of an object).
  let hash = 0x811c9dc5;
  for (let i = 0; i < seed.length; i += 1) {
    hash ^= seed.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return BENCH_WINDOW_FIRST + (hash % (BENCH_WINDOW_LAST - BENCH_WINDOW_FIRST + 1));
}

/**
 * `count` ports nothing is listening on, taken from the bench window starting at `start`.
 *
 * Synchronous because Playwright loads the config synchronously (`loadUserConfig` reads
 * `module.default` without awaiting it), and binding a socket is async in Node — so the answer
 * comes from a child process we block on. See `free-port-probe.mjs`.
 */
export function freePorts(count: number, start: number, excluded: number[] = []): number[] {
  const argv = [
    PROBE,
    String(BENCH_WINDOW_FIRST),
    String(BENCH_WINDOW_LAST),
    String(start),
    String(count),
    ...excluded.map(String),
  ];

  let stdout: string;
  try {
    // The child writes its own diagnosis to stderr, which execFileSync forwards to ours.
    stdout = execFileSync(process.execPath, argv, { encoding: 'utf8' });
  } catch (cause) {
    throw new Error(
      `bench-ports: could not reserve ${count} free port(s) in ` +
        `${BENCH_WINDOW_FIRST}-${BENCH_WINDOW_LAST} from ${start} (hub#1517)`,
      { cause },
    );
  }

  const ports = stdout
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map(Number);

  if (ports.length !== count || ports.some((port) => !Number.isInteger(port))) {
    throw new Error(`bench-ports: probe answered ${JSON.stringify(stdout)}, expected ${count} ports`);
  }
  return ports;
}

/** Port of a `HUB_BIND`-style `host:port` value. */
function portFromBind(bind: string | undefined): number | undefined {
  if (bind === undefined || bind === '') return undefined;
  const port = Number(bind.slice(bind.lastIndexOf(':') + 1));
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error(`bench-ports: HUB_BIND must be host:port, got ${JSON.stringify(bind)}`);
  }
  return port;
}

/** Port of a full URL, filling in the protocol default when the URL omits it. */
function portFromUrl(url: string | undefined, name: string): number | undefined {
  if (url === undefined || url === '') return undefined;
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch (cause) {
    throw new Error(`bench-ports: ${name} must be a URL, got ${JSON.stringify(url)}`, { cause });
  }
  if (parsed.port !== '') return Number(parsed.port);
  return parsed.protocol === 'https:' ? 443 : 80;
}

/** Port of a bare numeric env var. */
function portFromNumber(value: string | undefined, name: string): number | undefined {
  if (value === undefined || value === '') return undefined;
  const port = Number(value);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error(`bench-ports: ${name} must be a port number, got ${JSON.stringify(value)}`);
  }
  return port;
}

/**
 * The three ports this bench will use. An explicit env var always wins — pinning one half of the
 * bench by hand has to keep working — and only the ports left unset are allocated.
 */
export function resolveBenchPorts(env: BenchEnv, pid: number): BenchPorts {
  const pinned: Record<keyof BenchPorts, number | undefined> = {
    runtime: portFromBind(env.HUB_BIND),
    web: portFromUrl(env.HUB_WEB_URL, 'HUB_WEB_URL'),
    assistant: portFromNumber(env.HUB_E2E_ASSISTANT_PORT, 'HUB_E2E_ASSISTANT_PORT'),
  };
  const keys: (keyof BenchPorts)[] = ['runtime', 'web', 'assistant'];

  if (!env.CI) {
    // Local: the well-known ports, so `reuseExistingServer` finds the developer's `pnpm dev`.
    return {
      runtime: pinned.runtime ?? CLASSIC_BENCH_PORTS.runtime,
      web: pinned.web ?? CLASSIC_BENCH_PORTS.web,
      assistant: pinned.assistant ?? CLASSIC_BENCH_PORTS.assistant,
    };
  }

  const missing = keys.filter((key) => pinned[key] === undefined);
  // A pinned port is excluded from the scan: the other two must not be handed the same number.
  const excluded = keys.map((key) => pinned[key]).filter((port): port is number => port !== undefined);
  const allocated = missing.length > 0 ? freePorts(missing.length, scanStart(env, pid), excluded) : [];

  const ports = { ...pinned } as Record<keyof BenchPorts, number>;
  missing.forEach((key, index) => {
    ports[key] = allocated[index];
  });
  return { runtime: ports.runtime, web: ports.web, assistant: ports.assistant };
}

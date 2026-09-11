// Regression test for ERPlora/hub#1250 — pins `updateSnapshots` in `playwright.config.ts` to the
// decision made by `src/lib/visual-baseline-gate.ts`.
//
// Why this needs its own assertion and not just the pure-function tests: Playwright's OWN
// default for `updateSnapshots` is `'missing'`, which quietly CREATES a missing baseline PNG and
// marks the test green — in any environment, CI included. `resolveUpdateSnapshotsMode` alone
// proves the decision function is correct; this test proves the config file actually WIRES that
// decision into Playwright instead of leaving the library default in charge, which is exactly the
// kind of wiring gap hub#1240's contract test (`test-web-workflow.test.sh`) exists to catch for
// the workflow side.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createServer, type Server } from 'node:net';
import { BENCH_WINDOW_FIRST, BENCH_WINDOW_LAST } from './bench-ports.ts';

// Every key the config READS or WRITES. The ports (hub#1517) matter twice over: the config
// EXPORTS `HUB_RUNTIME_URL`/`HUB_WEB_URL`/`HUB_E2E_ASSISTANT_PORT` so the specs follow the bench,
// so a second load inside this file would reuse the first bench — and the regression below would
// pass while proving nothing.
const ENV_KEYS = [
  'CI',
  'HUB_UPDATE_BASELINES',
  'HUB_E2E_REUSE_SERVER',
  'HUB_BIND',
  'HUB_RUNTIME_URL',
  'HUB_WEB_URL',
  'HUB_E2E_ASSISTANT_PORT',
  'GITHUB_RUN_ID',
  'GITHUB_JOB',
  'GITHUB_RUN_ATTEMPT',
  'RUNNER_NAME',
] as const;
let saved: Record<string, string | undefined>;

beforeEach(() => {
  saved = {};
  for (const k of ENV_KEYS) {
    saved[k] = process.env[k];
    delete process.env[k];
  }
});

afterEach(() => {
  for (const k of ENV_KEYS) {
    if (saved[k] === undefined) delete process.env[k];
    else process.env[k] = saved[k];
  }
});

// The config reads the env at module evaluation → re-import fresh each time (same pattern as
// `vite.config.test.ts`). Importing it does not start any server: `webServer` is plain data.
async function loadConfig() {
  vi.resetModules();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return (await import('./playwright.config.ts')).default as any;
}

describe('playwright.config updateSnapshots (hub#1250)', () => {
  it('REGRESSION: a normal CI run must fail on a missing baseline, never recreate it', async () => {
    process.env.CI = '1';
    const cfg = await loadConfig();
    expect(cfg.updateSnapshots).toBe('none');
  });

  it('the dedicated baseline-update run (visual-baselines.yml) regenerates every screenshot', async () => {
    process.env.CI = '1';
    process.env.HUB_UPDATE_BASELINES = '1';
    const cfg = await loadConfig();
    expect(cfg.updateSnapshots).toBe('all');
  });

  it('outside CI, a missing baseline is created without failing (authoring a new spec)', async () => {
    const cfg = await loadConfig();
    expect(cfg.updateSnapshots).toBe('missing');
  });
});

// Regression test for ERPlora/hub#1517 — the config must not pin the bench to FIXED ports in CI.
//
// `bench-ports.test.ts` proves the allocator is correct on its own; this proves the config FILE
// actually wires it, which is the half that was broken: `ci-runner-1` serves six runner slots on
// one machine, so the second overlapping `e2e` job hit `http://127.0.0.1:8787/readyz is already
// used` and died — dropping a red on a PR whose diff had nothing to do with it.
const opened: Server[] = [];

/** Occupies a port for real — a "the port is busy" test that never binds anything proves nothing. */
function occupy(port: number): Promise<void> {
  return new Promise((ok, fail) => {
    const server = createServer();
    opened.push(server);
    server.once('error', fail);
    server.listen(port, '127.0.0.1', () => ok());
  });
}

afterEach(async () => {
  await Promise.all(opened.splice(0).map((s) => new Promise<void>((ok) => s.close(() => ok()))));
});

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function runtimePortOf(cfg: any): number {
  return Number(new URL(String(cfg.webServer[0].url)).port);
}

describe('playwright.config bench ports (hub#1517)', () => {
  it('REGRESSION: a second bench on the same machine never asks for the port the first one holds', async () => {
    process.env.CI = '1';
    const first = await loadConfig();
    const busy = runtimePortOf(first);
    expect(busy).toBeGreaterThanOrEqual(BENCH_WINDOW_FIRST);
    expect(busy).toBeLessThanOrEqual(BENCH_WINDOW_LAST);

    // Exactly what the other `e2e` job on the runner does: it takes the port and keeps it.
    await occupy(busy);

    // The first load exported its own bench into the env; leaving that behind would make the
    // second load REUSE it and the assertion below would hold for the wrong reason.
    for (const key of ENV_KEYS) {
      if (key !== 'CI') delete process.env[key];
    }

    const second = await loadConfig();
    expect(runtimePortOf(second)).not.toBe(busy);
    // Vite must be told the same port the config advertises, or the bench waits on a URL nothing
    // is serving until it times out.
    const webPort = new URL(String(second.use.baseURL)).port;
    expect(second.webServer[1].command).toContain(`--port ${webPort}`);
    expect(second.webServer[1].url).toBe(second.use.baseURL);
  });

  it('the config EXPORTS the bench into the env, which is how every spec finds it', async () => {
    process.env.CI = '1';
    const cfg = await loadConfig();

    expect(cfg.webServer[0].url).toBe(`${process.env.HUB_RUNTIME_URL}/readyz`);
    expect(process.env.HUB_WEB_URL).toBe(cfg.use.baseURL);
    // `AssistantGrounded.spec.ts` starts a runtime of its own and reads this one.
    expect(Number(process.env.HUB_E2E_ASSISTANT_PORT)).toBeGreaterThanOrEqual(BENCH_WINDOW_FIRST);
    expect(Number(process.env.HUB_E2E_ASSISTANT_PORT)).not.toBe(runtimePortOf(cfg));
  });

  it('a WORKER reloading the config lands on the same bench, without sorting new ports', async () => {
    // Playwright evaluates this config TWICE: once in the runner, once in every worker, and the
    // worker inherits the runner's `process.env` (measured — the worker reads what the runner
    // wrote). If the config did not export the whole bench, that second evaluation would draw a
    // fresh runtime port nobody serves, and every spec reading HUB_RUNTIME_URL would be pointing
    // at the bench of a process that no longer exists.
    process.env.CI = '1';
    const runner = await loadConfig();

    // The runner has already STARTED the runtime by the time it forks a worker, so that port is
    // busy on the second evaluation. Without it this test cannot fail: a config merely imported
    // binds nothing, the allocator finds the same ports free again and agrees with itself by
    // accident (checked — the assertions below all held with the export removed).
    await occupy(runtimePortOf(runner));

    const worker = await loadConfig(); // same env, exactly like the forked worker sees it

    expect(worker.webServer[0].url).toBe(runner.webServer[0].url);
    expect(worker.use.baseURL).toBe(runner.use.baseURL);
    expect(worker.webServer[1].command).toBe(runner.webServer[1].command);
    expect(worker.webServer[0].env.HUB_BIND).toBe(runner.webServer[0].env.HUB_BIND);
  });

  it('a developer who ASKS to reuse their `pnpm dev` gets 8787/5173 back (hub#1812)', async () => {
    process.env.HUB_E2E_REUSE_SERVER = '1';
    const cfg = await loadConfig();
    expect(cfg.webServer[0].url).toBe('http://127.0.0.1:8787/readyz');
    expect(cfg.use.baseURL).toBe('http://localhost:5173');
    expect(cfg.webServer[1].command).toContain('--port 5173');
    for (const server of cfg.webServer) expect(server.reuseExistingServer).toBe(true);
  });
});

// Regression test for ERPlora/hub#1812 — the config must not let a LOCAL run answer with the
// bench of another worktree. `bench-ports.test.ts` proves the allocator; this proves the config
// file wires it, which is the half that was broken: `reuseExistingServer: !process.env.CI` said
// "true" for every run on a developer's machine, so the second of two concurrent runs silently
// tested the first one's branch (#1756).
describe('playwright.config local bench isolation (hub#1812)', () => {
  it('REGRESSION: outside CI the config starts its OWN bench instead of taking over one it found', async () => {
    const cfg = await loadConfig();
    for (const server of cfg.webServer) expect(server.reuseExistingServer).toBe(false);

    const runtimePort = runtimePortOf(cfg);
    const webPort = Number(new URL(String(cfg.use.baseURL)).port);
    for (const port of [runtimePort, webPort]) {
      expect(port).toBeGreaterThanOrEqual(BENCH_WINDOW_FIRST);
      expect(port).toBeLessThanOrEqual(BENCH_WINDOW_LAST);
    }
    // Vite has to be told the port the config advertises, or the bench waits on a URL nothing
    // serves; `--strictPort` then makes a collision loud instead of silently serving elsewhere.
    expect(cfg.webServer[1].command).toContain(`--port ${webPort}`);
    expect(cfg.webServer[1].command).toContain('--strictPort');
    expect(cfg.webServer[1].url).toBe(cfg.use.baseURL);
  });

  it('REGRESSION: two local runs on this machine do not ask for the same runtime port', async () => {
    const first = await loadConfig();
    const busy = runtimePortOf(first);
    await occupy(busy);

    // The first load exported its bench into the env; a second load inheriting it would reuse the
    // same ports and the assertion below would pass for the wrong reason.
    for (const key of ENV_KEYS) delete process.env[key];

    const second = await loadConfig();
    expect(runtimePortOf(second)).not.toBe(busy);
  });
});

describe('playwright.config visual determinism (hub#1752)', () => {
  it('REGRESIÓN: el huso horario del navegador está FIJADO, no heredado de la máquina', async () => {
    const cfg = await loadConfig();
    expect(cfg.projects[0].use.timezoneId).toBe('Europe/Madrid');
  });
});


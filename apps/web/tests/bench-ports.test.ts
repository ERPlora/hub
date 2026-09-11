// Regression test for ERPlora/hub#1517 — the e2e bench must not pin FIXED ports.
//
// The bug this pins: `ci-runner-1` (cx53) serves SIX runner slots on ONE machine, so two `e2e`
// jobs overlap routinely. The bench bound `127.0.0.1:8787` (runtime), `5173 --strictPort` (Vite)
// and `8791` (the assistant spec's own runtime), and in CI `reuseExistingServer` is `false` on
// purpose — so the second job did not reuse the busy port, it DIED on it:
//
//   Error: http://127.0.0.1:8787/readyz is already used, make sure that nothing is running on
//   the port/url or set reuseExistingServer:true in config.webServer.
//
// That red lands on whatever PR happened to be second, which is why hub#1517 was filed as
// "develop is broken": the failure has nothing to do with the diff it kills. The same fix already
// exists one file over — `test-web.yml` gave the Postgres service a DYNAMIC host port in hub#898,
// for this exact reason.
import { describe, it, expect, afterEach } from 'vitest';
import { createServer, type Server } from 'node:net';
import {
  BENCH_WINDOW_FIRST,
  BENCH_WINDOW_LAST,
  CLASSIC_BENCH_PORTS,
  freePorts,
  resolveBenchPorts,
  runnerSlot,
  scanStart,
  shouldReuseExistingServer,
  SLOT_SPAN,
} from './bench-ports.ts';

const opened: Server[] = [];

/** Occupies a port for real — the only way to prove the allocator SKIPS a busy one. */
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

describe('bench-ports (hub#1517)', () => {
  it('a developer who ASKS for their own `pnpm dev` gets the well-known ports (hub#1812)', () => {
    // The classic ports only make sense together with reuse: they are where `pnpm dev` lives.
    // Since hub#1812 that pairing is opt-in, so it no longer decides the default for everyone.
    expect(resolveBenchPorts({ HUB_E2E_REUSE_SERVER: '1' }, 4242)).toEqual(CLASSIC_BENCH_PORTS);
  });

  it('in CI the three ports are distinct and inside the bench window', () => {
    const ports = resolveBenchPorts({ CI: '1' }, 4242);
    const values = [ports.runtime, ports.web, ports.assistant];
    expect(new Set(values).size).toBe(3);
    for (const port of values) {
      expect(port).toBeGreaterThanOrEqual(BENCH_WINDOW_FIRST);
      expect(port).toBeLessThanOrEqual(BENCH_WINDOW_LAST);
    }
  });

  it('REGRESSION: a port that is ALREADY TAKEN is never handed out again', async () => {
    // NOT asserted to be BENCH_WINDOW_FIRST: this suite runs on a machine that may already be
    // using it, and a test that assumes an idle box is the flake we are here to remove.
    const [taken] = freePorts(1, BENCH_WINDOW_FIRST);
    await occupy(taken);

    // Same starting point, same window — but the port is busy now, exactly like the second e2e
    // job on the runner. The allocator must move on instead of returning a doomed port.
    const [next] = freePorts(1, BENCH_WINDOW_FIRST);
    expect(next).not.toBe(taken);
    expect(next).toBeGreaterThan(taken);
  });

  it('the ports handed out are free FOR REAL, not merely unused by us', async () => {
    const ports = freePorts(3, BENCH_WINDOW_FIRST);
    expect(new Set(ports).size).toBe(3);
    // If any of them were busy this rejects, and the test fails — which is the point.
    await Promise.all(ports.map((p) => occupy(p)));
  });

  it('without a slot name two jobs start the scan at different points (the spread fallback)', () => {
    const a = scanStart({ GITHUB_RUN_ID: '33787018647', GITHUB_JOB: 'e2e' }, 100);
    const b = scanStart({ GITHUB_RUN_ID: '33786909054', GITHUB_JOB: 'e2e' }, 100);
    expect(a).not.toBe(b);
    for (const start of [a, b]) {
      expect(start).toBeGreaterThanOrEqual(BENCH_WINDOW_FIRST);
      expect(start).toBeLessThanOrEqual(BENCH_WINDOW_LAST);
    }
  });

  it('the spread fallback is deterministic for one identity', () => {
    const env = { GITHUB_RUN_ID: '33787018647', GITHUB_JOB: 'e2e', RUNNER_NAME: 'ci-runner-1-3' };
    expect(scanStart(env, 100)).toBe(scanStart(env, 100));
  });

  it('an explicit HUB_BIND wins over the allocator (a developer pinning their own bench)', () => {
    const ports = resolveBenchPorts({ CI: '1', HUB_BIND: '127.0.0.1:9000' }, 4242);
    expect(ports.runtime).toBe(9000);
    expect(ports.web).not.toBe(9000);
  });

  it('an explicit HUB_WEB_URL and assistant port win too', () => {
    const ports = resolveBenchPorts(
      { CI: '1', HUB_WEB_URL: 'http://localhost:4173', HUB_E2E_ASSISTANT_PORT: '9100' },
      4242,
    );
    expect(ports.web).toBe(4173);
    expect(ports.assistant).toBe(9100);
  });

  it('REGRESSION: a pinned port is never handed to the other halves of the bench', () => {
    // Pin the runtime to the very port the scan would hand out first. Without the exclusion the
    // allocator gives Vite that same port and the bench fights itself.
    const env = { CI: '1' };
    const [first] = freePorts(1, scanStart(env, 4242));
    const ports = resolveBenchPorts({ ...env, HUB_BIND: `127.0.0.1:${first}` }, 4242);
    expect(ports.runtime).toBe(first);
    expect(ports.web).not.toBe(first);
    expect(ports.assistant).not.toBe(first);
    expect(ports.web).not.toBe(ports.assistant);
  });

  it('two SLOTS of the same runner machine scan DISJOINT sub-windows, whatever the run or pid', () => {
    // `ci-runner-1` serves its slots as `ci-runner-1a`…`ci-runner-1f`, one job at a time each. The
    // probe releases the ports before the bench binds them, so two scans starting close together
    // could still pick the same first port; a scan that starts inside its own slot's sub-window
    // cannot race the neighbour slot for it.
    const d1 = scanStart({ RUNNER_NAME: 'ci-runner-1d', GITHUB_RUN_ID: '1' }, 100);
    const d2 = scanStart({ RUNNER_NAME: 'ci-runner-1d', GITHUB_RUN_ID: '2', GITHUB_RUN_ATTEMPT: '2' }, 999);
    const e1 = scanStart({ RUNNER_NAME: 'ci-runner-1e', GITHUB_RUN_ID: '1' }, 100);
    expect(d1).toBe(d2); // same slot: same sub-window, whatever the run id, attempt or pid
    expect(Math.abs(d1 - e1)).toBeGreaterThanOrEqual(SLOT_SPAN);
    for (const start of [d1, e1]) {
      expect(start).toBeGreaterThanOrEqual(BENCH_WINDOW_FIRST);
      expect(start + SLOT_SPAN - 1).toBeLessThanOrEqual(BENCH_WINDOW_LAST);
    }
  });

  it('a run without a runner slot (a local CI=1 run) falls back to the spread', () => {
    const a = scanStart({ GITHUB_RUN_ID: '1' }, 100);
    const b = scanStart({ GITHUB_RUN_ID: '2' }, 100);
    expect(a).not.toBe(b);
  });

  it('the FIRST slot carries no letter: `ci-runner-1` is slot 0, next to `ci-runner-1b`, and never overlaps it', () => {
    // `install.sh` names the slots `ci-runner-1`, `ci-runner-1b` … `ci-runner-1f`. Sending the
    // letterless first slot to the spread fallback would let it start anywhere in the window —
    // including on top of a lettered slot's ports, which is the race this partition exists to end.
    expect(runnerSlot('ci-runner-1')).toBe(0);
    expect(runnerSlot('ci-runner-1b')).toBe(1);
    expect(runnerSlot('ci-runner-1f')).toBe(5);
    expect(runnerSlot('GitHub Actions 5')).toBe(0); // its own VM: any sub-window is fine
    expect(runnerSlot(undefined)).toBeUndefined();
    expect(runnerSlot('macbook-ioan')).toBeUndefined();
    const first = scanStart({ RUNNER_NAME: 'ci-runner-1', GITHUB_RUN_ID: '9' }, 7);
    const second = scanStart({ RUNNER_NAME: 'ci-runner-1b', GITHUB_RUN_ID: '9' }, 7);
    expect(first).toBe(BENCH_WINDOW_FIRST);
    expect(second - first).toBe(SLOT_SPAN);
  });
});

// Regression tests for ERPlora/hub#1812 — two browser-test runs on the SAME machine must not
// share a bench.
//
// The bug this pins: outside CI the bench pinned `8787`/`5173`/`8791` AND `reuseExistingServer`
// was `!CI`, i.e. always true. So the second run did not fail on the busy port — Playwright took
// the neighbour's servers for its own and ran the whole suite against ANOTHER WORKTREE'S code.
// That is the worst shape a failure can take: the spec reports "the hook you just added is not
// there", so the time goes into the diff instead of into the bench. Measured on 11/09 in #1756;
// pinning two free ports by hand made the very same spec pass untouched.
//
// The decision that closes it: reuse is opt-in (`HUB_E2E_REUSE_SERVER=1`) instead of implied by
// "not CI". `not CI` stopped telling the two cases apart the day ~44 agents shared this machine —
// one developer with their own `pnpm dev` (reuse is right) and two concurrent runs (reuse is the
// bug) look identical to it.
describe('bench isolation outside CI (hub#1812)', () => {
  it('REGRESSION: a second local run never lands on the ports the first one holds', async () => {
    // No `CI` anywhere: this is precisely the environment that used to hand out 8787/5173/8791 to
    // everybody. Two runs on one machine are two processes, so they differ by pid and nothing else.
    const first = resolveBenchPorts({}, 4242);
    await Promise.all([occupy(first.runtime), occupy(first.web), occupy(first.assistant)]);

    const second = resolveBenchPorts({}, 5353);
    for (const port of [second.runtime, second.web, second.assistant]) {
      expect([first.runtime, first.web, first.assistant]).not.toContain(port);
    }
    // And the second run's ports are real: if any were busy this rejects and the test fails.
    await Promise.all([occupy(second.runtime), occupy(second.web), occupy(second.assistant)]);
  });

  it('REGRESSION: outside CI the bench does NOT answer with a server it did not start', () => {
    expect(shouldReuseExistingServer({})).toBe(false);
  });

  it('reuse is something you ASK for, and it comes with the ports `pnpm dev` actually uses', () => {
    expect(shouldReuseExistingServer({ HUB_E2E_REUSE_SERVER: '1' })).toBe(true);
    expect(resolveBenchPorts({ HUB_E2E_REUSE_SERVER: '1' }, 4242)).toEqual(CLASSIC_BENCH_PORTS);
  });

  it('CI never reuses, whatever the env asks for: a zombie of another job must not answer', () => {
    // In CI the bench is the job's own (hub#1517). Letting this flag through would re-open the
    // exact hole hub#1517 closed, from an env var anybody can export.
    expect(shouldReuseExistingServer({ CI: '1', HUB_E2E_REUSE_SERVER: '1' })).toBe(false);
    const ports = resolveBenchPorts({ CI: '1', HUB_E2E_REUSE_SERVER: '1' }, 4242);
    expect(ports).not.toEqual(CLASSIC_BENCH_PORTS);
  });

  it('pinning ports by hand still wins outside CI (the #1756 workaround keeps working)', () => {
    const ports = resolveBenchPorts(
      { HUB_BIND: '127.0.0.1:8850', HUB_WEB_URL: 'http://localhost:5250', HUB_E2E_ASSISTANT_PORT: '8851' },
      4242,
    );
    expect(ports).toEqual({ runtime: 8850, web: 5250, assistant: 8851 });
  });

  it('a half-pinned local bench allocates the rest instead of falling back to the classic ports', () => {
    const ports = resolveBenchPorts({ HUB_BIND: '127.0.0.1:8850' }, 4242);
    expect(ports.runtime).toBe(8850);
    expect(ports.web).not.toBe(CLASSIC_BENCH_PORTS.web);
    expect(ports.assistant).not.toBe(CLASSIC_BENCH_PORTS.assistant);
    expect(new Set([ports.runtime, ports.web, ports.assistant]).size).toBe(3);
  });
});

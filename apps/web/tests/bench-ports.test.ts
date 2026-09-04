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
  it('outside CI the bench keeps the well-known ports: reuseExistingServer must find `pnpm dev`', () => {
    expect(resolveBenchPorts({}, 4242)).toEqual(CLASSIC_BENCH_PORTS);
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

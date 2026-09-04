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
  scanStart,
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

  it('two jobs of the SAME runner start the scan at different points', () => {
    const a = scanStart({ GITHUB_RUN_ID: '33787018647', GITHUB_JOB: 'e2e' }, 100);
    const b = scanStart({ GITHUB_RUN_ID: '33786909054', GITHUB_JOB: 'e2e' }, 100);
    expect(a).not.toBe(b);
    for (const start of [a, b]) {
      expect(start).toBeGreaterThanOrEqual(BENCH_WINDOW_FIRST);
      expect(start).toBeLessThanOrEqual(BENCH_WINDOW_LAST);
    }
  });

  it('the scan start is deterministic for one job (a retry lands on the same bench)', () => {
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
});

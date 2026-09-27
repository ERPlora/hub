// hub#2278: on a loaded machine vitest 4 gives up on a fork that does not answer within a
// hard-coded 60 s (`START_TIMEOUT`, not configurable), reports "[vitest-pool]: Failed to start
// forks worker for test files …" as an UNHANDLED error and exits 1 — with every test that did
// run green and the summary counting only those ("393 passed (393)"): the files whose worker
// never started were simply NOT run. That aborted three pushes in a row on 27/09.
//
// `vitest-run.mjs` is what `pnpm -F @erplora/web test` runs. Contract pinned here:
//   1. A run whose ONLY problem is workers that failed to start re-runs exactly the files that
//      never ran, once, with a single worker — and that second pass decides the exit code.
//   2. A real failure keeps the run red with NO retry: a failed test file, any other unhandled
//      error (e.g. a floating rejection, hub#1164), or a red run we cannot explain.
//   3. The retry is not a re-roll of the dice: a red second pass is red, and there is no third.
import { describe, it, expect } from 'vitest';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { planRetry, runWithStartRetry } from './vitest-run.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const SCRIPT = join(HERE, 'vitest-run.mjs');

const A = '/repo/apps/web/src/a.test.ts';
const B = '/repo/apps/web/src/b.test.ts';
const C = '/repo/apps/web/src/c.test.ts';
// Verbatim from the aborted push of hub-wt-2253 (27/09), minus the path.
const startFailure = (files) => ({
  message: `[vitest-pool]: Failed to start forks worker for test files ${files.join(', ')}.`,
  cause: { message: '[vitest-pool-runner]: Timeout waiting for worker to respond' },
});
const passed = (moduleId) => ({ moduleId, state: 'passed' });

// The gate and CI both reach vitest through `pnpm verify` → `pnpm run test`: that is the door.
describe('wiring', () => {
  it('`pnpm -F @erplora/web test` runs vitest through vitest-run.mjs', () => {
    const pkg = JSON.parse(readFileSync(join(HERE, 'package.json'), 'utf8'));
    expect(pkg.scripts.test).toBe('node vitest-run.mjs');
    expect(pkg.scripts.verify).toContain('pnpm run test');
  });
});

describe('planRetry', () => {
  it('retries exactly the files whose worker never started', () => {
    const plan = planRetry({
      specifications: [A, B, C],
      testModules: [passed(B)],
      unhandledErrors: [startFailure([A]), startFailure([C])],
    });
    expect(plan).toEqual({ retry: [A, C] });
  });

  it('also treats the pool-level start timeout (no file list) as a start failure', () => {
    const plan = planRetry({
      specifications: [A, B],
      testModules: [passed(B)],
      unhandledErrors: [{ message: '[vitest-pool]: Timeout starting forks runner.' }],
    });
    expect(plan).toEqual({ retry: [A] });
  });

  it('keeps a skipped file as run: it is not retried', () => {
    const plan = planRetry({
      specifications: [A, B],
      testModules: [{ moduleId: B, state: 'skipped' }],
      unhandledErrors: [startFailure([A])],
    });
    expect(plan).toEqual({ retry: [A] });
  });

  it('does not retry when a test file really failed, even next to a start failure', () => {
    const plan = planRetry({
      specifications: [A, B],
      testModules: [{ moduleId: B, state: 'failed' }],
      unhandledErrors: [startFailure([A])],
    });
    expect(plan).toEqual({ retry: [], reason: 'test_failed' });
  });

  it('does not retry when another unhandled error rides along with the start failure', () => {
    const plan = planRetry({
      specifications: [A, B],
      testModules: [passed(B)],
      unhandledErrors: [startFailure([A]), { message: 'Unhandled Rejection: session expired' }],
    });
    expect(plan).toEqual({ retry: [], reason: 'foreign_unhandled_error' });
  });

  it('does not retry a red run that has no start failure to explain it', () => {
    const plan = planRetry({ specifications: [A], testModules: [passed(A)], unhandledErrors: [] });
    expect(plan).toEqual({ retry: [], reason: 'no_start_failure' });
  });

  it('does not retry when every file ran anyway (nothing left to run)', () => {
    const plan = planRetry({
      specifications: [A],
      testModules: [passed(A)],
      unhandledErrors: [startFailure([A])],
    });
    expect(plan).toEqual({ retry: [], reason: 'nothing_unstarted' });
  });
});

describe('runWithStartRetry', () => {
  const quiet = () => {};

  function recorder(results) {
    const calls = [];
    const runPass = async (filters, options) => {
      calls.push({ filters, options });
      return results[calls.length - 1];
    };
    return { calls, runPass };
  }

  const green = { exitCode: 0, specifications: [A, B], testModules: [passed(A), passed(B)], unhandledErrors: [] };
  const unstartedA = {
    exitCode: 1,
    specifications: [A, B],
    testModules: [passed(B)],
    unhandledErrors: [startFailure([A])],
  };

  it('a green run is green, with a single pass', async () => {
    const { calls, runPass } = recorder([green]);
    expect(await runWithStartRetry(['src'], { runPass, log: quiet })).toBe(0);
    expect(calls).toHaveLength(1);
    expect(calls[0].filters).toEqual(['src']);
  });

  // Only a red run can be owed a retry: if vitest itself exited 0 (e.g. the config sets
  // `dangerouslyIgnoreUnhandledErrors`), the wrapper does not second-guess it.
  it('never retries a run that vitest itself called green', async () => {
    const ignoredStartFailure = { ...unstartedA, exitCode: 0 };
    const { calls, runPass } = recorder([ignoredStartFailure, green]);
    expect(await runWithStartRetry([], { runPass, log: quiet })).toBe(0);
    expect(calls).toHaveLength(1);
  });

  it('a start failure alone re-runs only the unstarted files, with one worker, and ends green', async () => {
    const retryGreen = { exitCode: 0, specifications: [A], testModules: [passed(A)], unhandledErrors: [] };
    const { calls, runPass } = recorder([unstartedA, retryGreen]);
    expect(await runWithStartRetry([], { runPass, log: quiet })).toBe(0);
    expect(calls).toHaveLength(2);
    expect(calls[1].filters).toEqual([A]);
    expect(calls[1].options.maxWorkers).toBe(1);
  });

  it('keeps the CLI options on the retry pass', async () => {
    const retryGreen = { exitCode: 0, specifications: [A], testModules: [passed(A)], unhandledErrors: [] };
    const { calls, runPass } = recorder([unstartedA, retryGreen]);
    await runWithStartRetry(['--testTimeout=1234'], { runPass, log: quiet });
    expect(calls[1].options.testTimeout).toBe(1234);
  });

  // What vitest's own CLI does to the parsed options before starting (`normalizeCliOptions`):
  // `--exclude` ADDS to the configured excludes, and a `file:line` filter needs task locations.
  it('normalizes the CLI options exactly like `vitest run` does', async () => {
    const { calls, runPass } = recorder([green]);
    await runWithStartRetry(['src/a.test.ts:12', '--exclude', 'src/slow/**'], { runPass, log: quiet });
    expect(calls[0].options.cliExclude).toEqual(['src/slow/**']);
    expect(calls[0].options.exclude).toBeUndefined();
    expect(calls[0].options.includeTaskLocation).toBe(true);
  });

  it('a red retry is red, and there is no third pass', async () => {
    const { calls, runPass } = recorder([unstartedA, unstartedA, green]);
    expect(await runWithStartRetry([], { runPass, log: quiet })).toBe(1);
    expect(calls).toHaveLength(2);
  });

  it('a real failure is red with no retry', async () => {
    const failed = {
      exitCode: 1,
      specifications: [A, B],
      testModules: [passed(A), { moduleId: B, state: 'failed' }],
      unhandledErrors: [],
    };
    const { calls, runPass } = recorder([failed, green]);
    expect(await runWithStartRetry([], { runPass, log: quiet })).toBe(1);
    expect(calls).toHaveLength(1);
  });
});

// The real thing: the wrapper drives the real vitest over a throw-away project. The worker start
// timeout is reproduced for real — a preload parks the FIRST forked worker for 65 s (sleeping,
// not spinning: this suite shares the machine with the fleet), so vitest's 60 s timer fires.
describe('vitest-run.mjs against the real vitest', () => {
  function project(files) {
    const root = mkdtempSync(join(tmpdir(), 'erplora-2278-'));
    mkdirSync(join(root, 'ran'));
    for (const [name, body] of Object.entries(files)) {
      writeFileSync(
        join(root, name),
        `import { writeFileSync } from 'node:fs';\n` +
          `test('${name}', () => { writeFileSync(${JSON.stringify(join(root, 'ran', name))}, ''); ${body} });\n`,
      );
    }
    return root;
  }

  function run(root, env = {}) {
    // This test runs INSIDE a vitest worker: drop what vitest set on it (VITEST*, TEST, NODE_ENV)
    // so the nested run starts from a shell's environment, as `pnpm test` does.
    const inherited = (k) => k.startsWith('VITEST') || k === 'TEST' || k === 'NODE_ENV';
    const clean = Object.fromEntries(Object.entries(process.env).filter(([k]) => !inherited(k)));
    const res = spawnSync(process.execPath, [SCRIPT, '--globals'], {
      cwd: root,
      env: { ...clean, ...env, VITEST_MAX_WORKERS: '2' },
      encoding: 'utf8',
      timeout: 240_000,
    });
    return { status: res.status, out: `${res.stdout}\n${res.stderr}` };
  }

  // `vitest run` sets TEST/VITEST/NODE_ENV BEFORE it loads the config (`prepareVitest`); plugins
  // such as Vue's read NODE_ENV there. The wrapper must hand the config the same environment.
  it('loads the config and runs the tests under the same environment as `vitest run`', () => {
    const root = project({
      'env.test.js':
        "expect(globalThis.__CONFIG_ENV__).toEqual({ NODE_ENV: 'test', VITEST: 'true', TEST: 'true' });" +
        "expect(process.env.NODE_ENV).toBe('test');",
    });
    writeFileSync(
      join(root, 'vitest.config.mjs'),
      'const { NODE_ENV, VITEST, TEST } = process.env;\n' +
        'export default { define: { __CONFIG_ENV__: JSON.stringify({ NODE_ENV, VITEST, TEST }) } };\n',
    );
    try {
      const { status, out } = run(root);
      expect(status, out).toBe(0);
      expect(existsSync(join(root, 'ran', 'env.test.js'))).toBe(true);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it('a real assertion failure exits 1 and is not retried', () => {
    const root = project({ 'ok.test.js': '', 'bad.test.js': 'expect(1).toBe(2);' });
    try {
      const { status, out } = run(root);
      expect(status, out).toBe(1);
      expect(out).not.toContain('vitest-run: retrying');
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it('a worker that never starts is retried and its file really runs', () => {
    const root = project({ 'a.test.js': '', 'b.test.js': '' });
    const preload = join(root, 'park-first-worker.cjs');
    writeFileSync(
      preload,
      // Only forked workers have an IPC channel; the wrapper itself is spawned without one.
      `if (typeof process.send === 'function') {\n` +
        `  try { require('node:fs').mkdirSync(${JSON.stringify(join(root, 'parked'))}); }\n` +
        `  catch { return; }\n` +
        `  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 65_000);\n` +
        `}\n`,
    );
    try {
      const { status, out } = run(root, { NODE_OPTIONS: `--require ${preload}` });
      expect(out).toContain('Failed to start forks worker');
      expect(out).toContain('vitest-run: retrying');
      expect(status, out).toBe(0);
      expect(existsSync(join(root, 'ran', 'a.test.js'))).toBe(true);
      expect(existsSync(join(root, 'ran', 'b.test.js'))).toBe(true);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  }, 300_000);
});

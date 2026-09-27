#!/usr/bin/env node
// hub#2278 — what `pnpm -F @erplora/web test` runs: `vitest run`, plus ONE narrow retry.
//
// vitest 4 gives a forked worker a hard-coded 60 s to answer its "start" message (`START_TIMEOUT`
// in its pool runner; no config knob). On the fleet machine under load (26-62, Defender scanning
// every fork's node_modules) a fork can miss that window. vitest then records "[vitest-pool]:
// Failed to start forks worker for test files …" as an UNHANDLED error and exits 1 — while the
// files of that worker were never run at all and the summary only counts the ones that were
// ("393 passed (393)"). Three pushes died that way on 27/09, each after ~35 min of web stage.
//
// So: when the ONLY thing wrong with a run is workers that failed to start, the files that never
// ran are run again, once, with a single worker (fewer forks on a starved box), and that second
// pass decides the exit code. Anything else keeps today's behaviour — a failed test file, any
// other unhandled error, or a red run we cannot explain is red, with no retry. This is not
// `retry` (hub#1367 rejects re-rolling the dice): no test that RAN is ever run again.
//
// Same `vitest run` as before otherwise: the CLI arguments go through vitest's own parser and
// the configured reporters are untouched. Contract: vitest-run.test.mjs.
import { createVitest, parseCLI } from 'vitest/node';
import { fileURLToPath } from 'node:url';

// The two ways vitest's pool reports a worker that did not come up: the runner's own 60 s start
// timeout (names the files) and the pool's 90 s backstop (does not).
const START_FAILURE = /^\[vitest-pool\]: (?:Failed to start \S+ worker for test files |Timeout starting \S+ runner\.)/;

/**
 * Decides whether a red run is owed a retry, and of which files. Pure.
 * @param {{ specifications: string[], testModules: { moduleId: string, state: string }[],
 *           unhandledErrors: { message?: string }[] }} run
 * @returns {{ retry: string[], reason?: 'test_failed' | 'foreign_unhandled_error' | 'no_start_failure' | 'nothing_unstarted' }}
 */
export function planRetry({ specifications, testModules, unhandledErrors }) {
  if (testModules.some((m) => m.state === 'failed')) return { retry: [], reason: 'test_failed' };
  if (unhandledErrors.length === 0) return { retry: [], reason: 'no_start_failure' };
  if (!unhandledErrors.every((e) => START_FAILURE.test(String(e?.message ?? '')))) {
    return { retry: [], reason: 'foreign_unhandled_error' };
  }
  const ran = new Set(testModules.filter((m) => m.state === 'passed' || m.state === 'skipped').map((m) => m.moduleId));
  const retry = [...new Set(specifications)].filter((id) => !ran.has(id));
  return retry.length ? { retry } : { retry: [], reason: 'nothing_unstarted' };
}

/**
 * @param {string[]} argv arguments after `vitest run`
 * @param {{ runPass: (filters: string[], options: object) => Promise<{ exitCode: number,
 *           specifications: string[], testModules: { moduleId: string, state: string }[],
 *           unhandledErrors: { message?: string }[] }>, log: (line: string) => void }} io
 * @returns {Promise<number>} the exit code
 */
export async function runWithStartRetry(argv, { runPass, log }) {
  const { filter, options } = parseCLI(['vitest', 'run', ...argv]);
  // What `vitest run` does to the parsed options before starting (`normalizeCliOptions` in its CLI):
  // `--exclude` adds to the configured excludes, and a `file:line` filter needs task locations.
  if (options.exclude) {
    options.cliExclude = [options.exclude].flat();
    delete options.exclude;
  }
  if (filter.some((f) => f.includes(':'))) options.includeTaskLocation ??= true;
  // And what `prepareVitest` does: `vitest run` never watches (a TTY would default to watch mode).
  if (options.run) options.watch = false;
  const first = await runPass(filter, options);
  if (first.exitCode === 0) return 0;

  const plan = planRetry(first);
  if (plan.retry.length === 0) return first.exitCode;

  log(
    `\nvitest-run: retrying ${plan.retry.length} test file(s) whose worker never started ` +
      `(worker start timeout, hub#2278) — once, with a single worker:\n` +
      plan.retry.map((f) => `  ${f}`).join('\n') +
      '\n',
  );
  const second = await runPass(plan.retry, { ...options, maxWorkers: 1 });
  return second.exitCode;
}

async function runPass(filters, options) {
  // What `vitest run` sets BEFORE loading the config (`prepareVitest`): plugins read NODE_ENV there.
  process.env.TEST = 'true';
  process.env.VITEST = 'true';
  process.env.NODE_ENV ??= 'test';
  // A pass owns its exit code: the second one must not inherit the first's failure.
  process.exitCode = 0;
  const vitest = await createVitest('test', options);
  try {
    const specifications = (await vitest.globTestSpecifications(filters)).map((s) => s.moduleId);
    let started;
    try {
      started = await vitest.start(filters);
    } catch (error) {
      // `startVitest` swallows "no test files": vitest already printed it and set the exit code
      // (1, or 0 with --passWithNoTests). Anything else is a crash and stays one.
      if (error?.code !== 'VITEST_FILES_NOT_FOUND') throw error;
      started = { testModules: [], unhandledErrors: [] };
    }
    const { testModules, unhandledErrors } = started;
    return {
      exitCode: Number(process.exitCode ?? 0),
      specifications,
      testModules: testModules.map((m) => ({ moduleId: m.moduleId, state: m.state() })),
      unhandledErrors,
    };
  } finally {
    await vitest.close();
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  let code;
  try {
    code = await runWithStartRetry(process.argv.slice(2), { runPass, log: (line) => console.error(line) });
  } catch (error) {
    console.error(error);
    code = 1;
  }
  process.exit(code);
}

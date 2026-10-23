// @vitest-environment node
// The hub setup (vitest.setup.ts, `test.setupFiles`) proven for real: Vitest runs vitest.setup.fixture.ts with the
// hub's own config in a process of its own, and each of its tests must end as the setup says — failed when it
// leaves a real timer armed, passed otherwise (hub#197, hub#199: a timer that outlives a test fires into the
// torn-down page, an «Unhandled error» and exit 1 with every test green).
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { beforeAll, describe, expect, it } from 'vitest';

const HUB_DIR = dirname(fileURLToPath(import.meta.url));
const FIXTURE = 'vitest.setup.fixture.ts';

/** Runs the fixture alone with the hub's config (its `include` swapped for the fixture) and the JSON reporter. */
const RUN = `
import { startVitest } from 'vitest/node';
const [include, outputFile] = process.argv.slice(1);
const vitest = await startVitest('test', [], {
  config: 'vite.config.ts', include: [include], watch: false, reporters: ['json'], outputFile, maxWorkers: 1, minWorkers: 1,
});
await vitest?.close();
process.exit();
`;

interface Outcome {
  status: string;
  failureMessages: string[];
}

/** How each test of the fixture ended, by its title. */
let outcomes: Map<string, Outcome>;

// A process of its own, the hub's plugins loaded from the disk: seconds, more on a loaded machine (eslint.config.test.ts).
describe('the hub setup', { timeout: 60_000 }, () => {
  beforeAll(() => {
    const dir = mkdtempSync(join(tmpdir(), 'hub-timers-'));
    try {
      const report = join(dir, 'report.json');
      // Without the parent's Vitest variables: the child is a run of its own, not a worker of this one.
      const env = Object.fromEntries(Object.entries(process.env).filter(([name]) => !name.startsWith('VITEST')));
      const child = spawnSync(process.execPath, ['--input-type=module', '-e', RUN, FIXTURE, report], { cwd: HUB_DIR, env, encoding: 'utf8' });
      if (child.error) throw child.error;
      const results = JSON.parse(readFileSync(report, 'utf8')) as { testResults: { assertionResults: (Outcome & { title: string })[] }[] };
      outcomes = new Map(results.testResults.flatMap((file) => file.assertionResults).map((test) => [test.title, test]));
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  }, 60_000);

  function outcome(title: string): Outcome {
    const found = outcomes.get(title);
    if (!found) throw new Error(`the fixture ran no test «${title}»`);
    return { status: found.status, failureMessages: found.failureMessages };
  }

  it.each(['leaves a real timeout armed', 'leaves a real interval armed', 'leaves mounted a component that never clears its timer'])(
    'fails the test that %s, naming the timer',
    (title) => {
      const { status, failureMessages } = outcome(title);
      expect(status).toBe('failed');
      expect(failureMessages.join('\n')).toMatch(/real timers still armed when the test ends/);
      expect(failureMessages.join('\n')).toMatch(/vitest\.setup\.fixture\.ts/);
    },
  );

  it.each([
    'arms nothing while the file holds a timer of its own',
    'clears its real timeout',
    'lets its real timeout run',
    'clears its real interval',
    'clears a real timeout it keeps in reactive state',
    'leaves a timeout armed on fake timers',
    'leaves mounted a component that clears its timer when unmounted',
    'leaves on the page an element that clears its timer when removed',
    'leaves on the page an element whose removal sets off a short timer',
  ])('passes the test that %s', (title) => {
    expect(outcome(title)).toEqual({ status: 'passed', failureMessages: [] });
  });

  it('clears what a failed test left armed: it never fires into the next test', () => {
    expect(outcome('never runs the timeout the failed test before it left')).toEqual({ status: 'passed', failureMessages: [] });
  });
});

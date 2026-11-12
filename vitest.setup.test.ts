// @vitest-environment node
// The hub setup (vitest.setup.ts, `test.setupFiles`) proven for real: Vitest runs vitest.setup.fixture.ts with the
// hub's own config in a process of its own, and each of its tests must end as the setup says — failed when it
// leaves a real timer armed, passed otherwise (hub#197, hub#199: a timer that outlives a test fires into the
// torn-down page, an «Unhandled error» and exit 1 with every test green), and that its time budgets, stretched by the
// machine's load, still end what never ends (hub#765).
import { spawn } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { beforeAll, describe, expect, inject, it } from 'vitest';

const HUB_DIR = dirname(fileURLToPath(import.meta.url));
const FIXTURE = 'vitest.setup.fixture.ts';

/** The scale the fixture's run is told the machine is slowed by: its `vi.waitFor` must then wait three seconds, not
 *  one. Its test and hook budgets are the ones the hub's config reads from the machine. */
const FIXTURE_SCALE = 3;

/** Runs the fixture alone with the hub's config (its `include` swapped for the fixture) and the JSON reporter. */
const RUN = `
import { startVitest } from 'vitest/node';
const [include, outputFile] = process.argv.slice(1);
const vitest = await startVitest('test', [], {
  config: 'vite.config.ts', include: [include], watch: false, reporters: ['json'], outputFile, maxWorkers: 1, minWorkers: 1,
  provide: { loadScale: ${FIXTURE_SCALE} },
});
await vitest?.close();
process.exit();
`;

interface Outcome {
  status: string;
  failureMessages: string[];
}

interface Ended extends Outcome {
  title: string;
  duration: number;
}

/** How each test of the fixture ended, by its title. */
let outcomes: Map<string, Ended>;

/** How long the fixture's run took, and the longest this worker's event loop went without turning meanwhile. */
let waited: { took: number; longestStall: number };

/** Watches this worker's event loop from now on: the returned function stops watching and tells the longest it went
 *  without turning, up to that call included. A beat every 100 ms, so a loop that turns shows stalls of about that. */
function watchStalls(): () => number {
  let last = performance.now();
  let longest = 0;
  const beat = setInterval(() => {
    const now = performance.now();
    longest = Math.max(longest, now - last);
    last = now;
  }, 100);
  return () => {
    clearInterval(beat);
    return Math.max(longest, performance.now() - last);
  };
}

// A process of its own, the hub's plugins loaded from the disk: seconds, more on a loaded machine (eslint.config.test.ts);
// and its test that never ends waits out its whole budget, which the load stretches as it stretches this one's.
const BUDGET = Math.round(60_000 * inject('loadScale'));
// The fixture's run must end on its own. It is cut here, before this file's own budget could fire: a test that never
// ends and that no budget ends makes this file fail, never hang the suite.
const RUN_BUDGET = Math.round(50_000 * inject('loadScale'));

/** Runs the fixture in a process of its own and waits for it without blocking this worker (hub#1256): resolves once
 *  the run exits, and rejects once `RUN_BUDGET` is out, the run cut. */
function runFixture(report: string): Promise<void> {
  // Without the parent's Vitest variables: the child is a run of its own, not a worker of this one.
  const env = Object.fromEntries(Object.entries(process.env).filter(([name]) => !name.startsWith('VITEST')));
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, ['--input-type=module', '-e', RUN, FIXTURE, report], {
      cwd: HUB_DIR,
      env,
      stdio: 'ignore',
      timeout: RUN_BUDGET,
    });
    child.once('error', reject);
    child.once('exit', () => {
      // `killed`: the budget's signal reached it (an outside one leaves it false).
      if (child.killed) {
        reject(new Error(`the fixture's run did not end within ${RUN_BUDGET} ms: a test that never ends was not ended by its budget`));
      } else {
        resolve();
      }
    });
  });
}

describe('the hub setup', { timeout: BUDGET }, () => {
  beforeAll(async () => {
    const dir = mkdtempSync(join(tmpdir(), 'hub-timers-'));
    try {
      const report = join(dir, 'report.json');
      const started = performance.now();
      const stopWatching = watchStalls();
      try {
        await runFixture(report);
      } finally {
        waited = { longestStall: stopWatching(), took: performance.now() - started };
      }
      const results = JSON.parse(readFileSync(report, 'utf8')) as { testResults: { assertionResults: Ended[] }[] };
      outcomes = new Map(results.testResults.flatMap((file) => file.assertionResults).map((test) => [test.title, test]));
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  }, BUDGET);

  // hub#1256: Vitest gives a worker 60 s to answer each of its calls, and the fixture's run takes minutes on a loaded
  // machine. A worker blocked waiting for it answers none, and the whole run ends red with every test green
  // («Timeout calling "onTaskUpdate"»). Its event loop must keep turning while the run lasts, whatever it lasts.
  it("waits for the fixture's run without blocking its worker, which keeps answering Vitest meanwhile", () => {
    expect(waited.longestStall).toBeLessThan(waited.took / 2);
  });

  function ended(title: string): Ended {
    const found = outcomes.get(title);
    if (!found) throw new Error(`the fixture ran no test «${title}»`);
    return found;
  }

  function outcome(title: string): Outcome {
    const { status, failureMessages } = ended(title);
    return { status, failureMessages };
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

  // A page mounted alone paints the icons the running app paints (`createShell` registers them): without them each
  // `ion-icon` warns with its whole element and tries the network, megabytes of output per file that slow the run.
  it.each([
    'paints an icon the shell registers without a warning',
    'warns about an icon the shell does not register',
    'attaches Ionic elements without the errors happy-dom alone makes them log',
  ])(
    'passes the test that %s',
    (title) => {
      expect(outcome(title)).toEqual({ status: 'passed', failureMessages: [] });
    },
  );

  it('clears what a failed test left armed: it never fires into the next test', () => {
    expect(outcome('never runs the timeout the failed test before it left')).toEqual({ status: 'passed', failureMessages: [] });
  });

  // hub#765: the budgets stretch with the load, never away. (The JSON report keeps a timeout's stack, not its message:
  // what it took is what tells it ended by its budget.)
  it('fails the test that never ends once its budget is out, never before the 5 s of an idle machine', () => {
    const { status, duration } = ended('never ends');
    expect(status).toBe('failed');
    expect(duration).toBeGreaterThanOrEqual(5_000);
  });

  it('gives up a vi.waitFor on what never comes after its second times the scale of the run, and fails the test', () => {
    const { status, failureMessages, duration } = ended('waits for what never comes');
    expect(status).toBe('failed');
    expect(failureMessages.join('\n')).toMatch(/expected 'never' to be 'there'/);
    expect(duration).toBeGreaterThanOrEqual(1_000 * FIXTURE_SCALE);
  });
});

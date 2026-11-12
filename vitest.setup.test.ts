// @vitest-environment node
// The hub setup (vitest.setup.ts, `test.setupFiles`) proven for real: Vitest runs vitest.setup.fixture.ts with the
// hub's own config in a process of its own, and each of its tests must end as the setup says — failed when it
// leaves a real timer armed, passed otherwise (hub#197, hub#199: a timer that outlives a test fires into the
// torn-down page, an «Unhandled error» and exit 1 with every test green), and that its time budgets, stretched by the
// machine's load, still end what never ends (hub#765).
import { type ChildProcess, execFileSync, spawn } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { beforeAll, describe, expect, inject, it, vi } from 'vitest';

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

/** A Node process of its own, started by `runNode`. */
interface Run {
  child: ChildProcess;
  /** Resolves once the process exits, and rejects with `cut` once its budget is out, the process cut. */
  ended: Promise<void>;
}

/** Put before each script: the process that started this one holds its stdin, and once that process is gone, however
 *  it went (a Ctrl-C, a kill), the pipe closes and this one ends with every process it started — its own group, which
 *  it leads and which a Ctrl-C on the terminal no longer reaches (hub#1269). */
const ENDS_WITH_ITS_STARTER = "process.stdin.on('end', () => process.kill(-process.pid, 'SIGKILL')).resume();\n";

/** Runs `script`, an ES module, with `args` in a Node process of its own, waited for without blocking this worker
 *  (hub#1256). Once `budget` is out it is cut with every process it started (hub#1269): it leads a process group of
 *  its own, which they join, and the cut kills the group — a signal to its PID alone would leave them running. */
function runNode({ script, args, budget, cut }: { script: string; args: readonly string[]; budget: number; cut: string }): Run {
  // Without the parent's Vitest variables: the child is a run of its own, not a worker of this one.
  const env = Object.fromEntries(Object.entries(process.env).filter(([name]) => !name.startsWith('VITEST')));
  const child = spawn(process.execPath, ['--input-type=module', '-e', ENDS_WITH_ITS_STARTER + script, ...args], {
    cwd: HUB_DIR,
    env,
    stdio: ['pipe', 'ignore', 'ignore'],
    detached: true,
  });
  const ended = new Promise<void>((resolve, reject) => {
    let cutOff = false;
    const timer = setTimeout(() => {
      cutOff = true;
      try {
        if (child.pid !== undefined) process.kill(-child.pid, 'SIGKILL');
      } catch (error) {
        // ESRCH: the group ended meanwhile, and its exit is on its way.
        if ((error as NodeJS.ErrnoException).code !== 'ESRCH') reject(error as Error);
      }
    }, budget);
    child.once('error', (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.once('exit', () => {
      clearTimeout(timer);
      if (cutOff) {
        reject(new Error(cut));
      } else {
        resolve();
      }
    });
  });
  return { child, ended };
}

/** Runs the fixture, which writes its outcomes to `report`: resolves once the run exits, and rejects once `RUN_BUDGET`
 *  is out, the run cut. */
function runFixture(report: string): Promise<void> {
  const cut = `the fixture's run did not end within ${RUN_BUDGET} ms: a test that never ends was not ended by its budget`;
  return runNode({ script: RUN, args: [FIXTURE, report], budget: RUN_BUDGET, cut }).ended;
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

// hub#1269: a run of Vitest runs its tests in processes it starts itself (`node (vitest 1)`). A cut that reached only
// the process this file started left those running with no parent, a test that never ends for ever, on a machine the
// whole fleet shares.
describe('a process of its own', () => {
  /** Starts one more process and, as that one does, never ends: a tree of two. */
  const HANGS = `
import { spawn } from 'node:child_process';
spawn(process.execPath, ['-e', 'setInterval(() => {}, 1_000)'], { stdio: 'ignore' });
setInterval(() => {}, 1_000);
`;

  /** Each process of the machine, by its PID: its parent's PID and whether it still runs (a zombie, ended but not yet
   *  reaped, does not). */
  function processes(): Map<number, { ppid: number; running: boolean }> {
    const table = new Map<number, { ppid: number; running: boolean }>();
    for (const line of execFileSync('ps', ['-A', '-o', 'pid=,ppid=,stat='], { encoding: 'utf8' }).trim().split('\n')) {
      const [pid, ppid, stat] = line.trim().split(/\s+/);
      table.set(Number(pid), { ppid: Number(ppid), running: !stat?.startsWith('Z') });
    }
    return table;
  }

  /** `pid`, the processes it started and those they started, by PID and PPID: never by their names. */
  function tree(pid: number): number[] {
    const table = processes();
    const found = [pid];
    for (let i = 0; i < found.length; i++) {
      for (const [other, { ppid }] of table) if (ppid === found[i]) found.push(other);
    }
    return found;
  }

  /** Those of `pids` still running. */
  function running(pids: readonly number[]): number[] {
    const table = processes();
    return pids.filter((pid) => table.get(pid)?.running);
  }

  /** Starts HANGS with `budget` and waits until it has started its own process: the run, how it ended (the message it
   *  was cut with, or «exited») and the PIDs of its tree. */
  async function hanging(budget: number): Promise<{ run: Run; outcome: Promise<string>; pids: number[] }> {
    const run = runNode({ script: HANGS, args: [], budget, cut: 'cut by its budget' });
    const outcome = run.ended.then(
      () => 'exited',
      (error: Error) => error.message,
    );
    const { pid } = run.child;
    if (pid === undefined) throw new Error(`the process did not start: ${await outcome}`);
    const pids = await vi.waitFor(
      () => {
        const found = tree(pid);
        expect(found).toHaveLength(2);
        return found;
      },
      { timeout: 2_000 },
    );
    return { run, outcome, pids };
  }

  /** Kills by PID what is still running of `pids`, so a test that fails leaves nothing running, and waits for `run`. */
  async function sweep(pids: readonly number[], outcome: Promise<string>): Promise<void> {
    for (const pid of running(pids)) process.kill(pid, 'SIGKILL');
    await outcome;
  }

  it('cuts it once its budget is out with every process it started', { timeout: Math.round(15_000 * inject('loadScale')) }, async () => {
    // Long enough for it to start its own process on a loaded machine, short enough not to stretch the file.
    const { outcome, pids } = await hanging(Math.round(2_000 * inject('loadScale')));
    try {
      // Its budget and as long again.
      await vi.waitFor(() => expect(running(pids)).toEqual([]), { timeout: 4_000 });
      expect(await outcome).toBe('cut by its budget');
    } finally {
      await sweep(pids, outcome);
    }
  });

  it('ends with every process it started once the process that started it is gone, as a Ctrl-C leaves it', { timeout: Math.round(15_000 * inject('loadScale')) }, async () => {
    const { run, outcome, pids } = await hanging(BUDGET);
    try {
      // What the system does to its stdin once the process that started it is gone, however that went.
      run.child.stdin?.destroy();
      await vi.waitFor(() => expect(running(pids)).toEqual([]), { timeout: 2_000 });
      expect(await outcome).toBe('exited');
    } finally {
      await sweep(pids, outcome);
    }
  });
});

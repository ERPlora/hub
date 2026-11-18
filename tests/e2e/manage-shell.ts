// A `manage.py shell` a spec keeps open on control (the registry and the platform's passes the stack's worker does
// not run): Django starts once, and the spec waits until it says it reads steps, as global-setup.ts waits for the run's
// worker. A start of Django takes from seconds to minutes on a loaded machine, so a shell per step inside a test spent
// the test's time on starts; in this one each step runs at once.
import { type ChildProcess, spawn as spawnProcess } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HUB_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');

/** What starts the shell's every line: its «ready» and each step's answer. Looked for anywhere in a line, since a
 *  program a step runs may write to the same output without ending its own. */
const SAID = 'e2e-shell: ';
const READY = `${SAID}ready`;
/** How much of what the shell printed a failure quotes. */
const TAIL = 4_000;
/** How a failure names it. */
const SHELL = 'The shell of manage.py';

/** The shell's loop: one step per line (its code as a JSON string), run in a scope of its own and answered in one line
 *  with what it printed, or with its traceback when it raised. */
const LOOP = [
  'import contextlib, io, json, sys, traceback',
  `print(${JSON.stringify(READY)}, flush=True)`,
  'for line in sys.stdin:',
  '    out = io.StringIO()',
  '    try:',
  '        with contextlib.redirect_stdout(out):',
  '            exec(json.loads(line), {})',
  '        answer = {"out": out.getvalue()}',
  '    except Exception:',
  '        answer = {"out": out.getvalue(), "error": traceback.format_exc()}',
  `    print(${JSON.stringify(SAID)} + json.dumps(answer), file=sys.__stdout__, flush=True)`,
].join('\n');

export interface Shell {
  /** Runs `code` in the shell: what it printed, trimmed; rejected with its traceback when it raises. */
  run(code: string): Promise<string>;
  /** Closes its input, which ends it, and resolves once it exited. */
  close(): Promise<void>;
}

export type SpawnShell = (
  command: string,
  args: string[],
  options: { cwd: string; env: NodeJS.ProcessEnv; stdio: ['pipe', 'pipe', 'pipe'] },
) => Pick<ChildProcess, 'once' | 'on'> & {
  stdout: Pick<NonNullable<ChildProcess['stdout']>, 'on'>;
  stderr: Pick<NonNullable<ChildProcess['stderr']>, 'on'>;
  stdin: Pick<NonNullable<ChildProcess['stdin']>, 'write' | 'end'>;
};

interface Step {
  resolve: (out: string) => void;
  reject: (error: Error) => void;
}

/** This checkout's `manage.py shell` on control, open once it is ready. `command` replaces it (the loop is its last
 *  argument). A shell that exits or cannot start before it is ready fails at once, saying what it printed. */
export function openShell({
  command = ['uv', 'run', 'python', 'manage.py', 'shell', '-c'],
  spawn = spawnProcess as unknown as SpawnShell,
}: { command?: string[]; spawn?: SpawnShell } = {}): Promise<Shell> {
  const [program, ...args] = command;
  const child = spawn(program, [...args, LOOP], { cwd: HUB_DIR, env: process.env, stdio: ['pipe', 'pipe', 'pipe'] });
  const steps: Step[] = [];
  let printed = '';
  let pending = '';
  let ended: string | undefined;
  const said = (): string => printed.trim();
  const heard = (chunk: Buffer | string): void => {
    printed = (printed + chunk.toString()).slice(-TAIL);
  };
  const done = new Promise<void>((settle) => child.once('exit', () => settle()));

  return new Promise<Shell>((resolveOpen, rejectOpen) => {
    const shell: Shell = {
      run: (code) =>
        ended !== undefined
          ? Promise.reject(new Error(`${SHELL} ${ended}`))
          : new Promise<string>((resolveStep, rejectStep) => {
              steps.push({ resolve: resolveStep, reject: rejectStep });
              child.stdin.write(`${JSON.stringify(code)}\n`);
            }),
      close: async () => {
        ended ??= 'was closed';
        child.stdin.end();
        await done;
      },
    };
    const answered = (line: string): void => {
      const at = line.indexOf(SAID);
      if (at < 0) return;
      if (line.slice(at) === READY) return resolveOpen(shell);
      const answer = JSON.parse(line.slice(at + SAID.length)) as { out: string; error?: string };
      const step = steps.shift();
      if (answer.error === undefined) step?.resolve(answer.out.trim());
      else step?.reject(new Error(`A step of the shell of manage.py raised:\n${answer.out}${answer.error}`));
    };
    child.stdout.on('data', (chunk: Buffer | string) => {
      heard(chunk);
      const lines = (pending + chunk.toString()).split('\n');
      pending = lines.pop() ?? '';
      lines.forEach(answered);
    });
    child.stderr.on('data', heard);
    child.once('exit', (code) => {
      const why = `exited with ${code ?? 'a signal'}`;
      ended ??= why;
      rejectOpen(new Error(`${SHELL} ${why} before it was ready:\n${said()}`));
      for (const step of steps.splice(0)) step.reject(new Error(`${SHELL} ${why} during a step:\n${said()}`));
    });
    // A fork that fails (EAGAIN on a loaded machine, a missing program) emits 'error' and never 'exit'.
    child.once('error', (error) => {
      ended ??= `could not start: ${error.message}`;
      rejectOpen(new Error(`${SHELL} could not start: ${error.message}`));
    });
  });
}

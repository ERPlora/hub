import { EventEmitter } from 'node:events';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { openShell, type SpawnShell } from './manage-shell';

const HUB_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');

/** A plain Python in place of `manage.py shell -c`: the same loop, without Django. `before` runs first. */
const python = (before = ''): string[] => ['python3', '-c', `import sys\n${before}\nexec(sys.argv[1])`];

describe('openShell', () => {
  it("opens this checkout's manage.py shell on control and waits until it says it reads steps", async () => {
    const calls: Parameters<SpawnShell>[] = [];
    const child = Object.assign(new EventEmitter(), {
      stdout: new EventEmitter(),
      stderr: new EventEmitter(),
      stdin: { write: () => true, end: () => undefined },
    });
    const spawn: SpawnShell = (...args) => (calls.push(args), child as never);

    let opened = false;
    const up = openShell({ spawn }).then(() => (opened = true));
    child.stdout.emit('data', Buffer.from('3 objects imported automatically.\n'));
    await new Promise((settle) => setTimeout(settle, 50));
    expect(opened).toBe(false);
    child.stdout.emit('data', Buffer.from('e2e-shell: ready\n'));
    await up;

    const [command, args, options] = calls[0];
    expect([command, ...args.slice(0, -1)]).toEqual(['uv', 'run', 'python', 'manage.py', 'shell', '-c']);
    expect(options.cwd).toBe(HUB_DIR);
  });

  it('answers what each step printed, in order, each step in a scope of its own', async () => {
    const shell = await openShell({ command: python() });

    expect(await shell.run('x = 2\nprint("one")\nprint(x * 21)')).toBe('one\n42');
    expect(await shell.run('print("x" in globals())')).toBe('False');
    await shell.close();
  });

  it('waits for the ready line however long the start takes, ignoring what is printed before it', async () => {
    const shell = await openShell({ command: python('import time\nprint("warming up")\ntime.sleep(0.5)') });

    expect(await shell.run('print("up")')).toBe('up');
    await shell.close();
  });

  it('fails a step that raises with its traceback, and goes on answering the next one', async () => {
    const shell = await openShell({ command: python() });

    await expect(shell.run('print("before")\nraise ValueError("no copy made")')).rejects.toThrow(/ValueError: no copy made/);
    expect(await shell.run('print("still here")')).toBe('still here');
    await shell.close();
  });

  it('keeps the protocol when a step writes to the same output without ending its line', async () => {
    const shell = await openShell({ command: python() });

    expect(await shell.run('import os\nos.write(1, b"pg_dump noise")\nprint("made")')).toBe('made');
    await shell.close();
  });

  it('fails at once, with what it said, when the shell exits before it is ready', async () => {
    const dies = python('print("No module named django", file=sys.stderr)\nsys.exit(3)');

    await expect(openShell({ command: dies })).rejects.toThrow(/exited with 3 before it was ready:\nNo module named django/);
  });

  it('fails at once when the shell cannot start', async () => {
    await expect(openShell({ command: ['/nonexistent/python'] })).rejects.toThrow(/could not start/);
  });

  it('fails the step in flight when the shell exits under it', async () => {
    const shell = await openShell({ command: python() });

    await expect(shell.run('import os\nos._exit(9)')).rejects.toThrow(/exited with 9/);
  });

  it('ends on close, once its input is closed', async () => {
    const shell = await openShell({ command: python() });

    await shell.close();
    await expect(shell.run('print(1)')).rejects.toThrow(/closed/);
  });
});

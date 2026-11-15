// @vitest-environment node
// The long work of a test, off the Vitest worker's thread (vitest.offload.ts, hub#1315): files read at once by Node's
// own pool of threads, a TypeScript program read ahead of its build, and a script in a thread of its own — each waited
// for without holding the worker, whose event loop turns meanwhile and so answers Vitest's own calls to it.
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import ts from 'typescript';
import { afterAll, describe, expect, it, vi } from 'vitest';

import { inThread, listAll, readAll, readProgram, readText, readTexts, unwalkedAsks, walkAhead, walkingHost } from './vitest.offload';

// The reads at once, watched: each file is asked for together with the rest, and once.
vi.mock('node:fs/promises', async (importOriginal) => {
  const fs = await importOriginal<typeof import('node:fs/promises')>();
  return { ...fs, readFile: vi.fn(fs.readFile) };
});

const dir = mkdtempSync(join(tmpdir(), 'vitest-offload-'));

afterAll(() => {
  rmSync(dir, { recursive: true, force: true });
});

/** Writes `files` (name → text) under a folder of their own in `dir`, and gives each one's path, in order. */
function written(folder: string, files: Record<string, string | Buffer>): string[] {
  const at = mkdtempSync(join(dir, `${folder}-`));
  return Object.entries(files).map(([name, text]) => {
    writeFileSync(join(at, name), text);
    return join(at, name);
  });
}

/** Whether `work` lets this worker's event loop turn before it ends: what was given to the loop as the work started
 *  has run by then. A function that holds the thread ends first, and the loop runs it only after. */
async function turnsWhile(work: () => Promise<unknown>): Promise<boolean> {
  let turned = false;
  setImmediate(() => {
    turned = true;
  });
  await work();
  return turned;
}

describe('readAll and readText', () => {
  it('reads at once each file not read yet, as TypeScript decodes it, and none of them twice', async () => {
    const paths = [
      ...written('decoded', {
        'plain.ts': 'export const plain = 1;\n',
        'bom.ts': '﻿export const bom = 1;\n',
        'utf16.ts': Buffer.concat([Buffer.from([0xff, 0xfe]), Buffer.from('export const utf16 = 1;\n', 'utf16le')]),
      }),
      join(dir, 'missing.ts'),
    ];
    const before = vi.mocked(readFile).mock.calls.length;

    const reading = readAll(paths);
    // Each asked for before the first comes back: one after another, each would wait for the last.
    expect(vi.mocked(readFile).mock.calls.length - before).toBe(paths.length);
    await reading;
    await readAll(paths);

    expect(vi.mocked(readFile).mock.calls.length - before).toBe(paths.length);
    expect(paths.map(readText)).toEqual(paths.map((path) => ts.sys.readFile(path)));
  });

  it('reads without holding the worker: what the worker was given meanwhile runs before the reading ends', async () => {
    const paths = written('many', Object.fromEntries(Array.from({ length: 50 }, (_, index) => [`${index}.ts`, `export const n = ${index};\n`])));
    expect(await turnsWhile(() => readAll(paths))).toBe(true);
    expect(paths.map(readText)).toEqual(paths.map((_, index) => `export const n = ${index};\n`));
  });
});

describe('readTexts', () => {
  it('gives the texts of the files, in order, read at once without holding the worker', async () => {
    const paths = written('texts', { 'b.ts': 'b\n', 'a.ts': 'a\n' });
    let texts: string[] = [];
    expect(await turnsWhile(async () => (texts = await readTexts(paths)))).toBe(true);
    expect(texts).toEqual(['b\n', 'a\n']);
  });

  it('fails naming a file that cannot be read', async () => {
    await expect(readTexts([join(dir, 'gone.ts')])).rejects.toThrow(`${join(dir, 'gone.ts')} could not be read`);
  });
});

describe('listAll', () => {
  it('lists what the globs match from a folder, without holding the worker, each once and in order', async () => {
    const [first] = written('listed', { 'b.test.ts': '', 'a.test.ts': '', 'notes.md': '' });
    const at = join(first, '..');
    mkdirSync(join(at, 'deep'));
    writeFileSync(join(at, 'deep', 'c.test.ts'), '');
    let listed: string[] = [];
    expect(await turnsWhile(async () => (listed = await listAll(['*.test.ts', '**/*.test.ts'], at)))).toBe(true);
    expect(listed).toEqual(['a.test.ts', 'b.test.ts', join('deep', 'c.test.ts')]);
  });
});

describe('readProgram', () => {
  it('reads ahead every file a program loads, its imports too: building it then reads none from the disk', async () => {
    const [main, helper, leaf] = written('program', {
      'main.ts': "import { helper } from './helper';\nexport const main = helper;\n",
      'helper.ts': "import { leaf } from './leaf';\nexport const helper = leaf;\n",
      'leaf.ts': 'export const leaf = 1;\n',
    });
    const options: ts.CompilerOptions = { noLib: true, types: [], module: ts.ModuleKind.ESNext, moduleResolution: ts.ModuleResolutionKind.Bundler };

    expect(await turnsWhile(() => readProgram([main], options))).toBe(true);

    const fromDisk = vi.spyOn(ts.sys, 'readFile');
    try {
      const host = ts.createCompilerHost(options);
      host.readFile = readText;
      const program = ts.createProgram({ rootNames: [main], options, host });
      expect([main, helper, leaf].map((file) => program.getSourceFile(file)?.text)).toEqual([main, helper, leaf].map(readText));
      expect(fromDisk).not.toHaveBeenCalled();
    } finally {
      fromDisk.mockRestore();
    }
  });
});

describe('walkAhead', () => {
  it('walks the repo ahead in a thread of its own, as TypeScript walks it: this worker walks none of it', async () => {
    const [config] = written('walk', { 'tsconfig.json': JSON.stringify({ extends: './base.json', include: ['src/**/*'] }), 'base.json': '{}' });
    const at = join(config, '..');
    mkdirSync(join(at, 'src', 'deep'), { recursive: true });
    for (const file of ['src/a.ts', 'src/deep/b.ts']) writeFileSync(join(at, file), '');
    const host = { ...walkingHost, onUnRecoverableConfigFileDiagnostic: () => {} };
    const walk = vi.spyOn(ts.sys, 'readDirectory');
    const lookup = vi.spyOn(ts.sys, 'fileExists');
    const asksBefore = unwalkedAsks();
    let files: string[];
    try {
      files = await walkAhead(() => ts.getParsedCommandLineOfConfigFile(config, {}, host)?.fileNames ?? []);
      expect(walk).not.toHaveBeenCalled();
      expect(lookup).not.toHaveBeenCalled();
    } finally {
      walk.mockRestore();
      lookup.mockRestore();
    }
    // A pass asked for what was not walked yet, and its parse said so.
    expect(unwalkedAsks()).toBeGreaterThan(asksBefore);
    expect(files).toEqual(ts.getParsedCommandLineOfConfigFile(config, {}, { ...ts.sys, onUnRecoverableConfigFileDiagnostic: () => {} })?.fileNames);
    expect(files.map((file) => file.slice(at.length + 1))).toEqual(['src/a.ts', 'src/deep/b.ts']);
  });

  it('answers at once, here, what it is asked outside a walk ahead, and keeps it', () => {
    const [file] = written('lookup', { 'here.ts': '' });
    const lookup = vi.spyOn(ts.sys, 'fileExists');
    try {
      expect(walkingHost.fileExists(file)).toBe(true);
      expect(walkingHost.fileExists(file)).toBe(true);
      expect(lookup).toHaveBeenCalledTimes(1);
    } finally {
      lookup.mockRestore();
    }
  });
});

describe('inThread', () => {
  it('gives what its script says, from the data it was given', async () => {
    const script = "require('node:worker_threads').parentPort.postMessage(require('node:worker_threads').workerData.n * 2);";
    expect(await inThread(script, { n: 21 })).toBe(42);
  });

  it('fails with what its script threw', async () => {
    await expect(inThread("throw new Error('no parser for it');", {})).rejects.toThrow('no parser for it');
  });

  it('fails at once, saying so, when its script is left waiting on nothing that could end it', async () => {
    await expect(inThread('new Promise(() => {});', {})).rejects.toThrow('without saying what it found');
  });

  it('works without holding the worker: what the worker was given meanwhile runs before the thread answers', async () => {
    // The thread holds itself, as a long synchronous job would: this worker keeps turning.
    const holds = `
      const { parentPort } = require('node:worker_threads');
      Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 200);
      parentPort.postMessage('done');
    `;
    expect(await turnsWhile(() => inThread(holds, {}))).toBe(true);
  });
});

// The long work of a test, off the Vitest worker's thread (hub#1315). Vitest's worker answers the run's own calls to it
// (`onTaskUpdate`) only while its event loop turns, and gives up on one after a fixed minute that no config sets
// (vitest 3.2.7, DEFAULT_TIMEOUT): a test that holds the thread past it — reading every file of the hub one by one on a
// loaded machine, where each first open waits on its own — fails the run with every test green («Timeout calling
// "onTaskUpdate"», exit 1). So that work is done elsewhere and waited for without blocking: the files read at once by
// Node's own pool of threads (`readAll`, then `readText`), a TypeScript program read ahead of its build
// (`readProgram`), TypeScript's walk of the repo for a tsconfig's files made ahead (`walkAhead`), the folders listed
// (`listAll`) and a script in a thread of its own (`inThread`). What is left on the worker's thread is the parsing, a
// second at rest. A test that waits for them names NO_CLOCK (vitest.load.ts): a synchronous one may not, and
// vitest.load.test.ts holds every test of the run to it.
import { glob, readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { Worker } from 'node:worker_threads';

import ts from 'typescript';

/** The text of each file read, by its path, read once per run (see `readAll`). */
const texts = new Map<string, string | undefined>();

/** A file's bytes as TypeScript's own read decodes them: UTF-8 without its byte order mark; UTF-16, by that read. */
function decoded(file: string, bytes: Buffer): string | undefined {
  const utf16 = bytes.length >= 2 && ((bytes[0] === 0xfe && bytes[1] === 0xff) || (bytes[0] === 0xff && bytes[1] === 0xfe));
  if (utf16) return ts.sys.readFile(file);
  const text = bytes.toString('utf8');
  return text.charCodeAt(0) === 0xfeff ? text.slice(1) : text;
}

/**
 * Reads at once each file not read yet, by Node's own pool of threads, without holding the worker. With the machine
 * loaded, a file's first open waits on its own: 760 files read one by one took 75 s, 99 ms each against 0.5 at rest
 * (2026-10-30), and 2,046 took 38 s at load 19 against 1 s to parse them (2026-11-12); waiting for them together takes
 * a fraction of their sum. A file that cannot be read is `undefined`, as TypeScript's own read returns it. The tests
 * that read through it wait without a clock (NO_CLOCK): a read of a file of the repo ends, as late as the machine makes
 * it, which no clock in seconds tells from one that never does; what could still not end, a wait nobody settles, only
 * the end of the run's job cuts.
 */
export async function readAll(files: Iterable<string>): Promise<void> {
  const unread = [...new Set([...files].map((file) => resolve(file)))].filter((file) => !texts.has(file));
  const read = await Promise.all(unread.map((file) => readFile(file).then((bytes) => decoded(file, bytes), () => undefined)));
  unread.forEach((file, index) => texts.set(file, read[index]));
}

/** A file's text: what `readAll` read, or (once) from the disk. */
export function readText(file: string): string | undefined {
  const path = resolve(file);
  if (!texts.has(path)) texts.set(path, ts.sys.readFile(path));
  return texts.get(path);
}

/** The texts of `files`, in order, read at once without holding the worker (`readAll`); one that cannot be read fails. */
export async function readTexts(files: readonly string[]): Promise<string[]> {
  await readAll(files);
  return files.map((file) => {
    const text = readText(file);
    if (text === undefined) throw new Error(`${file} could not be read`);
    return text;
  });
}

/** What `patterns` match under `cwd`, relative to it, each once and in order: its folders opened by Node's own pool of
 *  threads, without holding the worker. */
export async function listAll(patterns: readonly string[], cwd: string): Promise<string[]> {
  const found = new Set<string>();
  for await (const file of glob(patterns, { cwd })) found.add(file);
  return [...found].sort();
}

/**
 * Reads at once every file a TypeScript program over `rootNames` loads, before it is built: each pass builds it
 * from what was read (a file not read yet, as empty) and reads at once what it asked for, until it asks for nothing
 * new. Each pass parses only what it had not parsed with the same text. A program built afterwards with `readText` as
 * its host's `readFile` reads none of them from the disk.
 */
export async function readProgram(rootNames: readonly string[], options: ts.CompilerOptions): Promise<void> {
  const parsed = new Map<string, ts.SourceFile>();
  for (let wanted: Iterable<string> = rootNames; ; ) {
    await readAll(wanted);
    const asked = new Set<string>();
    const host = ts.createCompilerHost(options);
    host.readFile = (file) => {
      const path = resolve(file);
      if (texts.has(path)) return texts.get(path);
      asked.add(path);
      return '';
    };
    const getSourceFile = host.getSourceFile;
    host.getSourceFile = (file, version, onError) => {
      const known = parsed.get(file);
      if (known && known.text === host.readFile(file)) return known;
      const source = getSourceFile(file, version, onError);
      if (source) parsed.set(file, source);
      return source;
    };
    ts.createProgram({ rootNames, options, host });
    if (asked.size === 0) return;
    wanted = asked;
  }
}

/** A walk of the repo for a tsconfig's files, or a lookup of a file, as TypeScript's own `sys` makes it. */
type Walk = ['readDirectory', ...Parameters<typeof ts.sys.readDirectory>] | ['fileExists', string];

/** What each walk and lookup found, by what it asked, once per run: made in a thread of its own ahead of the parse
 *  that asks for it (see `walkAhead`), else here, at once. */
const walks = new Map<string, unknown>();

/** The walks and lookups not made yet that the pass `walkAhead` is running asked for; outside one, none. */
let unwalked: Map<string, Walk> | undefined;
/** How many times a walk or lookup not made yet was asked for, ever (see `unwalkedAsks`). */
let asksOfUnwalked = 0;

/** How many times a walk or lookup not made yet was asked for, ever: a parse during which it grew was made without
 *  what it asked for (its project lists none of those files), and is not to be kept. */
export function unwalkedAsks(): number {
  return asksOfUnwalked;
}

/** What `walk` found; within a pass of `walkAhead`, until it is made, `meanwhile`. */
function walked<T>(walk: Walk, meanwhile: T): T {
  const key = JSON.stringify(walk);
  if (walks.has(key)) return walks.get(key) as T;
  if (unwalked) {
    unwalked.set(key, walk);
    asksOfUnwalked += 1;
    return meanwhile;
  }
  const [name, ...args] = walk;
  const found = name === 'readDirectory' ? ts.sys.readDirectory(...(args as Parameters<typeof ts.sys.readDirectory>)) : ts.sys.fileExists(args[0] as string);
  walks.set(key, found);
  return found as T;
}

/** TypeScript's own `sys` for parsing a tsconfig, but its walks of the repo and lookups of files: those are made once
 *  per run, ahead in a thread of its own within `walkAhead`, else here, at once. */
export const walkingHost: ts.System = {
  ...ts.sys,
  readDirectory: (...walk: Parameters<typeof ts.sys.readDirectory>) => walked<string[]>(['readDirectory', ...walk], []),
  fileExists: (file: string) => walked(['fileExists', file], false),
};

/** The thread's side: TypeScript's own `sys` makes each walk and lookup, and says what they found, in order. */
const WALKER = `
const { parentPort, workerData } = require('node:worker_threads');
const ts = require(workerData.typescript);
parentPort.postMessage(workerData.walks.map(([name, ...args]) => ts.sys[name](...args)));
`;
const TYPESCRIPT = createRequire(import.meta.url).resolve('typescript');

/**
 * What `parse`, which reads through `walkingHost`, gives once it asks for no walk of the repo, nor lookup of a file,
 * not made yet: each pass makes the ones it asked for at once, in a thread of its own (`inThread`), and the next pass
 * parses with them. TypeScript's walk is synchronous and, on a loaded machine, as slow as the opening of each folder
 * (465 of them for the hub's tsconfigs, 118 s for a test that opened 2,588 at load ~30): here it would hold the worker.
 * What a pass parsed without its walks lists none of their files: a cache of parses keeps one only if `unwalkedAsks`
 * did not grow while it was parsed.
 */
export async function walkAhead<T>(parse: () => T): Promise<T> {
  for (;;) {
    const asked = new Map<string, Walk>();
    unwalked = asked;
    let parsed: T;
    try {
      parsed = parse();
    } finally {
      unwalked = undefined;
    }
    if (asked.size === 0) return parsed;
    const found = await inThread<unknown[]>(WALKER, { typescript: TYPESCRIPT, walks: [...asked.values()] });
    [...asked.keys()].forEach((key, index) => walks.set(key, found[index]));
  }
}

/**
 * Runs `script`, CommonJS, in a thread of its own with `workerData` as its `workerData`, and gives what it says
 * (`parentPort.postMessage`), once. Work that holds the thread it runs in — loading a linter's parsers and plugins from
 * the disk, TypeScript's walk of the repo — holds that thread and not the worker's, for as long as a loaded machine
 * makes it (101 s measured for ESLint's first lint), which no clock in seconds tells from work that never ends.
 * Waited for without a clock (hub#1292): what could keep it from ever answering ends the thread, a script left waiting
 * on nothing that could end it as much as an error, and that fails at once, saying so. A script that never stops
 * working, only the end of the run's job cuts.
 */
export function inThread<T>(script: string, workerData: unknown): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const thread = new Worker(script, { eval: true, workerData });
    thread.once('message', resolve);
    thread.once('error', reject);
    thread.once('exit', (code) => {
      reject(new Error(`the thread ended (exit ${code}) without saying what it found: its work was left waiting on nothing that could end it`));
    });
  });
}

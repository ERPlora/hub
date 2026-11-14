// @vitest-environment node
// Lint of hub-next: the SPA reaches the server only through the SDK (`@erplora/ui/sdk`), so the
// shell entry and every app frontend are linted for raw network globals. Linted for real here, by the hub's ESLint
// in a thread of its own (`lintInThread`).
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { afterAll, beforeAll, describe, expect, it } from 'vitest';

import { NO_CLOCK } from './vitest.load';
import { inThread } from './vitest.offload';

const HUB_DIR = dirname(fileURLToPath(import.meta.url));
const nodeRequire = createRequire(import.meta.url);

/** A text to lint and the file ESLint lints it as. */
type Lint = readonly [code: string, filePath: string];
/** What ESLint said of each text of a `lintInThread`, in order, and whether it ignores each of its paths. */
interface Found {
  lints: { ruleId: string | null; message: string }[][];
  ignored: boolean[];
}

/** The thread's side: the ESLint at `workerData.eslint` lints each text as its file and tells whether it ignores each
 *  path, then says it all at once. */
const LINTER = `
const { parentPort, workerData } = require('node:worker_threads');
const { ESLint } = require(workerData.eslint);
const eslint = new ESLint({ cwd: workerData.cwd });
(async () => {
  const lints = [];
  for (const [code, filePath] of workerData.lints) {
    const [result] = await eslint.lintText(code, { filePath });
    lints.push(result.messages.map(({ ruleId, message }) => ({ ruleId, message })));
  }
  const ignored = [];
  for (const path of workerData.paths) ignored.push(await eslint.isPathIgnored(path));
  parentPort.postMessage({ lints, ignored });
})();
`;

/**
 * Lints `lints` and asks about `paths` with the hub's ESLint (or `eslint`) in a thread of its own (`inThread`), as
 * `pnpm lint` runs it in a process of its own. Its first lint loads its parsers and plugins from the disk, and that
 * load holds the thread it runs in: a second at rest, and for as long as a loaded machine makes it (101 s measured),
 * which no clock in seconds tells from one that never ends, and Vitest fails a run whose worker it held past a minute
 * (hub#1315). A lint left waiting on nothing that could end it fails at once, saying so.
 */
function lintInThread(lints: readonly Lint[], paths: readonly string[], eslint = nodeRequire.resolve('eslint')): Promise<Found> {
  return inThread<Found>(LINTER, { eslint, cwd: HUB_DIR, lints, paths });
}

const RESTRICTED = 'no-restricted-globals';
const NETWORK = ['fetch', 'EventSource', 'WebSocket', 'XMLHttpRequest'];
const APP_PAGE = 'apps/demo/frontend/pages/ItemListPage.ts';
const ENTRY = 'frontend/main.ts';
const VUE_PAGE = 'apps/demo/frontend/pages/ItemListPage.vue';
const PROBE = 'apps/demo/frontend/pages/Probe.vue';
const uses = (name: string) => `export const x = ${name};\n`;
const SCRIPT_SETUP = `<script setup lang="ts">\nconst items = fetch('/api/demo/items');\n</script>\n<template><div>{{ items }}</div></template>\n`;
const slottedIn = (tag: string) => `<template><ion-button><${tag} slot="start" /></ion-button></template>\n`;
const APP_TEST = 'apps/demo/frontend/pages/ItemListPage.test.ts';
const E2E_HELPER = 'tests/e2e/probe.ts';
/** A function with `branches` ifs: its complexity is `branches` + 1. */
const branchy = (branches: number) =>
  `export function f(v: number): number {\n${Array.from({ length: branches }, (_, i) => `  if (v === ${i}) v += 1;\n`).join('')}  return v;\n}\n`;
/** Ifs nested `depth` deep. */
const nested = (depth: number) =>
  `export function f(v: number): number {\n${'  if (v) {\n'.repeat(depth)}  v += 1;\n${'  }\n'.repeat(depth)}  return v;\n}\n`;
const taking = (count: number) =>
  `export function f(${Array.from({ length: count }, (_, i) => `a${i}: number`).join(', ')}): number {\n  return a0;\n}\n`;
/** A function of `lines` lines, braces included, with a blank line and a comment that do not count. */
const long = (lines: number) =>
  `export function f(): number {\n  let v = 0;\n\n  // a comment\n${'  v += 1;\n'.repeat(lines - 4)}  return v;\n}\n`;

/** Every lint these tests read. */
const LINTS: readonly Lint[] = [
  ...NETWORK.flatMap((name): Lint[] => [
    [uses(name), APP_PAGE],
    [uses(name), ENTRY],
  ]),
  [SCRIPT_SETUP, VUE_PAGE],
  ...['ion-icon', 'HubIcon', 'ok-icon'].map((tag): Lint => [slottedIn(tag), PROBE]),
  ...[branchy(14), branchy(15), nested(4), nested(5), taking(3), taking(4), long(50), long(51)].flatMap((code): Lint[] => [
    [code, APP_PAGE],
    [code, APP_TEST],
    [code, E2E_HELPER],
  ]),
];
/** What ESLint must ignore: the build and collectstatic output, the repo's own .venv (uv), which carries the admin's
 *  JavaScript, packages/ui and packages/live, linted in their own repos, and the shell scripts' tests. */
const IGNORED = [
  'frontend/dist/assets/main-abc.js',
  '.github/scripts/pytest-shard.test.sh',
  'staticfiles/admin/js/core.js',
  '.venv/lib/python3.14/site-packages/django/contrib/admin/static/admin/js/core.js',
  'packages/ui/src/sdk/client.ts',
];

describe('eslint config', () => {
  let found: Found;

  // ESLint's own load, in its thread, for as long as the machine takes (see lintInThread).
  beforeAll(async () => {
    found = await lintInThread(LINTS, IGNORED);
  }, NO_CLOCK);

  /** The messages of `rule` in what ESLint said of `code` linted as `filePath`, one of `LINTS`. */
  function said(code: string, filePath: string, rule: string): string[] {
    const index = LINTS.findIndex(([text, file]) => text === code && file === filePath);
    if (index < 0) throw new Error(`no lint of that text as ${filePath} in LINTS`);
    return found.lints[index].filter((message) => message.ruleId === rule).map((message) => message.message);
  }

  it.each(NETWORK)('forbids %s in an app page and in the entry', (name) => {
    expect(said(uses(name), APP_PAGE, RESTRICTED)).toHaveLength(1);
    expect(said(uses(name), ENTRY, RESTRICTED)).toHaveLength(1);
  });

  it('forbids it in the <script setup> of a .vue page too', () => {
    expect(said(SCRIPT_SETUP, VUE_PAGE, RESTRICTED)).toEqual(["Unexpected use of 'fetch'. Network access goes through the SDK (@erplora/ui/sdk)."]);
  });

  it('takes slot="…" on ion-* and on HubIcon as the Web Components slot, not on a leftover ok-*', () => {
    const slotted = (tag: string) => said(slottedIn(tag), PROBE, 'vue/no-deprecated-slot-attribute').length;
    expect(slotted('ion-icon')).toBe(0);
    expect(slotted('HubIcon')).toBe(0);
    expect(slotted('ok-icon')).toBe(1); // OutfitKit is gone: no exception left for it
  });

  it('caps the complexity of a function at 15, in tests too', () => {
    for (const file of [APP_PAGE, APP_TEST, E2E_HELPER]) {
      expect(said(branchy(14), file, 'complexity')).toEqual([]);
      expect(said(branchy(15), file, 'complexity')).toHaveLength(1);
    }
  });

  it('caps the nesting of blocks at 4, in tests too', () => {
    for (const file of [APP_PAGE, APP_TEST, E2E_HELPER]) {
      expect(said(nested(4), file, 'max-depth')).toEqual([]);
      expect(said(nested(5), file, 'max-depth')).toHaveLength(1);
    }
  });

  it('caps a function at 3 parameters and 50 lines, not counting blanks and comments, outside tests', () => {
    expect(said(taking(3), APP_PAGE, 'max-params')).toEqual([]);
    expect(said(taking(4), APP_PAGE, 'max-params')).toHaveLength(1);
    expect(said(long(50), APP_PAGE, 'max-lines-per-function')).toEqual([]);
    expect(said(long(51), APP_PAGE, 'max-lines-per-function')).toHaveLength(1);
  });

  it('leaves the parameters and the length of a function free in tests, where each describe is one', () => {
    for (const file of [APP_TEST, E2E_HELPER]) {
      expect(said(taking(4), file, 'max-params')).toEqual([]);
      expect(said(long(51), file, 'max-lines-per-function')).toEqual([]);
    }
  });

  it('keeps the suppressions of what already broke a limit, and fails on one no longer needed', () => {
    const { scripts } = JSON.parse(readFileSync(join(HUB_DIR, 'package.json'), 'utf8')) as { scripts: Record<string, string> };
    expect(existsSync(join(HUB_DIR, 'eslint-suppressions.json'))).toBe(true);
    expect(scripts.lint).toMatch(/^eslint /);
    expect(scripts.lint).not.toMatch(/--(pass-on-unpruned-suppressions|suppress-all|suppress-rule|suppressions-location)/);
  });

  it('lints in a thread of its own: this worker never loads ESLint', () => {
    const loaded = Object.keys(nodeRequire.cache).filter((file) => file.includes(join('node_modules', 'eslint', 'lib')));
    expect(loaded).toEqual([]);
  });

  it('ignores the build and collectstatic output, the virtualenv, the live and ui submodules and the shell scripts', () => {
    expect(IGNORED.filter((_path, index) => !found.ignored[index])).toEqual([]);
  });
});

describe('lintInThread', () => {
  const dir = mkdtempSync(join(tmpdir(), 'eslint-thread-'));

  afterAll(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  /** A stand-in for ESLint in the thread, whose `lintText` does `body`. */
  function eslintThat(name: string, body: string): string {
    const file = join(dir, `${name}.cjs`);
    writeFileSync(file, `exports.ESLint = class { lintText() { ${body} } isPathIgnored() { return Promise.resolve(false); } };\n`);
    return file;
  }

  it('fails at once, saying so, when its lint is left waiting on nothing that could end it', async () => {
    const waits = eslintThat('waits', 'return new Promise(() => {});');
    await expect(lintInThread([['', APP_PAGE]], [], waits)).rejects.toThrow('without saying what it found');
  });

  it('fails with what ESLint threw', async () => {
    const throws = eslintThat('throws', "return Promise.reject(new Error('no parser for it'));");
    await expect(lintInThread([['', APP_PAGE]], [], throws)).rejects.toThrow('no parser for it');
  });
});

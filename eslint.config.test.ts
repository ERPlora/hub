// @vitest-environment node
// Lint of hub-next: the SPA reaches the server only through the SDK (`@erplora/ui/sdk`), so the
// shell entry and every app frontend are linted for raw network globals. Linted for real here, by the hub's ESLint
// in a thread of its own (`lintInThread`).
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
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

/** Every lint these tests read. */
const LINTS: readonly Lint[] = [
  ...NETWORK.flatMap((name): Lint[] => [
    [uses(name), APP_PAGE],
    [uses(name), ENTRY],
  ]),
  [SCRIPT_SETUP, VUE_PAGE],
  ...['ion-icon', 'HubIcon', 'ok-icon'].map((tag): Lint => [slottedIn(tag), PROBE]),
];
/** What ESLint must ignore: the build and collectstatic output, the repo's own .venv (uv), which carries the admin's
 *  JavaScript, and packages/ui and packages/live, linted in their own repos. */
const IGNORED = [
  'frontend/dist/assets/main-abc.js',
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

  it('lints in a thread of its own: this worker never loads ESLint', () => {
    const loaded = Object.keys(nodeRequire.cache).filter((file) => file.includes(join('node_modules', 'eslint', 'lib')));
    expect(loaded).toEqual([]);
  });

  it('ignores the build and collectstatic output, the virtualenv, and the live and ui submodules', () => {
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

// What the guardrails over the Hub's frontends read (money-grouping, quantity-format): the code of a `.ts` and of the
// `<script>` blocks of a `.vue` at their own lines, the sources of a frontend without tests, their helpers, declarations
// or builds, and what a guard finds in them, as `<path>:<line>` by app.
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';

import ts from 'typescript';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { bare, findingsByApp, frontendSources, hubFrontends, linesWhere, scriptBlocks } from './frontend-sources';

describe('scriptBlocks', () => {
  it('gives a .ts whole, from its first line', () => {
    expect(scriptBlocks('const a = 1;\nconst b = 2;', 'format.ts')).toEqual([{ code: 'const a = 1;\nconst b = 2;', offset: 0 }]);
  });

  it('gives each <script> block of a .vue with the lines before it, and nothing of its template', () => {
    const component = [
      '<template>{{ total }}</template>',
      '<script lang="ts">',
      'export const a = 1;',
      '</script>',
      '<script setup lang="ts">',
      'const b = 2;',
      '</script>',
    ].join('\n');
    const blocks = scriptBlocks(component, 'Total.vue');
    expect(blocks.map((block) => block.offset)).toEqual([1, 4]);
    expect(blocks.map((block) => block.code.trim())).toEqual(['export const a = 1;', 'const b = 2;']);
  });

  it('gives a .vue without a script nothing', () => {
    expect(scriptBlocks('<template><p>hola</p></template>', 'Plain.vue')).toEqual([]);
  });
});

describe('bare', () => {
  it('sees through the parentheses, `as` and `satisfies` around an expression', () => {
    const file = ts.createSourceFile('x.ts', "const a = ((3 as const) satisfies number);\nconst b = 'always';", ts.ScriptTarget.Latest, true);
    const [first, second] = file.statements.map(
      (statement) => (statement as ts.VariableStatement).declarationList.declarations[0].initializer as ts.Expression,
    );
    expect(ts.isNumericLiteral(bare(first)) && bare(first).getText(file)).toBe('3');
    expect(bare(second)).toBe(second);
  });
});

describe('linesWhere', () => {
  const isTwo = (node: ts.Node): boolean => ts.isNumericLiteral(node) && node.text === '2';

  it('gives the line of each node that holds in a .ts, once per node', () => {
    expect(linesWhere('const a = 1;\nconst b = 2;\nconst c = [2, 2];', 'format.ts', isTwo)).toEqual([2, 3, 3]);
  });

  it('reads only the <script> blocks of a .vue, each node at its own line of the file', () => {
    const component = [
      '<template>{{ 2 }}</template>',
      '<script lang="ts">',
      'export const a = 2;',
      '</script>',
      '<script setup lang="ts">',
      'const b: number = 1;',
      'const c = 2;',
      '</script>',
    ].join('\n');
    expect(linesWhere(component, 'Total.vue', isTwo)).toEqual([3, 7]);
  });

  it('gives nothing when no node holds', () => {
    expect(linesWhere('const a = 1;', 'format.ts', isTwo)).toEqual([]);
  });
});

describe('frontendSources and findingsByApp', () => {
  let root: string;
  const put = (path: string, text = '') => {
    mkdirSync(dirname(join(root, path)), { recursive: true });
    writeFileSync(join(root, path), text);
  };

  beforeEach(() => {
    root = mkdtempSync(join(tmpdir(), 'frontend-sources-'));
  });

  afterEach(() => {
    rmSync(root, { recursive: true, force: true });
  });

  it('reads the .ts and .vue of a frontend, and no test, test helper, declaration, build or dependency', () => {
    for (const path of [
      'apps/a/frontend/lib/format.ts',
      'apps/a/frontend/pages/ListPage.vue',
      'apps/a/frontend/lib/format.test.ts',
      'apps/a/frontend/env.d.ts',
      'apps/a/frontend/__tests__/mount.ts',
      'apps/a/frontend/generated/api.ts',
      'apps/a/frontend/dist/app.ts',
      'apps/a/frontend/node_modules/x/index.ts',
      'apps/a/frontend/.cache/x.ts',
      'apps/a/frontend/lib/notes.md',
    ]) {
      put(path);
    }
    expect(frontendSources(join(root, 'apps/a/frontend')).map((file) => file.slice(root.length + 1))).toEqual([
      'apps/a/frontend/lib/format.ts',
      'apps/a/frontend/pages/ListPage.vue',
    ]);
  });

  it('reports what a guard finds by app, as path:line from the hub, and skips an app without a frontend', () => {
    put('base/frontend/lib/home.ts', 'ok\nbad\n');
    put('apps/a/frontend/lib/format.ts', 'bad\nok\nbad\n');
    put('apps/b/frontend/lib/format.ts', 'ok\n');
    const frontends = [
      { app: 'base', dir: join(root, 'base/frontend') },
      { app: 'a', dir: join(root, 'apps/a/frontend') },
      { app: 'b', dir: join(root, 'apps/b/frontend') },
      { app: 'c', dir: join(root, 'apps/c/frontend') },
    ];
    const bad = (text: string) => text.split('\n').flatMap((line, index) => (line === 'bad' ? [index + 1] : []));
    expect(findingsByApp(frontends, bad, root)).toEqual({
      base: ['base/frontend/lib/home.ts:2'],
      a: ['apps/a/frontend/lib/format.ts:1', 'apps/a/frontend/lib/format.ts:3'],
    });
  });
});

describe('hubFrontends', () => {
  it('names base, every app of the hub and, when asked, the shared `ui`', () => {
    const names = (ui: boolean) => hubFrontends({ ui }).map((frontend) => frontend.app);
    expect(names(false)).toEqual(expect.arrayContaining(['base', 'sale', 'inventory']));
    expect(names(false)).not.toContain('ui');
    expect(names(true)).toContain('ui');
    const sale = hubFrontends({ ui: false }).find((frontend) => frontend.app === 'sale');
    expect(sale?.dir.endsWith(join('apps', 'sale', 'frontend'))).toBe(true);
  });
});

// @vitest-environment node
// Guardrail: the e2e reads the page's requests only through `resource-timing.ts`. In the dev stack Vite's modules
// fill Chrome's resource timing buffer (250 entries) before the first click, so `performance.getEntriesByType
// ('resource')`, `performance.getEntries()` or `performance.getEntriesByName(…)` miss what came after it, in silence
// (2026-10-16: `NaN` in delete-item, `null` in optimistic-add-line and two-tabs-live, a blind module check in
// no-outfitkit). Reading other entry types (`'navigation'`: csp, hmr, prod-csp) is fine.
import { mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { afterEach, beforeEach, describe, expect, it } from 'vitest';

const HERE = dirname(fileURLToPath(import.meta.url));

/** A literal entry type other than `resource` (`'navigation'`, `"paint"`…): its buffer is not the one that fills. */
const OTHER_TYPE = /^\s*(['"`])(?!resource\1)[\w-]+\1\s*$/;
const CALL = /performance\s*\.\s*(getEntriesByType|getEntriesByName|getEntries)\s*\(([^)]*)\)/g;

/** Every read of the resource buffer in `source`, as `<line>: <call>`. */
function resourceBufferReads(source: string): string[] {
  const reads: string[] = [];
  for (const match of source.matchAll(CALL)) {
    const [call, method, args] = match;
    const type = method === 'getEntriesByType' ? args : method === 'getEntriesByName' ? args.split(',')[1] : undefined;
    if (type !== undefined && OTHER_TYPE.test(type)) continue;
    const line = source.slice(0, match.index).split('\n').length;
    reads.push(`${line}: ${call.replace(/\s+/g, '')}`);
  }
  return reads;
}

/** Folders that are not the e2e's own code: the runs' evidence and installed packages. */
const SKIPPED_DIRS = new Set(['.artifacts', 'node_modules']);

/**
 * The e2e's own files under `root`, at any depth (Playwright finds specs in subfolders too), as paths relative to
 * it: specs and helpers, not the Vitest tests, nor the recorder (`resource-timing.ts` at the top).
 */
function e2eSources(root = HERE): string[] {
  const walk = (dir: string): string[] =>
    readdirSync(join(root, dir), { withFileTypes: true }).flatMap((entry) => {
      const path = dir ? `${dir}/${entry.name}` : entry.name;
      if (entry.isDirectory()) return SKIPPED_DIRS.has(entry.name) ? [] : walk(path);
      const ownCode = entry.name.endsWith('.ts') && !entry.name.endsWith('.test.ts') && path !== 'resource-timing.ts';
      return ownCode ? [path] : [];
    });
  return walk('').sort();
}

/** Every read of the resource buffer in the e2e's files under `root`, as `<file>:<line>: <call>`. */
function bufferReadsIn(root = HERE): string[] {
  return e2eSources(root).flatMap((name) =>
    resourceBufferReads(readFileSync(join(root, name), 'utf8')).map((read) => `${name}:${read}`),
  );
}

describe('resourceBufferReads', () => {
  it('flags the resource buffer however it is written', () => {
    const source = [
      "performance.getEntriesByType('resource')",
      'performance\n  .getEntriesByType("resource")',
      'window.performance.getEntriesByType(`resource`)',
      'performance.getEntries()',
      "performance.getEntriesByName('http://a.localhost/api/demo/items')",
      "performance.getEntriesByName(url, 'resource')",
      'performance.getEntriesByType(type)',
    ].join('\n');

    expect(resourceBufferReads(source)).toEqual([
      "1: performance.getEntriesByType('resource')",
      '2: performance.getEntriesByType("resource")',
      '4: performance.getEntriesByType(`resource`)',
      '5: performance.getEntries()',
      "6: performance.getEntriesByName('http://a.localhost/api/demo/items')",
      "7: performance.getEntriesByName(url,'resource')",
      '8: performance.getEntriesByType(type)',
    ]);
  });

  it('lets other entry types through', () => {
    const source = [
      "performance.getEntriesByType('navigation').length",
      'performance.getEntriesByType("paint")',
      "performance.getEntriesByName('first-contentful-paint', 'paint')",
      'list.getEntries()',
    ].join('\n');

    expect(resourceBufferReads(source)).toEqual([]);
  });
});

describe('the e2e reads requests through resource-timing.ts', () => {
  it('scans the specs and the helpers', () => {
    const sources = e2eSources();

    expect(sources).toEqual(expect.arrayContaining(['delete-item.spec.ts', 'helpers.ts', 'hmr.spec.ts']));
    expect(sources).not.toContain('resource-timing.ts');
  });

  it('no spec or helper reads the resource buffer', () => {
    expect(bufferReadsIn(), 'use recordResponses + responseEnd / resourceUrls from resource-timing.ts').toEqual([]);
  });
});

describe('e2eSources + bufferReadsIn on a tree of their own', () => {
  const READ = "const entries = performance.getEntriesByType('resource');\n";
  let root: string;
  const write = (path: string, source: string): void => {
    mkdirSync(dirname(join(root, path)), { recursive: true });
    writeFileSync(join(root, path), source);
  };

  beforeEach(() => {
    root = mkdtempSync(join(tmpdir(), 'e2e-resource-reads-'));
  });
  afterEach(() => rmSync(root, { recursive: true, force: true }));

  it('finds a read of the buffer in a spec of a subfolder (Playwright runs those too)', () => {
    write('top.spec.ts', "performance.getEntriesByType('navigation');\n");
    write('sales/nested/deep.spec.ts', `// a nested spec\n${READ}`);

    expect(e2eSources(root)).toEqual(['sales/nested/deep.spec.ts', 'top.spec.ts']);
    expect(bufferReadsIn(root)).toEqual(["sales/nested/deep.spec.ts:2: performance.getEntriesByType('resource')"]);
  });

  it('skips .artifacts, node_modules, the Vitest tests and the recorder itself, at any depth', () => {
    write('.artifacts/test-results/copy.spec.ts', READ);
    write('node_modules/some-package/index.ts', READ);
    write('helpers.test.ts', READ);
    write('sales/sale.test.ts', READ);
    write('resource-timing.ts', READ);
    write('sales/resource-timing.ts', READ);

    expect(e2eSources(root)).toEqual(['sales/resource-timing.ts']);
  });
});

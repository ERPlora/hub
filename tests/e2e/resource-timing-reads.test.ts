// @vitest-environment node
// Guardrail: the e2e reads the page's requests only through `resource-timing.ts`. In the dev stack Vite's modules
// fill Chrome's resource timing buffer (250 entries) before the first click, so `performance.getEntriesByType
// ('resource')`, `performance.getEntries()` or `performance.getEntriesByName(…)` miss what came after it, in silence
// (2026-10-16: `NaN` in delete-item, `null` in optimistic-add-line and two-tabs-live, a blind module check in
// no-outfitkit). Reading other entry types (`'navigation'`: csp, hmr, prod-csp) is fine.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

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

/** The e2e's own files that run in or drive the page: specs and helpers, not the Vitest tests. */
function e2eSources(): string[] {
  return readdirSync(HERE)
    .filter((name) => name.endsWith('.ts') && !name.endsWith('.test.ts') && name !== 'resource-timing.ts')
    .sort();
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
    const reads = e2eSources().flatMap((name) =>
      resourceBufferReads(readFileSync(join(HERE, name), 'utf8')).map((read) => `${name}:${read}`),
    );

    expect(reads, 'use recordResponses + responseEnd / resourceUrls from resource-timing.ts').toEqual([]);
  });
});

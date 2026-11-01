// @vitest-environment node
// Guardrail: every e2e spec that loads a template into a business (it first empties it of what a template brings,
// `emptyOfTemplateData` of helpers.ts) leaves it empty again after its tests: `emptyOfTemplateData` in a
// `test.afterAll` or `test.afterEach` of its own, or each load undone in a `finally` (`/settings/data/imports/undo`,
// as base-apps-born-off.spec.ts does). The business is the one every later spec of the run uses: until hub#529
// base-data.spec.ts left the template's services, products and categories in `a`, and the specs after it found them
// (SALE-F12's «All» started with a service; WEBSITE-F05's catalogue and website.spec.ts's published page showed six
// categories instead of two).
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import ts from 'typescript';
import { describe, expect, it } from 'vitest';

const HERE = dirname(fileURLToPath(import.meta.url));

/** Folders that are not the e2e's own code: the runs' evidence and installed packages. */
const SKIPPED_DIRS = new Set(['.artifacts', 'node_modules']);

/** The hooks that run once a spec's tests are over, failed ones included. */
const AFTER_HOOKS = new Set(['test.afterAll', 'test.afterEach']);

/** The route that undoes one load (`base.blueprint` undo): what the load brought goes. */
const UNDO = '/settings/data/imports/undo';

/** Every spec under `root`, at any depth (Playwright finds them in subfolders too), relative to it. */
function e2eSpecs(root = HERE): string[] {
  const walk = (dir: string): string[] =>
    readdirSync(join(root, dir), { withFileTypes: true }).flatMap((entry) => {
      const path = dir ? `${dir}/${entry.name}` : entry.name;
      if (entry.isDirectory()) return SKIPPED_DIRS.has(entry.name) ? [] : walk(path);
      return entry.name.endsWith('.spec.ts') ? [path] : [];
    });
  return walk('').sort();
}

/** Whether `node` or anything under it is what `found` looks for. */
function contains(node: ts.Node, found: (node: ts.Node) => boolean): boolean {
  return found(node) || (ts.forEachChild(node, (child) => contains(child, found) || undefined) ?? false);
}

const empties = (node: ts.Node): boolean =>
  ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === 'emptyOfTemplateData';

/** `test.afterAll(…)` or `test.afterEach(…)` whose body empties the business again. */
const emptiesAfter = (node: ts.Node): boolean =>
  ts.isCallExpression(node) && AFTER_HOOKS.has(node.expression.getText()) && contains(node, empties);

/** A `try … finally` whose `finally` undoes the load. */
const undoesInFinally = (node: ts.Node): boolean =>
  ts.isTryStatement(node) &&
  node.finallyBlock !== undefined &&
  contains(node.finallyBlock, (inner) => ts.isStringLiteralLike(inner) && inner.text === UNDO);

/** Whether the spec `file` (`source`) loads a template into a business and never puts that business back. */
export function leavesTemplateData(file: string, source: string): boolean {
  const spec = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  if (!contains(spec, empties)) return false;
  return !contains(spec, (node) => emptiesAfter(node) || undoesInFinally(node));
}

describe('every spec that loads a template into a business', () => {
  it('leaves it empty of what the template brought once its tests are over', () => {
    const specs = e2eSpecs().map((file) => ({ file, source: readFileSync(join(HERE, file), 'utf8') }));
    // Not a guard that finds nothing to guard: Settings › Data and the business born with every app off load one.
    expect(specs.filter(({ source }) => source.includes('emptyOfTemplateData(')).length).toBeGreaterThan(1);
    expect(specs.filter(({ file, source }) => leavesTemplateData(file, source)).map(({ file }) => file)).toEqual([]);
  });
});

describe('leavesTemplateData', () => {
  const loading = (after: string) => `
    ${after}
    test('x', async ({ browser }) => {
      const { context, page } = await hostPage(browser, A);
      await emptyOfTemplateData(context, A);
      await page.locator('[data-testid^="blueprint-card-use-"]').first().click();
    });`;

  it('passes a spec that empties the business again in an afterAll or an afterEach', () => {
    const afterAll = `test.afterAll(async ({ browser }) => {
      const { context } = await hostPage(browser, A);
      try { await emptyOfTemplateData(context, A); } finally { await context.close(); }
    });`;
    expect(leavesTemplateData('x.spec.ts', loading(afterAll))).toBe(false);
    expect(leavesTemplateData('x.spec.ts', loading('test.afterEach(async () => { await emptyOfTemplateData(owner, A); });'))).toBe(false);
  });

  it('passes a spec that undoes its load in a finally (base-apps-born-off.spec.ts)', () => {
    const undone = `
      test('x', async ({ browser }) => {
        const { context } = await hostPage(browser, A);
        let loadId = '';
        try {
          await emptyOfTemplateData(context, A);
          loadId = await load(context);
        } finally {
          if (loadId) await api(context, A, 'POST', '/settings/data/imports/undo', { id: loadId });
          await context.close();
        }
      });`;
    expect(leavesTemplateData('x.spec.ts', undone)).toBe(false);
  });

  it('names a spec that empties the business first and never again (base-data.spec.ts until hub#529)', () => {
    expect(leavesTemplateData('x.spec.ts', loading(''))).toBe(true);
    expect(leavesTemplateData('x.spec.ts', loading('test.afterAll(() => psql("drop table if exists rows"));'))).toBe(true);
  });

  it('wants it after the tests, and the undo in a finally, not before them nor in a try', () => {
    expect(leavesTemplateData('x.spec.ts', loading('test.beforeAll(async () => { await emptyOfTemplateData(owner, A); });'))).toBe(true);
    expect(leavesTemplateData('x.spec.ts', loading('test.beforeEach(async () => { await emptyOfTemplateData(owner, A); });'))).toBe(true);
    const inTry = loading("try { await api(owner, A, 'POST', '/settings/data/imports/undo', { id }); } catch { throw new Error('x'); }");
    expect(leavesTemplateData('x.spec.ts', inTry)).toBe(true);
  });

  it('leaves alone a spec that loads no template', () => {
    expect(leavesTemplateData('x.spec.ts', 'test("x", async () => { await clearItems(owner, A); });')).toBe(false);
  });
});

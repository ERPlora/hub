// @vitest-environment node
// Guardrail: every e2e scope (a spec file or one of its `test.describe`) that seeds erplora.com (`seedErplora` of
// whatsapp-helpers.ts, whose push replaces `a`'s photo with erplora.com's: its plan is Free, one device) puts `a`'s
// photo back in its own `test.afterAll`, as its last step (`restorePhoto()`). Until
// FIX-HUB-E2E-WHATSAPP-INBOX-CONNECT-LEAVES-FREE-PLAN only whatsapp-inbox-plan-cap put back what it changed (its
// plan's WhatsApp figure, in erplora.com), and every other spec left `a` on the Free plan: a spec run after it on the
// same database lost its sessions to the device cap (BASE-G57; website-flows.spec.ts, WEBSITE-F11: 401). Last, because
// what the hook pushes after it (a seed again, erplora.com's plan put back) would leave the photo changed once more.
// whatsapp-photo.spec.ts proves the pair itself against the run's real erplora.com.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import ts from 'typescript';
import { describe, expect, it } from 'vitest';

const HERE = dirname(fileURLToPath(import.meta.url));

/** Folders that are not the e2e's own code: the runs' evidence and installed packages. */
const SKIPPED_DIRS = new Set(['.artifacts', 'node_modules']);

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

/** `describe`, `afterAll`… when `node` calls Playwright's `test.<that>(…)` (`describe.serial` included). */
function testCall(node: ts.Node): string | undefined {
  if (!ts.isCallExpression(node)) return undefined;
  const callee = node.expression.getText();
  return callee.startsWith('test.') ? callee.slice('test.'.length) : undefined;
}

const callsTo = (node: ts.Node | undefined, name: string): boolean =>
  node !== undefined && ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === name;

/** The hook `test.afterAll(…)` ends by putting `a`'s photo back: `restorePhoto()` is its last statement. */
function endsRestoring(hook: ts.CallExpression): boolean {
  const fn = hook.arguments.at(-1);
  if (fn === undefined) return false;
  if (ts.isIdentifier(fn)) return fn.text === 'restorePhoto';
  if (!ts.isArrowFunction(fn) && !ts.isFunctionExpression(fn)) return false;
  if (!ts.isBlock(fn.body)) return callsTo(fn.body, 'restorePhoto');
  const last = fn.body.statements.at(-1);
  return last !== undefined && ts.isExpressionStatement(last) && callsTo(last.expression, 'restorePhoto');
}

/** The scopes of the spec `file` (`source`) that call `seedErplora` and do not end an `afterAll` of their own with
 *  `restorePhoto()`: the file itself, or `<file> › <describe's title>` (nested ones joined the same way). */
function unrestored(file: string, source: string): string[] {
  const missing: string[] = [];
  const scope = (name: string, body: ts.Node): void => {
    let seeds = false;
    let restores = false;
    const walk = (node: ts.Node): void => {
      const call = testCall(node);
      if (call?.startsWith('describe') && ts.isCallExpression(node)) {
        const [title] = node.arguments;
        const fn = node.arguments.at(-1);
        if (fn && (ts.isArrowFunction(fn) || ts.isFunctionExpression(fn))) {
          scope(`${name} › ${title && ts.isStringLiteralLike(title) ? title.text : '(describe)'}`, fn.body);
          return;
        }
      }
      if (call === 'afterAll' && ts.isCallExpression(node) && endsRestoring(node)) restores = true;
      if (callsTo(node, 'seedErplora')) seeds = true;
      ts.forEachChild(node, walk);
    };
    ts.forEachChild(body, walk);
    if (seeds && !restores) missing.push(name);
  };
  scope(file, ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS));
  return missing;
}

describe('every spec that seeds erplora.com', () => {
  it('puts a’s photo back last in its afterAll', () => {
    const specs = e2eSpecs().map((file) => ({ file, source: readFileSync(join(HERE, file), 'utf8') }));
    // Not a guard that finds nothing to guard: the WhatsApp specs seed erplora.com.
    expect(specs.filter(({ source }) => source.includes('seedErplora(')).length).toBeGreaterThan(0);
    expect(specs.flatMap(({ file, source }) => unrestored(file, source))).toEqual([]);
  });
});

describe('unrestored', () => {
  const seeding = (afterAll: string) => `
    test.beforeAll(async () => {
      expect(seedErplora()).toEqual({ delivered: true, hub_error: '' });
      await metaGraph();
    });
    ${afterAll}
    test('x', () => {});`;

  it('passes a spec whose afterAll ends with restorePhoto()', () => {
    expect(unrestored('x.spec.ts', seeding('test.afterAll(() => { cleanUp(); restorePhoto(); });'))).toEqual([]);
    expect(unrestored('x.spec.ts', seeding('test.afterAll(() => restorePhoto());'))).toEqual([]);
    expect(unrestored('x.spec.ts', seeding('test.afterAll(restorePhoto);'))).toEqual([]);
    expect(unrestored('x.spec.ts', seeding('test.afterAll(function () { cleanUp(); restorePhoto(); });'))).toEqual([]);
  });

  it('names a spec that seeds and never puts the photo back (what every WhatsApp spec did)', () => {
    expect(unrestored('x.spec.ts', seeding('test.afterAll(() => cleanUp());'))).toEqual(['x.spec.ts']);
    expect(unrestored('x.spec.ts', seeding(''))).toEqual(['x.spec.ts']);
  });

  it('names one that pushes again after putting it back', () => {
    const after = 'test.afterAll(() => { cleanUp(); restorePhoto(); expect(seedErplora()).toEqual({ delivered: true, hub_error: "" }); });';
    expect(unrestored('x.spec.ts', seeding(after))).toEqual(['x.spec.ts']);
  });

  it('wants the restore in the describe that seeds, and leaves alone a spec that does not seed', () => {
    const nested = `
      test.describe('the month spent', () => {
        test.beforeAll(() => { seedErplora({ used: 30 }); });
        test.afterAll(() => cleanUp());
      });
      test.afterAll(() => { restorePhoto(); });`;
    expect(unrestored('x.spec.ts', nested)).toEqual(['x.spec.ts › the month spent']);
    const inner = `
      test.beforeAll(() => { seedErplora(); });
      test.describe('one', () => { test.afterAll(() => restorePhoto()); });`;
    expect(unrestored('x.spec.ts', inner)).toEqual(['x.spec.ts']);
    expect(unrestored('x.spec.ts', 'test.afterAll(() => cleanUp()); test("x", () => { pushChannel({ status: "connected" }); });')).toEqual([]);
  });
});

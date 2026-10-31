// @vitest-environment node
// Guardrail: every e2e scope (a spec file or one of its `test.describe`) that seeds erplora.com (`seedErplora` of
// whatsapp-helpers.ts, whose push replaces `a`'s photo with erplora.com's: its plan is Free, one device) puts `a`'s
// photo back in its own `test.afterAll`, as its last step (`restorePhoto()`). Until
// FIX-HUB-E2E-WHATSAPP-INBOX-CONNECT-LEAVES-FREE-PLAN only whatsapp-inbox-plan-cap put back what it changed (its
// plan's WhatsApp figure, in erplora.com), and every other spec left `a` on the Free plan: a spec run after it on the
// same database lost its sessions to the device cap (BASE-G57; website-flows.spec.ts, WEBSITE-F11: 401). Last, because
// what the hook pushes after it (a seed again, erplora.com's plan put back) would leave the photo changed once more.
// whatsapp-photo.spec.ts proves the pair itself against the run's real erplora.com.
//
// Seeding is not the only way in: every spec that drives the WhatsApp inbox (it imports whatsapp-helpers.ts) can make
// the Hub call erplora.com — a template sent to Meta's review, a message sent — and erplora.com, which knows `a` since
// the stack's seed, answers some of those calls by pushing `a`'s photo (Meta's refusal of the seed's made-up permission
// marks the number to reconnect, and the photo goes with it). fix-whatsapp-inbox-template-header-thumbnail.spec.ts
// never seeded, so this guard did not look at it, and in a whole run it left `a` on the Free plan for every spec after
// it (hub#528: nine of them failed with 401 or 402 `base.app_limit_reached`). So such a spec keeps `a`'s photo too
// (`keepPhoto()`, or the seed that calls it) and, keeping it, puts it back last like a seeding scope.
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

/** The hook `test.beforeAll(keepPhoto)`: `keepPhoto` handed over as the hook itself. */
const hookIsKeepPhoto = (node: ts.Node): boolean => {
  if (testCall(node) !== 'beforeAll' || !ts.isCallExpression(node)) return false;
  const fn = node.arguments.at(-1);
  return fn !== undefined && ts.isIdentifier(fn) && fn.text === 'keepPhoto';
};

/** `node` keeps `a`'s photo for a later `restorePhoto()`: `keepPhoto()` (or `test.beforeAll(keepPhoto)`), or
 *  `seedErplora(…)`, which calls it. */
const keeps = (node: ts.Node): boolean =>
  callsTo(node, 'seedErplora') || callsTo(node, 'keepPhoto') || hookIsKeepPhoto(node);

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

/** The scopes of the spec `file` (`source`) that keep `a`'s photo (`keepPhoto` or `seedErplora`) and do not end an
 *  `afterAll` of their own with `restorePhoto()`: the file itself, or `<file> › <describe's title>` (nested ones joined
 *  the same way). */
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
      if (keeps(node)) seeds = true;
      ts.forEachChild(node, walk);
    };
    ts.forEachChild(body, walk);
    if (seeds && !restores) missing.push(name);
  };
  scope(file, ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS));
  return missing;
}

/** The spec `file` (`source`), named, when it drives the WhatsApp inbox — it imports whatsapp-helpers.ts — and never
 *  keeps `a`'s photo: no `keepPhoto()` in a `test.beforeAll` of its own and no `seedErplora(…)` anywhere. Whatever it
 *  makes the Hub ask erplora.com may bring erplora.com's photo of `a` back (hub#528). */
function unkept(file: string, source: string): string[] {
  const sourceFile = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  const drivesInbox = sourceFile.statements.some(
    (statement) =>
      ts.isImportDeclaration(statement) &&
      ts.isStringLiteral(statement.moduleSpecifier) &&
      statement.moduleSpecifier.text === './whatsapp-helpers',
  );
  if (!drivesInbox) return [];
  let kept = false;
  const walk = (node: ts.Node, inBeforeAll: boolean): void => {
    if (callsTo(node, 'seedErplora') || hookIsKeepPhoto(node) || (inBeforeAll && callsTo(node, 'keepPhoto'))) kept = true;
    const within = inBeforeAll || testCall(node) === 'beforeAll';
    ts.forEachChild(node, (child) => walk(child, within));
  };
  walk(sourceFile, false);
  return kept ? [] : [file];
}

describe('every spec that seeds erplora.com', () => {
  it('puts a’s photo back last in its afterAll', () => {
    const specs = e2eSpecs().map((file) => ({ file, source: readFileSync(join(HERE, file), 'utf8') }));
    // Not a guard that finds nothing to guard: the WhatsApp specs seed erplora.com.
    expect(specs.filter(({ source }) => source.includes('seedErplora(')).length).toBeGreaterThan(0);
    expect(specs.flatMap(({ file, source }) => unrestored(file, source))).toEqual([]);
  });
});

describe('every spec that drives the WhatsApp inbox', () => {
  it('keeps a’s photo first (keepPhoto or the seed) and so puts it back last', () => {
    const specs = e2eSpecs().map((file) => ({ file, source: readFileSync(join(HERE, file), 'utf8') }));
    // Not a guard that finds nothing to guard: specs that never seed drive the inbox too.
    const drivers = specs.filter(({ source }) => source.includes("from './whatsapp-helpers'"));
    expect(drivers.filter(({ source }) => !source.includes('seedErplora(')).length).toBeGreaterThan(0);
    expect(drivers.flatMap(({ file, source }) => unkept(file, source))).toEqual([]);
  });
});

describe('unkept', () => {
  const driving = (hooks: string) => `
    import { cleanUp, keepPhoto, pushChannel, restorePhoto } from './whatsapp-helpers';
    ${hooks}
    test('x', () => { pushChannel({ status: 'connected' }); });`;

  it('names a spec that drives the inbox and never keeps the photo (fix-whatsapp-inbox-template-header-thumbnail, hub#528)', () => {
    expect(unkept('x.spec.ts', driving('test.beforeAll(() => cleanUp()); test.afterAll(() => cleanUp());'))).toEqual(['x.spec.ts']);
    expect(unkept('x.spec.ts', driving('test.afterAll(() => { cleanUp(); restorePhoto(); });'))).toEqual(['x.spec.ts']);
  });

  it('passes one that keeps it in a beforeAll, or seeds', () => {
    expect(unkept('x.spec.ts', driving('test.beforeAll(() => { keepPhoto(); cleanUp(); });'))).toEqual([]);
    expect(unkept('x.spec.ts', driving('test.beforeAll(() => keepPhoto());'))).toEqual([]);
    expect(unkept('x.spec.ts', driving('test.beforeAll(keepPhoto);'))).toEqual([]);
    expect(unkept('x.spec.ts', driving("test.describe('one', () => { test.beforeAll(async () => { keepPhoto(); }); });"))).toEqual([]);
    expect(unkept('x.spec.ts', driving("test('seeds', () => { expect(seedErplora()).toEqual({}); });"))).toEqual([]);
  });

  it('names one that keeps it only once a test has already run (too late: erplora.com may have pushed)', () => {
    expect(unkept('x.spec.ts', driving("test('late', () => { keepPhoto(); });"))).toEqual(['x.spec.ts']);
  });

  it('leaves alone a spec that does not drive the inbox', () => {
    expect(unkept('x.spec.ts', "import { A } from './helpers'; test.afterAll(() => cleanUp());")).toEqual([]);
  });

  it('and unrestored wants the restore of a scope that keeps it', () => {
    expect(unrestored('x.spec.ts', driving('test.beforeAll(() => keepPhoto()); test.afterAll(() => cleanUp());'))).toEqual(['x.spec.ts']);
    expect(unrestored('x.spec.ts', driving('test.beforeAll(keepPhoto); test.afterAll(() => cleanUp());'))).toEqual(['x.spec.ts']);
    expect(unrestored('x.spec.ts', driving('test.beforeAll(() => keepPhoto()); test.afterAll(() => { cleanUp(); restorePhoto(); });'))).toEqual([]);
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

// flow: e2e-capture — FIX of the e2e harness (FIX-HUB-E2E-OWN-ANIMATION-WAIT-UNGUARDED)
// Every wait for «nothing moves» in the e2e goes through the one detector of helpers.ts (`settled`, `untilStill`,
// `movingInPage`), which asks every open shadow root too. `document.getAnimations()` leaves shadow roots out, and Ionic
// animates its toasts, dialogs and popovers there: the specs that asked for animations themselves let a toast still
// entering pass for still (the FIX-HUB-*-E2E-WAIT-BLIND-TO-SHADOW-ROOTS family). Their guardrails (`<app>-wait.test.ts`)
// keep the copies out of their own app's files; this one keeps them out of every file of the e2e, as a ratchet:
// `own-animation-waits.json` holds, for each file that still asks for animations itself, how many times; a file can only
// lose them (and then its count goes down, or its line away), never gain them, and a new file has none.
import { mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import ts from 'typescript';
import { describe, expect, it } from 'vitest';

const E2E_DIR = dirname(fileURLToPath(import.meta.url));

/**
 * The files that ask for animations on purpose, and how many times: the detector itself (`movingInPage`), and the two
 * specs that measure it from outside — every root, and the document against a toast's shadow root (`settled.spec.ts`), and
 * a toast still entering once `capture()` returned (`helpers-capture.spec.ts`). They read; they never wait.
 */
const ALLOWED: Record<string, number> = { 'helpers-capture.spec.ts': 1, 'helpers.ts': 1, 'settled.spec.ts': 3 };

/** What is left of the specs' own waits, by file: it only goes down. */
const RATCHET = JSON.parse(readFileSync(join(E2E_DIR, 'own-animation-waits.json'), 'utf8')) as Record<string, number>;

const NAME = 'getAnimations';

const WAIT_WITH_THE_DETECTOR =
  'wait with settled(page) or untilStill(page) of helpers.ts, which also sees the shadow roots, instead of asking for ' +
  'getAnimations() yourself (and never raise a count in own-animation-waits.json)';

const LOWER_THE_RATCHET =
  'a file that lost getAnimations() reads lowers its count in own-animation-waits.json, or drops its line at 0 ' +
  '(helpers.ts, settled.spec.ts and helpers-capture.spec.ts: their number in ALLOWED of own-animation-waits.test.ts)';

/**
 * How many times `source` reaches for `getAnimations` in its code, comments left out: a call
 * (`document.getAnimations()`, `root?.getAnimations ()`), a reference kept under another name
 * (`const read = document.getAnimations`, `const { getAnimations } = document`) and the name in a string or a template
 * (`document['getAnimations']()`, `page.evaluate('document.getAnimations()')`), escapes decoded.
 */
function animationReads(source: string, fileName = 'spec.ts'): number {
  let reads = 0;
  const visit = (node: ts.Node): void => {
    if (ts.isIdentifier(node) || ts.isPrivateIdentifier(node)) {
      if (node.text === NAME) reads += 1;
    } else if (
      ts.isStringLiteralLike(node) ||
      ts.isTemplateHead(node) ||
      ts.isTemplateMiddle(node) ||
      ts.isTemplateTail(node)
    ) {
      reads += node.text.split(NAME).length - 1;
    }
    ts.forEachChild(node, visit);
  };
  visit(ts.createSourceFile(fileName, source, ts.ScriptTarget.Latest, true));
  return reads;
}

/**
 * Whether the guardrail reads `name` (a path under tests/e2e/): the specs and their helpers at any depth (`.ts` and
 * `.js`), outside dot folders (the screenshots of `.artifacts/`) and node_modules, without Vitest's own tests (the
 * `*.test.ts` of this folder, the ones Vitest runs, which name the call to forbid it).
 */
function scanned(name: string): boolean {
  const parts = name.split(/[\\/]/);
  if (!/\.[cm]?[jt]s$/.test(name) || (parts.length === 1 && name.endsWith('.test.ts'))) return false;
  return !parts.some((part) => part.startsWith('.') || part === 'node_modules');
}

/** Each file under `dir` (the e2e's folder) that reaches for `getAnimations`, and how many times. */
function readsByFile(dir = E2E_DIR): Record<string, number> {
  const found: Record<string, number> = {};
  for (const name of readdirSync(dir, { recursive: true, encoding: 'utf8' }).filter(scanned)) {
    const reads = animationReads(readFileSync(join(dir, name), 'utf8'), name);
    if (reads > 0) found[name.split(/[\\/]/).join('/')] = reads;
  }
  return found;
}

const allowed = (name: string): number => ALLOWED[name] ?? RATCHET[name] ?? 0;

/** The files of `found` that ask for animations more times than they may: their number in `ALLOWED`, else the ratchet's, else none. */
function overTheRatchet(found: Record<string, number>): string[] {
  return Object.entries(found)
    .filter(([name, reads]) => reads > allowed(name))
    .map(([name, reads]) => `${name}: ${reads} getAnimations reads, ${allowed(name)} allowed`);
}

/** The files of `ALLOWED` and the ratchet that `found` shows asking for animations fewer times than their number. */
function staleInTheRatchet(found: Record<string, number>): string[] {
  return Object.keys({ ...ALLOWED, ...RATCHET })
    .filter((name) => (found[name] ?? 0) < allowed(name))
    .map((name) => `${name}: ${found[name] ?? 0} getAnimations reads, the ratchet says ${allowed(name)}`);
}

describe('the e2e waits for «nothing moves» with the one detector of helpers.ts', () => {
  it('no file asks for animations more times than the ratchet lists: a new wait is settled(page) or untilStill(page)', () => {
    expect(overTheRatchet(readsByFile()), WAIT_WITH_THE_DETECTOR).toEqual([]);
  });

  it('the ratchet only goes down: a file that asks for animations fewer times lowers its count in own-animation-waits.json', () => {
    expect(staleInTheRatchet(readsByFile()), LOWER_THE_RATCHET).toEqual([]);
  });

  it('the ratchet lists only files with own waits left, none of the allowed ones, in order', () => {
    const names = Object.keys(RATCHET);
    expect(Object.entries(RATCHET).filter(([, reads]) => !(Number.isInteger(reads) && reads > 0))).toEqual([]);
    expect(names.filter((name) => name in ALLOWED)).toEqual([]);
    expect(names).toEqual([...names].sort());
  });

  it('a new file has none, at any depth, a listed one not one more, and one that lost a read lowers its number', () => {
    const dir = mkdtempSync(join(tmpdir(), 'own-animation-waits-'));
    try {
      mkdirSync(join(dir, 'lib'));
      mkdirSync(join(dir, '.artifacts'));
      writeFileSync(join(dir, 'zz-new.spec.ts'), 'await page.waitForFunction(() => document.getAnimations().length === 0);\n');
      writeFileSync(join(dir, 'lib', 'wait.ts'), "export const moving = (page) => page.evaluate('document.getAnimations().length');\n");
      writeFileSync(join(dir, 'helpers.ts'), 'const moving = document.getAnimations();\nconst more = root.getAnimations();\n');
      writeFileSync(join(dir, '.artifacts', 'report.js'), 'document.getAnimations();\n');
      writeFileSync(join(dir, 'zz-wait.test.ts'), 'document.getAnimations();\n');
      expect(overTheRatchet(readsByFile(dir)).sort()).toEqual([
        'helpers.ts: 2 getAnimations reads, 1 allowed',
        'lib/wait.ts: 1 getAnimations reads, 0 allowed',
        'zz-new.spec.ts: 1 getAnimations reads, 0 allowed',
      ]);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
    expect(staleInTheRatchet({ ...ALLOWED, ...RATCHET, 'settled.spec.ts': 2 })).toEqual([
      'settled.spec.ts: 2 getAnimations reads, the ratchet says 3',
    ]);
  });

  it('the count reads every way of reaching getAnimations in code, and comments and the detector’s helpers as none', () => {
    const blind = "  await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== 'running'));";
    expect(animationReads(blind)).toBe(1);
    expect(animationReads('const knob = toggle.shadowRoot?.getAnimations().length;')).toBe(1);
    expect(animationReads('const moving = document.getAnimations ();')).toBe(1);
    expect(animationReads('const read = document.getAnimations;\nread.call(document);')).toBe(1);
    expect(animationReads('const { getAnimations } = document;')).toBe(1);
    expect(animationReads("const moving = document['getAnimations']();")).toBe(1);
    expect(animationReads('const moving = document[`getAnimations`]();')).toBe(1);
    expect(animationReads("await page.evaluate('document.getAnimations().length');")).toBe(1);
    expect(animationReads('await page.evaluate(`${root}.getAnimations().length`);')).toBe(1);
    expect(animationReads('const moving = Element.prototype.getAnimations.call(label);')).toBe(1);
    expect(animationReads("const moving = document.getAnim\\u0061tions();")).toBe(1);
    expect(animationReads("const moving = document['getAnim\\x61tions']();")).toBe(1);
    expect(animationReads("await page.goto('http://a.localhost/'); const moving = document.getAnimations();")).toBe(1);
    expect(animationReads('const moving = document.getAnimations(), more = root.getAnimations();', 'helpers.js')).toBe(2);
    expect(animationReads('// document.getAnimations() leaves shadow roots out\n/** getAnimations() */\nawait settled(page);')).toBe(0);
    expect(animationReads('await untilStill(page);\nconst moving = await movingInPage(page);')).toBe(0);
  });

  it('it reads every spec and helper, at any depth, but Vitest’s own tests and what is not code', () => {
    const files = ['sale-pos.spec.ts', 'sale-helpers.ts', 'lib/wait.ts', 'lib/wait.test.ts', 'helpers.mjs', 'lib/wait.cjs'];
    expect(files.filter(scanned)).toEqual(files);
    const skipped = ['own-animation-waits.test.ts', 'sale-wait.test.ts', 'README.md', 'raw-screenshots.json', '.artifacts/report/index.js', 'node_modules/pkg/index.js'];
    expect(skipped.filter(scanned)).toEqual([]);
  });
});

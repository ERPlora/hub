// @vitest-environment node
// The time budgets of the hub's Vitest run follow the machine's load (hub#765): Vitest's own (5 s a test, 10 s a hook,
// 1 s a `vi.waitFor`) stretched as the machine, with the run's own workers, slows down. A test or hook whose work is
// synchronous names no clock of its own (hub#1200): the guardrail at the end holds every test file of the run to it.
import { globSync, readFileSync } from 'node:fs';
import { dirname, join, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

import ts from 'typescript';
import { describe, expect, it } from 'vitest';

import config from './vite.config';
import { loadScale, NO_CLOCK, scaleWaitFor } from './vitest.load';

const HUB_DIR = dirname(fileURLToPath(import.meta.url));

describe('loadScale', () => {
  it('counts the run\'s own workers in the load it will run under: Vitest\'s one per core but one', () => {
    expect(loadScale([0, 0, 0], 15)).toBeCloseTo(1.87, 2);
    expect(loadScale([0, 0, 0], 15, 14)).toBeCloseTo(1.87, 2);
    expect(loadScale([0, 0, 0], 1)).toBe(2);
  });

  it('is 1 while the machine\'s load and the run\'s workers fit in half its cores', () => {
    expect(loadScale([0, 0, 0], 16, 8)).toBe(1);
    expect(loadScale([2, 1, 0], 15, 5)).toBe(1);
  });

  it('is twice that load per core above: the CPU slowdown measured at load ~80 over 15 cores', () => {
    expect(loadScale([31, 20, 5], 10, 9)).toBe(8);
    expect(loadScale([100, 90, 80], 15, 14)).toBeCloseTo(15.2, 5);
    expect(loadScale([25, 16, 18], 15, 14)).toBeCloseTo(5.2, 5);
  });

  it('follows the busier of the last minute and the last five, never the last fifteen', () => {
    expect(loadScale([30, 60, 10], 15, 15)).toBe(10);
    expect(loadScale([60, 30, 10], 15, 15)).toBe(10);
    expect(loadScale([1, 1, 90], 15, 4)).toBe(1);
  });

  it('is 1 when the machine reports no load (Windows) and has cores to spare, or gives no number', () => {
    expect(loadScale([], 15, 4)).toBe(1);
    expect(loadScale([Number.NaN, Number.NaN, Number.NaN], 15)).toBe(1);
    expect(loadScale([60, 60, 60], 0)).toBe(1);
  });

  it('reads this machine by default: a number no smaller than 1', () => {
    const scale = loadScale();
    expect(Number.isFinite(scale)).toBe(true);
    expect(scale).toBeGreaterThanOrEqual(1);
  });
});

describe('scaleWaitFor', () => {
  it('gives a vi.waitFor without a budget its default second times the scale', () => {
    expect(scaleWaitFor(undefined, 3)).toEqual({ timeout: 3_000 });
  });

  it('scales the budget a vi.waitFor names, as a number or as an option, and keeps its interval', () => {
    expect(scaleWaitFor(2_000, 2.5)).toBe(5_000);
    expect(scaleWaitFor({ timeout: 400, interval: 20 }, 3)).toEqual({ timeout: 1_200, interval: 20 });
    expect(scaleWaitFor({ interval: 20 }, 2)).toEqual({ timeout: 2_000, interval: 20 });
  });

  it('leaves every budget as it is on an idle machine', () => {
    expect(scaleWaitFor(undefined, 1)).toEqual({ timeout: 1_000 });
    expect(scaleWaitFor(250, 1)).toBe(250);
    expect(scaleWaitFor({ timeout: 400, interval: 20 }, 1)).toEqual({ timeout: 400, interval: 20 });
  });

  it('gives whole milliseconds', () => {
    expect(scaleWaitFor(undefined, 13.333_333)).toEqual({ timeout: 13_333 });
    expect(scaleWaitFor(1_000, 1.000_6)).toBe(1_001);
  });
});

/** The functions of Vitest that declare a test or a hook: the budget they name is one of their other arguments. */
const DECLARES = new Set(['it', 'test', 'beforeAll', 'beforeEach', 'afterAll', 'afterEach']);

/** The function `callee` is reached from: `it` for `it`, `it.skip`, `it.each([…])` or `test.concurrent.each(…)`. */
function declaredBy(callee: ts.Expression): string | undefined {
  let current = callee;
  while (ts.isCallExpression(current) || ts.isPropertyAccessExpression(current)) current = current.expression;
  return ts.isIdentifier(current) ? current.text : undefined;
}

/** Whether `fn` has returned once its body has run: it is not `async` and, a block, it returns no value — what it
 *  starts it does not wait for. An arrow whose body is an expression may return a promise: it is not counted. */
function isSynchronous(fn: ts.ArrowFunction | ts.FunctionExpression): boolean {
  const isAsync = fn.modifiers?.some((modifier) => modifier.kind === ts.SyntaxKind.AsyncKeyword);
  if (isAsync || !ts.isBlock(fn.body)) return false;
  let returns = false;
  const visit = (node: ts.Node): void => {
    // What a function inside it returns is not its own.
    if (returns || ts.isFunctionLike(node)) return;
    if (ts.isReturnStatement(node) && node.expression) returns = true;
    else ts.forEachChild(node, visit);
  };
  ts.forEachChild(fn.body, visit);
  return !returns;
}

/** The clock `argument` names: a budget in milliseconds, or the `timeout` of an options object. `NO_CLOCK` is none. */
function clockOf(argument: ts.Expression): ts.Node | undefined {
  if (ts.isObjectLiteralExpression(argument)) {
    const timeout = argument.properties.find((property) => property.name?.getText() === 'timeout');
    if (!timeout || !ts.isPropertyAssignment(timeout)) return timeout;
    return clockOf(timeout.initializer);
  }
  return ts.isIdentifier(argument) && argument.text === 'NO_CLOCK' ? undefined : argument;
}

/** The lines of `text`, a test file, where a synchronous test or hook names a clock of its own. */
function ownClocks(text: string): number[] {
  const source = ts.createSourceFile('test.ts', text, ts.ScriptTarget.Latest, true);
  const lines: number[] = [];
  const visit = (node: ts.Node): void => {
    const declares = ts.isCallExpression(node) ? declaredBy(node.expression) : undefined;
    if (ts.isCallExpression(node) && declares && DECLARES.has(declares)) {
      const fn = node.arguments.find((argument) => ts.isArrowFunction(argument) || ts.isFunctionExpression(argument));
      if (fn && isSynchronous(fn as ts.ArrowFunction | ts.FunctionExpression)) {
        // A test's first argument is its name; a hook has none.
        const named = declares === 'it' || declares === 'test';
        const others = node.arguments.filter((argument, index) => argument !== fn && (index > 0 || !named));
        const clock = others.map(clockOf).find((found) => found !== undefined);
        if (clock) lines.push(source.getLineAndCharacterOfPosition(clock.getStart()).line + 1);
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return lines;
}

/** Every synchronous test or hook of the run's test files (the config's `include`) that names a clock, as
 *  `<path>:<line>`. */
function ownClocksOfTheRun(): string[] {
  return globSync(config.test?.include ?? [], { cwd: HUB_DIR })
    .filter((file) => !file.split(sep).includes('node_modules'))
    .sort()
    .flatMap((file) => ownClocks(readFileSync(join(HUB_DIR, file), 'utf8')).map((line) => `${file}:${line}`));
}

const NAME_NO_CLOCK =
  'a synchronous test or hook that names a clock of its own: Vitest looks at that clock only once the test has ' +
  'returned (vitest#2920), so it never cuts one that hangs and only turns red, after the fact, a correct run the ' +
  'machine made slow. Give it NO_CLOCK (vitest.load.ts)';

describe('guardrail: no synchronous test or hook of the Hub names a clock of its own (hub#1200)', () => {
  it('counts the budget of a test or hook that has returned once its body has run, and none of one that waits', () => {
    const planted = [
      // A number, a name and the options before or after it, through `each`: lines 3, 6, 7 and 12.
      "it('walks the tree', () => {",
      '  expect(walk()).toEqual({});',
      '}, 60_000);',
      'beforeAll(() => {',
      '  warm();',
      '}, BUDGET);',
      "it('reads', { timeout: 60_000 }, () => {",
      '  read();',
      '});',
      "it.each(['a'])('reads %s', function (name) {",
      '  read(name);',
      '}, { timeout: 30_000, retry: 1 });',
      // It waits, or may wait (what it returns), so the clock can cut it.
      "it('lints', async () => {",
      '  await lint();',
      '}, 60_000);',
      "it('spawns', () => {",
      '  return spawn();',
      '}, 60_000);',
      "it('polls', () => poll(), 60_000);",
      // No clock of its own: no budget, `NO_CLOCK`, or options without one.
      "it('walks without a clock', () => {",
      '  walk();',
      '}, NO_CLOCK);',
      "test('names none', () => {",
      '  walk();',
      '});',
      "it('retries', { timeout: NO_CLOCK, retry: 2 }, () => {",
      '  walk();',
      '});',
      // What a callback inside returns is not the test returning: line 31.
      "it('maps', () => {",
      '  expect([1].map((n) => { return n; })).toEqual([1]);',
      '}, 5_000);',
      // A suite's options are its tests' (each judged by its own function).
      "describe('a suite', { timeout: 60_000 }, () => {});",
    ].join('\n');
    expect(ownClocks(planted)).toEqual([3, 6, 7, 12, 31]);
  });

  // It reads every test file of the run (some 900): its work is synchronous, so it names no clock either.
  it('every test file of the run keeps to it', () => {
    expect(ownClocksOfTheRun(), NAME_NO_CLOCK).toEqual([]);
  }, NO_CLOCK);
});

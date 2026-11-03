// @vitest-environment node
// flow: ninguno — FIX of the e2e harness (hub#480)
// A spec file that needs some apps on turns on, in its `beforeAll`, those that are off in the business and turns them
// off again in its `afterAll`. Five assistant specs kept «what was on» in a module-level `let wasOn = new Set()` filled
// after the check of the SaaS's assistant provider: when that check fell (a stack whose SaaS lacks the seed), `wasOn`
// stayed empty and the `afterAll` turned off every app it needed, though the business had them on — Time clock, Staff,
// Pricing, Cart checkout… — and the specs that came after failed one after another (404 on their routes, 409
// `base.app_required` on the way). Now the `beforeAll` records each app once it is on (`turnOnMissing`) and the
// `afterAll` turns off that record and nothing else, last first (`turnOffTurnedOn`, helpers.ts): a file that fell before
// turning anything on leaves the business as it found it. The guardrail keeps it so: no hook, and no function a hook
// can call, posts `/apps/disable` itself; only a test does (turning an app off is what some tests prove) and the one
// helper, which every file hands the record its own `turnOnMissing` filled (never `NEEDED` or a copy).
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import ts from 'typescript';
import { describe, expect, it } from 'vitest';

import { turnOffRecorded, turnOnRecording } from './apps-turned-on';

const HERE = dirname(fileURLToPath(import.meta.url));

/** Folders that are not the e2e's own code: the runs' evidence and installed packages. */
const SKIPPED_DIRS = new Set(['.artifacts', 'node_modules']);

/** Apps' own command to turn an app off (`base.app.disable`). */
const DISABLE = '/apps/disable';

/** The one place outside a test that turns an app off: `turnOffTurnedOn`, which turns off only what was recorded. */
const ALLOWED = new Set(['helpers.ts']);

/** Every source of the e2e under `root` (specs and their helpers, at any depth; not Vitest's own tests). */
function e2eSources(root = HERE): string[] {
  const walk = (dir: string): string[] =>
    readdirSync(join(root, dir), { withFileTypes: true }).flatMap((entry) => {
      const path = dir ? `${dir}/${entry.name}` : entry.name;
      if (entry.isDirectory()) return SKIPPED_DIRS.has(entry.name) ? [] : walk(path);
      return entry.name.endsWith('.ts') && !entry.name.endsWith('.test.ts') ? [path] : [];
    });
  return walk('').sort();
}

/** Where `file` (`source`) posts `/apps/disable` anywhere but inside a test of its own (`test('…', …)`): in a hook
 *  (`test.afterAll`, `test.beforeEach`…), at the top of the file or in a function a hook may call. `file:line` each. */
function disablesOutsideATest(file: string, source: string): string[] {
  const sourceFile = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  const found: string[] = [];
  const walk = (node: ts.Node, inTest: boolean): void => {
    if (!inTest && ts.isStringLiteralLike(node) && node.text === DISABLE) {
      found.push(`${file}:${sourceFile.getLineAndCharacterOfPosition(node.getStart()).line + 1}`);
    }
    const within = inTest || (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === 'test');
    ts.forEachChild(node, (child) => walk(child, within));
  };
  walk(sourceFile, false);
  return found;
}

/** Where `file` (`source`) posts `/apps/disable` other than from the callback that `turnOffTurnedOn` hands to
 *  `turnOffRecorded(turnedOn, …)`: an app turned off that the record never held. `file:line` each. */
function disablesOffTheRecord(file: string, source: string): string[] {
  const sourceFile = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  const ofTheRecord = (node: ts.Node): boolean => {
    let inCallback = false;
    for (let up: ts.Node | undefined = node.parent; up; up = up.parent) {
      if (ts.isArrowFunction(up) || ts.isFunctionExpression(up)) {
        const call = up.parent;
        inCallback =
          ts.isCallExpression(call) &&
          ts.isIdentifier(call.expression) &&
          call.expression.text === 'turnOffRecorded' &&
          call.arguments.at(-1) === up &&
          call.arguments[0] !== undefined &&
          ts.isIdentifier(call.arguments[0]) &&
          call.arguments[0].text === 'turnedOn';
        if (!inCallback) return false;
      }
      if (ts.isFunctionDeclaration(up)) return inCallback && up.name?.text === 'turnOffTurnedOn';
    }
    return false;
  };
  const found: string[] = [];
  const walk = (node: ts.Node): void => {
    if (ts.isStringLiteralLike(node) && node.text === DISABLE && !ofTheRecord(node)) {
      found.push(`${file}:${sourceFile.getLineAndCharacterOfPosition(node.getStart()).line + 1}`);
    }
    ts.forEachChild(node, walk);
  };
  walk(sourceFile);
  return found;
}

/** Where `file` (`source`) hands `turnOffTurnedOn` something other than a record its own `turnOnMissing` filled (a
 *  list of its own such as `NEEDED`, or a copy): hub#480 again, through the helper. `file:line` each. */
function turnsOffOffTheRecord(file: string, source: string): string[] {
  const sourceFile = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  const calls: ts.CallExpression[] = [];
  const walk = (node: ts.Node): void => {
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression)) calls.push(node);
    ts.forEachChild(node, walk);
  };
  walk(sourceFile);
  const named = (call: ts.CallExpression, name: string): boolean => (call.expression as ts.Identifier).text === name;
  const records = new Set(
    calls.filter((call) => named(call, 'turnOnMissing')).flatMap((call) => {
      const record = call.arguments[3];
      return record !== undefined && ts.isIdentifier(record) ? [record.text] : [];
    }),
  );
  return calls
    .filter((call) => named(call, 'turnOffTurnedOn'))
    .filter((call) => {
      const record = call.arguments[2];
      return record === undefined || !ts.isIdentifier(record) || !records.has(record.text);
    })
    .map((call) => `${file}:${sourceFile.getLineAndCharacterOfPosition(call.getStart()).line + 1}`);
}

describe('turnOnRecording', () => {
  it('turns on, in order, only the needed apps that are off, and records each one once it is on', async () => {
    const calls: string[] = [];
    const turnedOn: string[] = [];
    await turnOnRecording(['staff', 'attendance', 'customer'], new Set(['customer']), async (app) => {
      expect(turnedOn, `${app} recorded before it was on`).not.toContain(app);
      calls.push(app);
    }, turnedOn);
    expect(calls).toEqual(['staff', 'attendance']);
    expect(turnedOn).toEqual(['staff', 'attendance']);
  });

  it('records nothing for an app whose turning on failed, and keeps what was on before it', async () => {
    const turnedOn: string[] = [];
    const failing = turnOnRecording(['customer', 'tax', 'sale'], new Set(), async (app) => {
      if (app === 'tax') throw new Error('turn on tax: 409');
    }, turnedOn);
    await expect(failing).rejects.toThrow('turn on tax: 409');
    expect(turnedOn).toEqual(['customer']);
  });

  it('records nothing when every needed app was already on', async () => {
    const turnedOn: string[] = [];
    await turnOnRecording(['staff'], new Set(['staff']), async () => {
      throw new Error('nothing to turn on');
    }, turnedOn);
    expect(turnedOn).toEqual([]);
  });
});

describe('turnOffRecorded', () => {
  it('turns off what was recorded and nothing else, last first, and empties the record', async () => {
    const calls: string[] = [];
    const turnedOn = ['customer', 'tax', 'sale', 'table'];
    await turnOffRecorded(turnedOn, async (app) => {
      calls.push(app);
    });
    expect(calls).toEqual(['table', 'sale', 'tax', 'customer']);
    expect(turnedOn).toEqual([]);
  });

  it('turns off nothing when nothing was turned on: a beforeAll that fell first leaves the business as it was (hub#480)', async () => {
    const calls: string[] = [];
    await turnOffRecorded([], async (app) => {
      calls.push(app);
    });
    expect(calls).toEqual([]);
  });

  it('keeps recorded the app it could not turn off and those before it', async () => {
    const turnedOn = ['staff', 'attendance', 'task'];
    const failing = turnOffRecorded(turnedOn, async (app) => {
      if (app === 'attendance') throw new Error('turn off attendance: 409');
    });
    await expect(failing).rejects.toThrow('turn off attendance: 409');
    expect(turnedOn).toEqual(['staff', 'attendance']);
  });
});

describe('every source of the e2e', () => {
  it('turns an app off only inside a test, or through turnOffTurnedOn', () => {
    const sources = e2eSources().map((file) => ({ file, source: readFileSync(join(HERE, file), 'utf8') }));
    // Not a guard that finds nothing to guard: tests turn apps off, and the helper does.
    expect(sources.filter(({ source }) => source.includes(DISABLE)).length).toBeGreaterThan(1);
    const offenders = sources.filter(({ file }) => !ALLOWED.has(file)).flatMap(({ file, source }) => disablesOutsideATest(file, source));
    expect(offenders, 'turn off in an afterAll with turnOffTurnedOn(context, origin, turnedOn) of helpers.ts').toEqual([]);
  });

  it('hands turnOffTurnedOn only the record its own turnOnMissing filled', () => {
    const sources = e2eSources().map((file) => ({ file, source: readFileSync(join(HERE, file), 'utf8') }));
    expect(sources.filter(({ source }) => /turnOffTurnedOn\(context/.test(source)).length).toBeGreaterThan(1);
    const offenders = sources.flatMap(({ file, source }) => turnsOffOffTheRecord(file, source));
    expect(offenders, 'hand turnOffTurnedOn the same list the file handed turnOnMissing').toEqual([]);
  });

  it('and helpers.ts posts it once, for each app of the record (turnOffTurnedOn → turnOffRecorded)', () => {
    const source = readFileSync(join(HERE, 'helpers.ts'), 'utf8');
    expect(disablesOutsideATest('helpers.ts', source)).toHaveLength(1);
    expect(disablesOffTheRecord('helpers.ts', source)).toEqual([]);
  });
});

describe('disablesOffTheRecord', () => {
  const post = `const off = await api(context, origin, 'POST', '${DISABLE}', { app });`;

  it('passes the helper that turns off each app of the record', () => {
    const helper = `export async function turnOffTurnedOn(context, origin, turnedOn) {\n  await turnOffRecorded(turnedOn, async (app) => {\n    ${post}\n  });\n}`;
    expect(disablesOffTheRecord('helpers.ts', helper)).toEqual([]);
  });

  it('names one that turns off a list of its own, or hands the record a callback that is not the one posting', () => {
    const own = `export async function turnOffTurnedOn(context, origin, turnedOn) {\n  for (const app of NEEDED) {\n    ${post}\n  }\n}`;
    expect(disablesOffTheRecord('helpers.ts', own)).toEqual(['helpers.ts:3']);
    const aside = `export async function turnOffTurnedOn(context, origin, turnedOn) {\n  turnOffRecorded; await each(['x'], async (app) => {\n    ${post}\n  });\n}`;
    expect(disablesOffTheRecord('helpers.ts', aside)).toEqual(['helpers.ts:3']);
    const otherList = `export async function turnOffTurnedOn(context, origin, turnedOn) {\n  await turnOffRecorded(NEEDED, async (app) => {\n    ${post}\n  });\n}`;
    expect(disablesOffTheRecord('helpers.ts', otherList)).toEqual(['helpers.ts:3']);
  });

  it('names one posted from another function of helpers.ts', () => {
    const other = `export async function turnOffAll(context, origin, turnedOn) {\n  await turnOffRecorded(turnedOn, async (app) => {\n    ${post}\n  });\n}`;
    expect(disablesOffTheRecord('helpers.ts', other)).toEqual(['helpers.ts:3']);
  });
});

describe('turnsOffOffTheRecord', () => {
  const on = 'test.beforeAll(async () => {\n  await turnOnMissing(context, A, NEEDED, turnedOn);\n});';

  it('passes a file whose afterAll hands the record its turnOnMissing filled', () => {
    const spec = `${on}\ntest.afterAll(async () => {\n  await turnOffTurnedOn(context, A, turnedOn);\n});`;
    expect(turnsOffOffTheRecord('x.spec.ts', spec)).toEqual([]);
  });

  it('names one that hands it NEEDED, a copy of the record, or a record no turnOnMissing filled (hub#480)', () => {
    for (const record of ['NEEDED', '[...NEEDED]', '[...turnedOn]', 'other']) {
      const spec = `${on}\ntest.afterAll(async () => {\n  await turnOffTurnedOn(context, A, ${record});\n});`;
      expect(turnsOffOffTheRecord('x.spec.ts', spec), record).toEqual(['x.spec.ts:5']);
    }
  });
});

describe('disablesOutsideATest', () => {
  const line = `const off = await api(context, A, 'POST', '${DISABLE}', { app });`;

  it('names an afterAll that posts it itself (the five assistant specs of hub#480)', () => {
    const spec = `let wasOn = new Set<string>();\ntest.afterAll(async () => {\n  for (const app of NEEDED) {\n    ${line}\n  }\n});`;
    expect(disablesOutsideATest('x.spec.ts', spec)).toEqual(['x.spec.ts:4']);
  });

  it('names a beforeEach, a function at the top of the file and a template literal', () => {
    expect(disablesOutsideATest('x.spec.ts', `test.beforeEach(async () => { ${line} });`)).toEqual(['x.spec.ts:1']);
    expect(disablesOutsideATest('x.ts', `export async function off(app: string) {\n  ${line}\n}`)).toEqual(['x.ts:2']);
    expect(disablesOutsideATest('x.spec.ts', `test.afterAll(() => api(c, A, 'POST', \`${DISABLE}\`, {}));`)).toEqual(['x.spec.ts:1']);
  });

  it('passes one inside a test, at any depth, and one inside a describe’s test', () => {
    expect(disablesOutsideATest('x.spec.ts', `test('off', async () => { ${line} });`)).toEqual([]);
    expect(disablesOutsideATest('x.spec.ts', `test.describe('d', () => { test('off', async () => { if (x) { ${line} } }); });`)).toEqual([]);
  });

  it('leaves alone other paths', () => {
    expect(disablesOutsideATest('x.spec.ts', "test.afterAll(() => api(c, A, 'POST', '/apps/enable', {}));")).toEqual([]);
  });
});

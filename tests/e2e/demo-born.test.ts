// flow: ninguno — arnés e2e del Hub (hub#1061)
// demo.spec.ts waited 15 s for a demo and failed on a loaded machine with nothing broken (the demo was ready 15.3 s
// after it was asked for). Those 15 s stood for a fact: a demo's sign-up is the clone of its template (PLAN-DB §6), and
// one that makes its tables again took 13–32 s. The spec now waits for the demo without a clock of its own and checks
// that fact instead: every migration its database has came with its template's clone, none was applied at its sign-up.
import { describe, expect, it } from 'vitest';

import { demoBeingPrepared, migrationsAppliedAtSignUp, notFromItsTemplate, templateOf } from './demo-born';
import type { CommandResult } from './global-setup';

const CONTROL = 'hub_e2e_30610';
const DEMO_DB = `${CONTROL}_demo_0193a1b2c3d4`;

/** `psql` on each database as `rows` says, by the database it is asked on and the statement's first words. */
function fakeSql(rows: Record<string, (statement: string) => CommandResult>): (database: string) => (statement: string) => CommandResult {
  return (database) => (statement) => {
    const answer = rows[database];
    if (!answer) return { status: 2, stdout: '', stderr: `psql: database "${database}" does not exist` };
    return answer(statement);
  };
}

const ok = (lines: string[]): CommandResult => ({ status: 0, stdout: lines.join('\n'), stderr: '' });

const TEMPLATE_ROWS = [
  'base.0001_initial 2026-11-12 05:10:01.100001',
  'live.0001_initial 2026-11-12 05:10:01.200002',
  'tax.0001_initial 2026-11-12 05:10:02.300003',
];

describe('templateOf(): the template a hub is cloned from, as base/tenancy/names.py template_db_name names it', () => {
  it('is <control>_template without a vertical', () => {
    expect(templateOf(CONTROL, '')).toBe(`${CONTROL}_template`);
  });

  it('is <control>_template_<vertical> with one', () => {
    expect(templateOf(CONTROL, 'restaurant')).toBe(`${CONTROL}_template_restaurant`);
  });
});

describe('notFromItsTemplate(): the migrations of a hub that did not come with its template', () => {
  it('is empty for the clone of its template: the same rows, applied at the same instant', () => {
    expect(notFromItsTemplate(TEMPLATE_ROWS, TEMPLATE_ROWS)).toEqual([]);
  });

  it('lists a migration its template lacks: applied at its sign-up', () => {
    const demo = [...TEMPLATE_ROWS, 'demo.0001_initial 2026-11-12 05:20:07.000001'];
    expect(notFromItsTemplate(demo, TEMPLATE_ROWS)).toEqual(['demo.0001_initial 2026-11-12 05:20:07.000001']);
  });

  it('lists a migration its template has, applied again at its sign-up: its tables made again, not cloned', () => {
    const demo = ['base.0001_initial 2026-11-12 05:20:05.000001', ...TEMPLATE_ROWS.slice(1)];
    expect(notFromItsTemplate(demo, TEMPLATE_ROWS)).toEqual(['base.0001_initial 2026-11-12 05:20:05.000001']);
  });

  it('is empty when the template got a migration after the clone: the hub took nothing of its own', () => {
    expect(notFromItsTemplate(TEMPLATE_ROWS.slice(0, 2), TEMPLATE_ROWS)).toEqual([]);
  });
});

describe('migrationsAppliedAtSignUp(): what the sign-up of a demo applied to its database', () => {
  const asked: string[] = [];
  const registry = (vertical: string) =>
    fakeSql({
      [CONTROL]: (statement) => {
        asked.push(`${CONTROL}: ${statement}`);
        return ok(statement.includes("slug = 'demo-0193a1b2'") ? [`${DEMO_DB}|${vertical}`] : []);
      },
      [DEMO_DB]: () => ok([...TEMPLATE_ROWS, 'demo.0001_initial 2026-11-12 05:20:07.000001']),
      [templateOf(CONTROL, vertical)]: () => ok(TEMPLATE_ROWS),
    });

  it('reads its database from the registry and compares it with its template', () => {
    expect(migrationsAppliedAtSignUp('demo-0193a1b2', CONTROL, registry(''))).toEqual(['demo.0001_initial 2026-11-12 05:20:07.000001']);
    expect(asked.at(-1)).toMatch(/from base_hub where slug = 'demo-0193a1b2'/);
  });

  it('compares a demo of a vertical with its vertical’s template', () => {
    expect(migrationsAppliedAtSignUp('demo-0193a1b2', CONTROL, registry('restaurant'))).toEqual([
      'demo.0001_initial 2026-11-12 05:20:07.000001',
    ]);
  });

  it('is empty for a demo born as the clone of its template', () => {
    const sql = fakeSql({
      [CONTROL]: () => ok([`${DEMO_DB}|`]),
      [DEMO_DB]: () => ok(TEMPLATE_ROWS),
      [`${CONTROL}_template`]: () => ok(TEMPLATE_ROWS),
    });
    expect(migrationsAppliedAtSignUp('demo-0193a1b2', CONTROL, sql)).toEqual([]);
  });

  it('refuses a demo the registry does not have, or that has no database of its own', () => {
    expect(() => migrationsAppliedAtSignUp('demo-ffffffff', CONTROL, registry(''))).toThrow(
      /no demo 'demo-ffffffff' with a database of its own in the registry of hub_e2e_30610/,
    );
    const shared = fakeSql({ [CONTROL]: () => ok(['|']) });
    expect(() => migrationsAppliedAtSignUp('demo-0193a1b2', CONTROL, shared)).toThrow(/no demo 'demo-0193a1b2' with a database/);
  });

  it('says which read failed and why, never an empty list', () => {
    const missingTemplate = fakeSql({ [CONTROL]: () => ok([`${DEMO_DB}|`]), [DEMO_DB]: () => ok(TEMPLATE_ROWS) });
    expect(() => migrationsAppliedAtSignUp('demo-0193a1b2', CONTROL, missingTemplate)).toThrow(
      /hub_e2e_30610_template: psql: database "hub_e2e_30610_template" does not exist/,
    );
    const emptyTemplate = fakeSql({
      [CONTROL]: () => ok([`${DEMO_DB}|`]),
      [DEMO_DB]: () => ok(TEMPLATE_ROWS),
      [`${CONTROL}_template`]: () => ok([]),
    });
    expect(() => migrationsAppliedAtSignUp('demo-0193a1b2', CONTROL, emptyTemplate)).toThrow(/no migrations in hub_e2e_30610_template/);
  });
});

describe('demoBeingPrepared(): the newest demo of the registry, for a door that said not_ready', () => {
  it('reads its slug, its status and its last error', () => {
    const sql = fakeSql({ [CONTROL]: () => ok(['demo-0193a1b2|failed|template_missing: The template is not on this cluster']) });
    expect(demoBeingPrepared(CONTROL, sql)).toEqual({
      slug: 'demo-0193a1b2',
      status: 'failed',
      lastError: 'template_missing: The template is not on this cluster',
    });
  });

  it('keeps a last error that has the separator in it', () => {
    const sql = fakeSql({ [CONTROL]: () => ok(['demo-0193a1b2|failed|unexpected: a|b']) });
    expect(demoBeingPrepared(CONTROL, sql)?.lastError).toBe('unexpected: a|b');
  });

  it('is null when the registry has no demo', () => {
    expect(demoBeingPrepared(CONTROL, fakeSql({ [CONTROL]: () => ok([]) }))).toBeNull();
  });
});

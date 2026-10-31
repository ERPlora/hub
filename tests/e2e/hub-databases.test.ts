// Where a spec's SQL goes since every hub has its own database (round 2026-10-30 of PLAN-DB, S2a): control's tables
// (the registry, Django's users and sessions, the memberships) to the stack's control database, every other table to
// the hub's own (`a` unless the spec names another), read from the registry once per hub. A statement that names both
// cannot run anywhere now (no query crosses two databases): it is refused, saying how to split it.
import { describe, expect, it, vi } from 'vitest';

import { hubDatabases, plan, statementsOf, tablesOf } from './hub-databases';

describe('tablesOf', () => {
  it('reads the tables a statement names, after from, join, into, update, table and its subqueries', () => {
    expect(
      tablesOf(
        "select h.id from base_hubuser h join auth_user u on u.username = h.username where u.email = 'x'",
      ),
    ).toEqual(['base_hubuser', 'auth_user']);
    expect(tablesOf('delete from printing_printjob; insert into base_appactivation (host) values (1)')).toEqual([
      'printing_printjob',
      'base_appactivation',
    ]);
    expect(tablesOf('UPDATE base_hub SET state = 1 WHERE id = 2')).toEqual(['base_hub']);
    expect(tablesOf('drop table if exists e2e_rows; create table e2e_rows as select * from base_appactivation')).toEqual([
      'e2e_rows',
      'e2e_rows',
      'base_appactivation',
    ]);
    expect(tablesOf("select (select id from auth_user where email = 'x') from staff_member")).toEqual([
      'auth_user',
      'staff_member',
    ]);
  });

  it('reads a quoted name whole, and never takes a keyword or a function for a table', () => {
    expect(tablesOf('drop table if exists \\"e2e-fix-printing-hooks-parked\\"')).toEqual(['e2e-fix-printing-hooks-parked']);
    expect(tablesOf('drop table if exists "e2e-fix-printing-hooks-parked"')).toEqual(['e2e-fix-printing-hooks-parked']);
    expect(
      tablesOf("insert into base_hub (id) values ('x') on conflict (id) do update set state = excluded.state"),
    ).toEqual(['base_hub']);
    expect(tablesOf("select x from jsonb_array_elements('[]'::jsonb) x")).toEqual([]);
  });
});

describe('statementsOf', () => {
  it("splits at each ; outside a quoted string or name, and drops the empty ones", () => {
    expect(
      statementsOf(
        `update base_hub set state = '{\\"plan\\": \\"a;b\\"}' where slug = 'it''s; fine'; drop table "e2e;x";; select 1;`,
      ),
    ).toEqual([
      `update base_hub set state = '{\\"plan\\": \\"a;b\\"}' where slug = 'it''s; fine'`,
      'drop table "e2e;x"',
      'select 1',
    ]);
  });
});

describe('plan', () => {
  const hubs = (slug: string) => `hub_e2e_8030_${slug}_db`;
  const CONTROL = 'hub_e2e_8030';

  it('runs each statement where its tables live, the ones in a row on one database together, in order', () => {
    const made = new Map<string, string>();
    expect(
      plan(
        "delete from staff_member where first_name like 'E2E%'; select count(*) from auth_user; select count(*) from django_session; delete from printing_printjob",
        'a',
        CONTROL,
        hubs,
        made,
      ),
    ).toEqual([
      { database: 'hub_e2e_8030_a_db', sql: "delete from staff_member where first_name like 'E2E%'" },
      { database: CONTROL, sql: 'select count(*) from auth_user; select count(*) from django_session' },
      { database: 'hub_e2e_8030_a_db', sql: 'delete from printing_printjob' },
    ]);
  });

  it('remembers where a scratch table was made, across calls, until it is dropped', () => {
    const made = new Map<string, string>();
    const backup = 'e2e_backup_photo';
    expect(
      plan(`drop table if exists ${backup}; create table ${backup} as select id, state from base_hub`, 'a', CONTROL, hubs, made),
    ).toEqual([{ database: CONTROL, sql: `drop table if exists ${backup}; create table ${backup} as select id, state from base_hub` }]);
    expect(plan('create table e2e_rows as select * from base_appactivation', 'a', CONTROL, hubs, made)).toEqual([
      { database: 'hub_e2e_8030_a_db', sql: 'create table e2e_rows as select * from base_appactivation' },
    ]);

    // The putting back names both, one statement each: each goes where its table was made.
    expect(
      plan(
        `update base_hub h set state = b.state from ${backup} b where b.id = h.id; drop table ${backup}; drop table e2e_rows`,
        'a',
        CONTROL,
        hubs,
        made,
      ),
    ).toEqual([
      { database: CONTROL, sql: `update base_hub h set state = b.state from ${backup} b where b.id = h.id; drop table ${backup}` },
      { database: 'hub_e2e_8030_a_db', sql: 'drop table e2e_rows' },
    ]);
    expect([...made.keys()]).toEqual([]);
  });

  it("runs SQL that names no table at all on control's, where the live notices are heard; a statement without one goes with its neighbours", () => {
    const made = new Map<string, string>();
    expect(plan("SELECT pg_notify('live_host_b', '*')", 'b', CONTROL, hubs, made)).toEqual([
      { database: CONTROL, sql: "SELECT pg_notify('live_host_b', '*')" },
    ]);
    expect(
      plan(
        "set client_min_messages = warning; create table if not exists e2e_c as select * from whatsapp_inbox_channel",
        'a',
        CONTROL,
        hubs,
        made,
      ),
    ).toEqual([
      {
        database: 'hub_e2e_8030_a_db',
        sql: 'set client_min_messages = warning; create table if not exists e2e_c as select * from whatsapp_inbox_channel',
      },
    ]);
  });

  it('asks whether a scratch table is still there (to_regclass) where it was made', () => {
    const made = new Map([['e2e_backup_photo', CONTROL]]);
    expect(plan("select to_regclass('e2e_backup_photo') is not null", 'a', CONTROL, hubs, made)).toEqual([
      { database: CONTROL, sql: "select to_regclass('e2e_backup_photo') is not null" },
    ]);
  });

  it("puts a scratch table nobody made yet with the statement next to it, else the hub's", () => {
    const made = new Map<string, string>();
    expect(plan('drop table if exists e2e_x; create table e2e_x as select * from base_membership', 'a', CONTROL, hubs, made)).toEqual([
      { database: CONTROL, sql: 'drop table if exists e2e_x; create table e2e_x as select * from base_membership' },
    ]);
    expect(plan('drop table if exists "e2e-fix-printing-hooks-parked"', 'a', CONTROL, hubs, made)).toEqual([
      { database: 'hub_e2e_8030_a_db', sql: 'drop table if exists "e2e-fix-printing-hooks-parked"' },
    ]);
  });

  it("refuses a statement whose scratch table lives in another database than its other tables", () => {
    const made = new Map([['e2e_rows', 'hub_e2e_8030_a_db']]);
    expect(() => plan('insert into base_hub select * from e2e_rows', 'a', CONTROL, hubs, made)).toThrow(
      /e2e_rows.*hub_e2e_8030_a_db/,
    );
  });

  it('refuses a statement that names tables of both, saying how to split it', () => {
    expect(() =>
      plan("update base_credential set pin_hash = '' where username in (select username from auth_user)", 'a', CONTROL, hubs, new Map()),
    ).toThrow(/auth_user.*base_credential|base_credential.*auth_user/);
  });
});

describe('where one statement runs', () => {
  const hubs = (slug: string) => `hub_e2e_8030_${slug}_db`;
  const on = (sql: string, hub = 'a') => plan(sql, hub, 'hub_e2e_8030', hubs, new Map()).map((run) => run.database);

  it("sends control's tables to the control database", () => {
    for (const sql of [
      "select state_version from base_hub where slug = 'a'",
      "select username from auth_user where email = 'x'",
      'select count(*) from base_membership',
      'select count(*) from django_session',
      'select count(*) from base_sessionowner',
      'select count(*) from base_democode',
    ]) {
      expect(on(sql)).toEqual(['hub_e2e_8030']);
    }
  });

  it("sends every other table to the hub's own database, a's unless another is named", () => {
    expect(on('delete from printing_printjob')).toEqual(['hub_e2e_8030_a_db']);
    expect(on('select count(*) from base_hubuser', 'b')).toEqual(['hub_e2e_8030_b_db']);
    // Look-alikes of control's are a hub's: base_hubuser, base_hub_identity.
    expect(on('select hub_id from base_hub_identity')).toEqual(['hub_e2e_8030_a_db']);
  });

  it("puts a spec's own scratch tables (e2e_…) where the tables it copies or restores live", () => {
    const backup = 'e2e_backup_session_photo';
    expect(on(`drop table if exists ${backup}; create table ${backup} as select id, state from base_hub`)).toEqual([
      'hub_e2e_8030',
    ]);
    expect(on(`update base_hub h set state = b.state from ${backup} b where b.id = h.id`)).toEqual(['hub_e2e_8030']);
    expect(on('create table e2e_rows as select * from base_appactivation')).toEqual(['hub_e2e_8030_a_db']);
    expect(on('select count(*) from e2e_rows')).toEqual(['hub_e2e_8030_a_db']);
    expect(on('drop table if exists "e2e-fix-printing-hooks-parked"')).toEqual(['hub_e2e_8030_a_db']);
  });
});

describe('hubDatabases', () => {
  it("reads each hub's database from the registry once, and a hub that shares control's is control's", () => {
    const read = vi.fn((sql: string) => (sql.includes("'a'") ? 'db:hub_e2e_8030_0123' : 'db:'));
    const of = hubDatabases('hub_e2e_8030', read);

    expect([of('a'), of('a'), of('b')]).toEqual(['hub_e2e_8030_0123', 'hub_e2e_8030_0123', 'hub_e2e_8030']);
    expect(read).toHaveBeenCalledTimes(2);
  });

  it('refuses a hub the registry does not have', () => {
    const of = hubDatabases('hub_e2e_8030', () => '');

    expect(() => of('nobody')).toThrow("no hub 'nobody' in the registry of hub_e2e_8030");
  });
});

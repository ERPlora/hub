// Where a spec's SQL goes since every hub has its own database (round 2026-10-30 of PLAN-DB, S2a): control's tables
// (the registry, Django's users and sessions, the memberships) to the stack's control database, every other table to
// the hub's own (`a` unless the spec names another), read from the registry once per hub. A statement that names both
// cannot run anywhere now (no query crosses two databases): it is refused, saying how to split it.
import { describe, expect, it, vi } from 'vitest';

import { databaseFor, hubDatabases, tablesOf } from './hub-databases';

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
});

describe('databaseFor', () => {
  const hubs = (slug: string) => `hub_e2e_8030_${slug}_db`;

  it("sends control's tables to the control database", () => {
    for (const sql of [
      "select state_version from base_hub where slug = 'a'",
      "select username from auth_user where email = 'x'",
      'select count(*) from base_membership',
      'select count(*) from django_session',
      'select count(*) from base_sessionowner',
      'select count(*) from base_democode',
    ]) {
      expect(databaseFor(sql, 'a', 'hub_e2e_8030', hubs)).toBe('hub_e2e_8030');
    }
  });

  it("sends every other table to the hub's own database, a's unless another is named", () => {
    expect(databaseFor('delete from printing_printjob', 'a', 'hub_e2e_8030', hubs)).toBe('hub_e2e_8030_a_db');
    expect(databaseFor('select count(*) from base_hubuser', 'b', 'hub_e2e_8030', hubs)).toBe('hub_e2e_8030_b_db');
    // Look-alikes of control's are a hub's: base_hubuser, base_hub_identity.
    expect(databaseFor('select hub_id from base_hub_identity', 'a', 'hub_e2e_8030', hubs)).toBe('hub_e2e_8030_a_db');
  });

  it("puts a spec's own scratch tables (e2e_…) where the tables it copies or restores live", () => {
    const backup = 'e2e_backup_session_photo';
    expect(
      databaseFor(`drop table if exists ${backup}; create table ${backup} as select id, state from base_hub`, 'a', 'hub_e2e_8030', hubs),
    ).toBe('hub_e2e_8030');
    expect(databaseFor(`update base_hub h set state = b.state from ${backup} b where b.id = h.id`, 'a', 'hub_e2e_8030', hubs)).toBe(
      'hub_e2e_8030',
    );
    expect(databaseFor('create table e2e_rows as select * from base_appactivation', 'a', 'hub_e2e_8030', hubs)).toBe(
      'hub_e2e_8030_a_db',
    );
    expect(databaseFor('select count(*) from e2e_rows', 'a', 'hub_e2e_8030', hubs)).toBe('hub_e2e_8030_a_db');
    expect(databaseFor('drop table if exists "e2e-fix-printing-hooks-parked"', 'a', 'hub_e2e_8030', hubs)).toBe(
      'hub_e2e_8030_a_db',
    );
  });

  it('refuses a statement that names tables of both, saying how to split it', () => {
    expect(() =>
      databaseFor(
        "select h.id from base_hubuser h join auth_user u on u.username = h.username where u.email = 'x'",
        'a',
        'hub_e2e_8030',
        hubs,
      ),
    ).toThrow(/auth_user.*base_hubuser|base_hubuser.*auth_user/);
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

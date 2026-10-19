// The e2e database of a stack beside the shared one (database.ts): `node tests/e2e/database.ts` creates it
// when missing and migrates it, `--drop` deletes it. On 2026-10-16 two stacks (8030 and 8040) shared the
// default `hub` and the cash sale of one fell into the other's open shift; each stack now runs on its own
// e2e database, and these commands never touch any other (`hub`, `saas`, the templates…). Preparing it also leaves
// the checkout's .env the key that seals the test certificates (certificate-key.ts).
// flow: ninguno — FIX de la infraestructura e2e del Hub (aislar los datos de cada ejecución)
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { newFernetKey } from './certificate-key';
import { adminSql, dropDatabase, prepareDatabase, runCli, type AdminSql } from './database';
import type { CommandResult, ManagePy, Spawn } from './global-setup';

const OK = (stdout = ''): CommandResult => ({ status: 0, stdout, stderr: '' });
const FAILED = (stderr: string): CommandResult => ({ status: 1, stdout: '', stderr });

/** A Postgres double: which databases exist, every statement it got, and an optional failure per statement. */
function fakePostgres(existing: string[], fail: Record<string, string> = {}): { sql: AdminSql; statements: string[] } {
  const statements: string[] = [];
  const databases = new Set(existing);
  return {
    statements,
    sql: (statement) => {
      statements.push(statement);
      const failure = Object.entries(fail).find(([prefix]) => statement.startsWith(prefix));
      if (failure) return FAILED(failure[1]);
      const asked = /^select 1 from pg_database where datname = '([a-z0-9_]+)'$/.exec(statement);
      if (asked) return OK(databases.has(asked[1]) ? '1\n' : '');
      const created = /^create database "([a-z0-9_]+)"$/.exec(statement);
      if (created) databases.add(created[1]);
      const dropped = /^drop database if exists "([a-z0-9_]+)"$/.exec(statement);
      if (dropped) databases.delete(dropped[1]);
      return OK();
    },
  };
}

/** A `manage.py` double: records every call and answers `answers[command]` (success by default). */
function fakeManage(answers: Record<string, CommandResult> = {}): { manage: ManagePy; calls: string[][] } {
  const calls: string[][] = [];
  return { calls, manage: (args) => (calls.push(args), answers[args[0]] ?? OK()) };
}

describe('prepareDatabase', () => {
  it('creates a missing e2e database, migrates it (control and hubs) and leaves `a` and `b` in its registry', () => {
    const postgres = fakePostgres([]);
    const { manage, calls } = fakeManage();

    expect(prepareDatabase('hub_e2e_8030', { sql: postgres.sql, manage })).toEqual({ created: true });
    expect(postgres.statements).toEqual([
      "select 1 from pg_database where datname = 'hub_e2e_8030'",
      'create database "hub_e2e_8030"',
    ]);
    expect(calls).toEqual([['migrate', '--no-input'], ['migrate_hubs'], ['seed_local_hubs']]);
  });

  it('only migrates and seeds one that exists: it is idempotent and keeps its rows', () => {
    const postgres = fakePostgres(['hub_e2e_8030']);
    const { manage, calls } = fakeManage();

    expect(prepareDatabase('hub_e2e_8030', { sql: postgres.sql, manage })).toEqual({ created: false });
    expect(postgres.statements).toEqual(["select 1 from pg_database where datname = 'hub_e2e_8030'"]);
    expect(calls).toEqual([['migrate', '--no-input'], ['migrate_hubs'], ['seed_local_hubs']]);
  });

  it('refuses the shared `hub` and every database that is no e2e one, touching nothing', () => {
    for (const name of ['hub', 'saas', 'postgres', 'hub_template', 'test_hub_next']) {
      const postgres = fakePostgres([name]);
      const { manage, calls } = fakeManage();

      expect(() => prepareDatabase(name, { sql: postgres.sql, manage }), name).toThrow(`DB_NAME=${name} is no e2e database`);
      expect(postgres.statements, name).toEqual([]);
      expect(calls, name).toEqual([]);
    }
  });

  it('stops at the failed step, naming it and saying what the server said', () => {
    const unreachable = fakePostgres([], { select: 'connection to server on socket failed: No such file or directory' });
    expect(() => prepareDatabase('hub_e2e_8030', { sql: unreachable.sql, ...fakeManage() })).toThrow(
      /^Could not read Postgres's databases[^\n]*\nconnection to server on socket failed/,
    );

    const refused = fakePostgres([], { create: 'ERROR:  permission denied to create database' });
    const notMigrated = fakeManage();
    expect(() => prepareDatabase('hub_e2e_8030', { sql: refused.sql, manage: notMigrated.manage })).toThrow(
      /^Could not create the e2e database hub_e2e_8030[^\n]*\nERROR: {2}permission denied to create database/,
    );
    expect(notMigrated.calls).toEqual([]);

    const broken = fakeManage({ migrate: { status: 1, stdout: 'Operations to perform:', stderr: 'django.db.utils.ProgrammingError: boom' } });
    expect(() => prepareDatabase('hub_e2e_8030', { sql: fakePostgres([]).sql, manage: broken.manage })).toThrow(
      /^Could not migrate the e2e database hub_e2e_8030: `manage\.py migrate --no-input` exited with 1:\nOperations to perform:\ndjango\.db\.utils\.ProgrammingError: boom$/,
    );
    expect(broken.calls).toEqual([['migrate', '--no-input']]);

    const hubs = fakeManage({ migrate_hubs: { status: null, stdout: '', stderr: 'killed' } });
    expect(() => prepareDatabase('hub_e2e_8030', { sql: fakePostgres([]).sql, manage: hubs.manage })).toThrow(
      '`manage.py migrate_hubs` exited with no status:\nkilled',
    );

    // The host gate answers 404 to a slug the registry does not have: without `a` and `b`, every spec fails.
    const unseeded = fakeManage({ seed_local_hubs: { status: 1, stdout: '', stderr: 'CommandError: DEBUG' } });
    expect(() => prepareDatabase('hub_e2e_8030', { sql: fakePostgres([]).sql, manage: unseeded.manage })).toThrow(
      /^Could not seed the local hubs of the e2e database hub_e2e_8030: `manage\.py seed_local_hubs` exited with 1:\nCommandError: DEBUG$/,
    );
  });
});

describe('dropDatabase', () => {
  it('drops an e2e database, and a missing one is no error', () => {
    const postgres = fakePostgres(['hub_e2e_8030']);

    dropDatabase('hub_e2e_8030', { sql: postgres.sql });
    dropDatabase('hub_e2e_8030', { sql: postgres.sql });

    expect(postgres.statements).toEqual(['drop database if exists "hub_e2e_8030"', 'drop database if exists "hub_e2e_8030"']);
  });

  it('refuses `hub` and every database that is no e2e one', () => {
    for (const name of ['hub', 'saas', 'hub_template']) {
      const postgres = fakePostgres([name]);
      expect(() => dropDatabase(name, { sql: postgres.sql }), name).toThrow(`DB_NAME=${name} is no e2e database`);
      expect(postgres.statements, name).toEqual([]);
    }
  });

  it('never forces it: with a runserver still connected it fails saying to stop it first', () => {
    const postgres = fakePostgres(['hub_e2e_8030'], {
      drop: 'ERROR:  database "hub_e2e_8030" is being accessed by other users\nDETAIL:  There is 1 other session using the database.',
    });

    expect(() => dropDatabase('hub_e2e_8030', { sql: postgres.sql })).toThrow(
      /^The e2e database hub_e2e_8030 is still in use \(its runserver\?\): stop it and retry\.\nERROR: {2}database "hub_e2e_8030" is being accessed by other users/,
    );
    expect(postgres.statements[0]).not.toMatch(/force/i);
  });
});

describe('runCli', () => {
  function io() {
    const out: string[] = [];
    const err: string[] = [];
    return { out, err, print: (line: string) => out.push(line), fail: (line: string) => err.push(line) };
  }

  const folders: string[] = [];
  afterEach(() => {
    for (const folder of folders.splice(0)) rmSync(folder, { recursive: true, force: true });
  });

  /** A checkout's .env holding `content`, and an environment without the certificate key. */
  function checkout(content: string): { envFile: string; env: NodeJS.ProcessEnv } {
    const folder = mkdtempSync(join(tmpdir(), 'e2e-database-'));
    folders.push(folder);
    const envFile = join(folder, '.env');
    writeFileSync(envFile, content);
    return { envFile, env: {} };
  }

  /** A checkout whose .env already has its certificate key. */
  const keyed = () => checkout(`DEBUG=True\nFISCAL_CERTIFICATE_KEY=${newFernetKey()}\n`);

  it('prepares the database of DB_NAME without arguments and drops it with --drop', () => {
    const postgres = fakePostgres([]);
    const prepared = io();
    expect(runCli([], { database: 'hub_e2e_8030', sql: postgres.sql, manage: fakeManage().manage, ...keyed(), ...prepared })).toBe(0);
    expect(prepared.out[0]).toBe('database.ts: hub_e2e_8030 created, migrated and seeded (a, b).');

    const again = io();
    expect(runCli([], { database: 'hub_e2e_8030', sql: postgres.sql, manage: fakeManage().manage, ...keyed(), ...again })).toBe(0);
    expect(again.out[0]).toBe('database.ts: hub_e2e_8030 migrated and seeded (a, b).');

    const dropped = io();
    expect(runCli(['--drop'], { database: 'hub_e2e_8030', sql: postgres.sql, manage: fakeManage().manage, ...keyed(), ...dropped })).toBe(0);
    expect(dropped.out).toEqual(['database.ts: hub_e2e_8030 dropped.']);
    expect(postgres.statements.at(-1)).toBe('drop database if exists "hub_e2e_8030"');
  });

  it("leaves the checkout's .env a certificate key once the database is ready, and never prints it", () => {
    const stack = checkout('DEBUG=True\n');
    const prepared = io();

    expect(runCli([], { database: 'hub_e2e_8030', sql: fakePostgres([]).sql, manage: fakeManage().manage, ...stack, ...prepared })).toBe(0);

    const given = readFileSync(stack.envFile, 'utf8');
    const [line] = given.split('\n').filter((l) => l.startsWith('FISCAL_CERTIFICATE_KEY='));
    const key = line.slice('FISCAL_CERTIFICATE_KEY='.length);
    expect(key).toMatch(/^[A-Za-z0-9_-]{43}=$/);
    expect(prepared.out).toHaveLength(2);
    expect(prepared.out[1]).toMatch(/^database\.ts: FISCAL_CERTIFICATE_KEY generated in /);
    expect(prepared.out.join('\n')).not.toContain(key);

    // Again on the same checkout: the key it gave is the one the run keeps.
    const kept = io();
    expect(runCli([], { database: 'hub_e2e_8030', sql: fakePostgres(['hub_e2e_8030']).sql, manage: fakeManage().manage, ...stack, ...kept })).toBe(0);
    expect(kept.out[1]).toMatch(/^database\.ts: FISCAL_CERTIFICATE_KEY kept from /);
    expect(readFileSync(stack.envFile, 'utf8')).toBe(given);
  });

  it('exits 1 with the reason on stderr, and 2 on an argument it does not know', () => {
    const refused = io();
    expect(runCli([], { database: 'hub', sql: fakePostgres(['hub']).sql, manage: fakeManage().manage, ...keyed(), ...refused })).toBe(1);
    expect(refused.err.join('\n')).toMatch(/^database\.ts: DB_NAME=hub is no e2e database/);

    const broken = checkout('DEBUG=True\nFISCAL_CERTIFICATE_KEY=not-a-key\n');
    const unusable = io();
    expect(runCli([], { database: 'hub_e2e_8030', sql: fakePostgres([]).sql, manage: fakeManage().manage, ...broken, ...unusable })).toBe(1);
    expect(unusable.err.join('\n')).toMatch(/^database\.ts: FISCAL_CERTIFICATE_KEY in /);

    const unknown = io();
    expect(runCli(['--force'], { database: 'hub_e2e_8030', sql: fakePostgres([]).sql, manage: fakeManage().manage, ...keyed(), ...unknown })).toBe(2);
    expect(unknown.err).toEqual(['database.ts: unknown argument --force. Usage: node tests/e2e/database.ts [--drop]']);
  });

  it('never gives a key to a database it refused, nor when dropping one', () => {
    for (const [args, database] of [[[], 'hub'], [['--drop'], 'hub_e2e_8030']] as const) {
      const stack = checkout('DEBUG=True\n');
      runCli([...args], { database, sql: fakePostgres(['hub', 'hub_e2e_8030']).sql, manage: fakeManage().manage, ...stack, ...io() });
      expect(readFileSync(stack.envFile, 'utf8')).toBe('DEBUG=True\n');
    }
  });
});

describe('adminSql', () => {
  it("runs one statement with psql in compose's Postgres, on the maintenance database, stopping at the first error", () => {
    const seen: { command: string; args: string[] }[] = [];
    const spawn: Spawn = (command, args) => (seen.push({ command, args }), { status: 0, stdout: '1\n', stderr: '' });

    expect(adminSql(spawn)('select 1')).toEqual({ status: 0, stdout: '1\n', stderr: '' });
    expect(seen).toEqual([
      {
        command: 'docker',
        args: ['compose', 'exec', '-T', 'postgres', 'psql', '-U', 'hub', '-d', 'postgres', '-v', 'ON_ERROR_STOP=1', '-At', '-c', 'select 1'],
      },
    ]);
  });

  it('turns a docker that never started into a result without status that says why', () => {
    const spawn: Spawn = () => ({ status: null, stdout: null, stderr: null, error: new Error('spawnSync docker ENOENT') });

    expect(adminSql(spawn)('select 1')).toEqual({ status: null, stdout: '', stderr: 'spawnSync docker ENOENT' });
  });
});

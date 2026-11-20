// @vitest-environment node
// Every scenario starts from the same business: a copy of `a`'s own database taken once per run, put back before each
// scenario, so what one assistant did (or broke) in a scenario never changes the next one.
import { describe, expect, it } from 'vitest';

import { copyCountStatement, copyOf, dropCopyStatements, onServer, restoreStatements, snapshotStatements } from './assistant-snapshot';

const HUB = 'hub_e2e_8980_01a1f558e78b7698be40493ec211f7eb';

describe('copyOf', () => {
  it('names the copy after the business\'s database, and only of an e2e stack', () => {
    expect(copyOf(HUB)).toBe(`${HUB}_qa`);
    expect(() => copyOf('hub_01a1f558e78b7698be40493ec211f7eb')).toThrow(/e2e/);
    expect(() => copyOf('hub_e2e_8980')).toThrow(/business/);
    expect(() => copyOf(`${HUB}; drop database hub`)).toThrow(/business/);
  });
});

describe('the statements', () => {
  const closing = `select pg_terminate_backend(pid) from pg_stat_activity where datname = '${HUB}' and pid <> pg_backend_pid()`;

  it('copies the database with no one connected to it, replacing an earlier copy', () => {
    expect(snapshotStatements(HUB)).toEqual([closing, `drop database if exists "${HUB}_qa"`, `create database "${HUB}_qa" template "${HUB}"`]);
  });

  it('puts the copy back in its place, with no one connected', () => {
    expect(restoreStatements(HUB)).toEqual([closing, `drop database "${HUB}"`, `create database "${HUB}" template "${HUB}_qa"`]);
  });

  it('counts the copy before anything is put back, so a business is never dropped without one', () => {
    expect(copyCountStatement(HUB)).toBe(`select count(*) from pg_database where datname = '${HUB}_qa'`);
  });

  it('drops the copy at the end of the run', () => {
    expect(dropCopyStatements(HUB)).toEqual([`drop database if exists "${HUB}_qa"`]);
  });
});

describe('onServer', () => {
  it('runs each statement on its own on the maintenance database, stopping at the first error', () => {
    const seen: string[][] = [];
    expect(onServer(['select 1', 'select 2'], '/repo', (file, args, options) => (seen.push([file, ...args, options.cwd]), '1\n'))).toBe('1');
    expect(seen).toEqual([
      ['docker', 'compose', 'exec', '-T', 'postgres', 'psql', '-U', 'hub', '-d', 'postgres', '-v', 'ON_ERROR_STOP=1', '-At', '-c', 'select 1', '-c', 'select 2', '/repo'],
    ]);
  });
});

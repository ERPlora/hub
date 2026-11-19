// The business every scenario starts from: a copy of `a`'s own database (`<database>_qa`), taken once per run after
// the apps are on and the owner has signed in, and put back before each scenario, so what one assistant did (or broke)
// never changes the next scenario. Each statement runs on the server's maintenance database with no one connected to
// the copied one; only a business database of an e2e stack is ever copied or replaced. Pure but for the command it
// is given, so Vitest proves it (assistant-snapshot.test.ts).
import { execFileSync } from 'node:child_process';

const BUSINESS = /^hub_[a-z0-9_]*e2e[a-z0-9_]*_[0-9a-f]{32}$/;

/** The copy's name; refuses anything but a business database of an e2e stack. */
export function copyOf(database: string): string {
  if (!database.includes('e2e')) throw new Error(`${database} is no e2e database: a scenario run only copies a stack's own`);
  if (!BUSINESS.test(database)) throw new Error(`${database} is not a business's own database (<control>_<hex>)`);
  return `${database}_qa`;
}

const closing = (database: string): string =>
  `select pg_terminate_backend(pid) from pg_stat_activity where datname = '${database}' and pid <> pg_backend_pid()`;

export const snapshotStatements = (database: string): string[] => {
  const copy = copyOf(database);
  return [closing(database), `drop database if exists "${copy}"`, `create database "${copy}" template "${database}"`];
};

export const restoreStatements = (database: string): string[] => {
  const copy = copyOf(database);
  return [closing(database), `drop database "${database}"`, `create database "${database}" template "${copy}"`];
};

/** How many copies of `database` there are: 1 before anything is put back from one, or nothing is dropped. */
export const copyCountStatement = (database: string): string => `select count(*) from pg_database where datname = '${copyOf(database)}'`;

export const dropCopyStatements = (database: string): string[] => [`drop database if exists "${copyOf(database)}"`];

type Exec = (file: string, args: string[], options: { cwd: string; encoding: 'utf8' }) => string;

/** Runs each statement on its own (a database is never created inside a transaction) on the stack's Postgres; what
 *  they printed. */
export function onServer(statements: string[], cwd: string, exec: Exec = execFileSync as unknown as Exec): string {
  const args = ['compose', 'exec', '-T', 'postgres', 'psql', '-U', 'hub', '-d', 'postgres', '-v', 'ON_ERROR_STOP=1', '-At'];
  return exec('docker', [...args, ...statements.flatMap((statement) => ['-c', statement])], { cwd, encoding: 'utf8' }).trim();
}

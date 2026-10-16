// The e2e database of a stack beside the shared one (`stack.ts`): its own copy of the Hub's control
// database, where phase 1 keeps the business of every hub (`a`, `b`…), so that two runs at once never
// write into each other's (on 2026-10-16 the cash sale of one run fell into the other's open shift).
//
//   DB_NAME=hub_e2e_8030 node tests/e2e/database.ts          creates it when missing, then migrates it
//   DB_NAME=hub_e2e_8030 node tests/e2e/database.ts --drop   drops it once its runserver is stopped
//
// Run it before starting the stack's runserver (which cannot start without its database) and again after
// adding a migration; it keeps the rows of a database that exists. Only e2e databases (`isE2eDatabase`):
// `hub`, `saas`, the templates and every other one are refused untouched. A drop is never forced: with a
// connection open (its runserver) it fails and says so. Postgres is compose.yaml's (`COMPOSE_FILE` points
// at it from a checkout elsewhere), reached as its superuser `hub`, like the specs' `psql()`.
import { spawnSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

import { type CommandResult, type ManagePy, managePy, type Spawn } from './global-setup.ts';
import { isE2eDatabase, STACK } from './stack.ts';

const REPO_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const USAGE = 'Usage: node tests/e2e/database.ts [--drop]';

/** Runs one SQL statement on Postgres's maintenance database `postgres`. */
export type AdminSql = (statement: string) => CommandResult;

/** `psql` in compose's Postgres, as `hub`, on `postgres`, stopping at the first error. */
export function adminSql(spawn: Spawn = spawnSync, env: NodeJS.ProcessEnv = process.env): AdminSql {
  return (statement) => {
    const args = ['compose', 'exec', '-T', 'postgres', 'psql', '-U', 'hub', '-d', 'postgres', '-v', 'ON_ERROR_STOP=1', '-At', '-c', statement];
    const result = spawn('docker', args, { cwd: REPO_DIR, encoding: 'utf8', env });
    return {
      status: result.status,
      stdout: result.stdout ?? '',
      stderr: [result.stderr, result.error?.message].filter(Boolean).join('\n'),
    };
  };
}

function refuseUnlessE2e(name: string): void {
  if (!isE2eDatabase(name)) {
    throw new Error(
      `DB_NAME=${name} is no e2e database: database.ts only creates, migrates and drops a stack's own, ` +
        '`hub_…` with `e2e` as one of its words (`hub_e2e_8030`).',
    );
  }
}

/** What a failed command said, after the line that names it. */
function said(result: CommandResult): string {
  const exit = result.status === null ? 'no status' : String(result.status);
  const output = [result.stdout.trim(), result.stderr.trim()].filter(Boolean).join('\n');
  return `exited with ${exit}:\n${output}`;
}

/** Creates the e2e database `name` when missing, then applies every migration (control and hubs). */
export function prepareDatabase(name: string, { sql, manage }: { sql: AdminSql; manage: ManagePy }): { created: boolean } {
  refuseUnlessE2e(name);
  const found = sql(`select 1 from pg_database where datname = '${name}'`);
  if (found.status !== 0) throw new Error(`Could not read Postgres's databases: psql ${said(found)}`);
  const created = found.stdout.trim() !== '1';
  if (created) {
    const create = sql(`create database "${name}"`);
    if (create.status !== 0) throw new Error(`Could not create the e2e database ${name}: psql ${said(create)}`);
  }
  for (const args of [['migrate', '--no-input'], ['migrate_hubs']]) {
    const run = manage(args);
    if (run.status !== 0) throw new Error(`Could not migrate the e2e database ${name}: \`manage.py ${args.join(' ')}\` ${said(run)}`);
  }
  return { created };
}

/** Drops the e2e database `name` (a missing one is no error); never while a connection is open. */
export function dropDatabase(name: string, { sql }: { sql: AdminSql }): void {
  refuseUnlessE2e(name);
  const drop = sql(`drop database if exists "${name}"`);
  if (drop.status === 0) return;
  if (drop.stderr.includes('is being accessed by other users')) {
    throw new Error(`The e2e database ${name} is still in use (its runserver?): stop it and retry.\n${drop.stderr.trim()}`);
  }
  throw new Error(`Could not drop the e2e database ${name}: psql ${said(drop)}`);
}

/** The command line: prepares `database`, or drops it with `--drop`. Returns the exit status. */
export function runCli(
  args: string[],
  deps: { database: string; sql: AdminSql; manage: ManagePy; print: (line: string) => void; fail: (line: string) => void },
): number {
  const [flag, ...rest] = args;
  if ((flag !== undefined && flag !== '--drop') || rest.length > 0) {
    deps.fail(`database.ts: unknown argument ${flag !== '--drop' ? flag : rest[0]}. ${USAGE}`);
    return 2;
  }
  try {
    if (flag === '--drop') {
      dropDatabase(deps.database, deps);
      deps.print(`database.ts: ${deps.database} dropped.`);
    } else {
      const { created } = prepareDatabase(deps.database, deps);
      deps.print(`database.ts: ${deps.database} ${created ? 'created and migrated' : 'migrated'}.`);
    }
    return 0;
  } catch (error) {
    deps.fail(`database.ts: ${error instanceof Error ? error.message : String(error)}`);
    return 1;
  }
}

// Run as a script (not imported by a test): the database is the run's (`STACK`, which already refused a
// stack beside the shared one without its own when this module was loaded).
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  process.exitCode = runCli(process.argv.slice(2), {
    database: STACK.database,
    sql: adminSql(),
    manage: managePy(STACK.database),
    print: (line) => console.log(line),
    fail: (line) => console.error(line),
  });
}

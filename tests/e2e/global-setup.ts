// The e2e's start: it refuses local databases with unapplied migrations before the first spec. On
// 2026-10-16 the local `hub` lacked verifactu.0003–0005 and the specs failed with «not valid JSON» (the
// `post` helper got Django's HTML error page), a red that never said its cause. It checks the control
// database (`migrate --check`) and the hub databases (`migrate_hubs --check`; phase 1: the control
// database again) of the run's `DB_NAME` (`stack.ts`), and never migrates: other sessions share them.
// A stack's own e2e database that does not exist yet is said as such, with `database.ts`, which creates
// it (runserver cannot start without it, so the e2e cannot create it here). Then it checks that the local
// hubs `a` and `b` are ready in the registry (`seed_local_hubs --check`; without them every host is a 404), and last
// that the stack's SaaS has the demo accounts the specs sign in with (`demo_seed` of the SaaS; one select on its
// database, `STACK.saasDatabase`): on its fresh e2e database it has none, and every login failed on «The email address
// and/or password you specified are not correct.» after 30 s (2026-10-28).
// Before all that it refuses more than one worker: `--workers=N` overrides `workers: 1` of playwright.config.ts, and
// specs running at once on the one stack delete each other's data (2026-10-23: the agenda spec timed out).
import { spawnSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { FullConfig } from '@playwright/test';

import { isE2eDatabase, STACK } from './stack.ts';

const HERE = dirname(fileURLToPath(import.meta.url));
const HUB_DIR = resolve(HERE, '..', '..');
/** Where compose.yaml lives: the root of erplora-next, above hub/ and every hub-wt-*. */
const REPO_DIR = resolve(HUB_DIR, '..');

/** What a `manage.py` command left: its exit status (`null` when it never ran or was killed) and output. */
export interface CommandResult {
  status: number | null;
  stdout: string;
  stderr: string;
}

/** Runs `manage.py` with `args` against the e2e's local databases. */
export type ManagePy = (args: string[]) => CommandResult;

/** `spawnSync` as `managePy` calls it. */
export type Spawn = (
  command: string,
  args: string[],
  options: { cwd: string; encoding: 'utf8'; env: NodeJS.ProcessEnv },
) => { status: number | null; stdout: string | null; stderr: string | null; error?: Error };

/** Each exits 1, listing what a run would apply, if anything is pending, and applies nothing. */
const CHECKS = [
  ['migrate', '--check', '--plan', '--no-color'],
  ['migrate_hubs', '--check', '--no-color'],
];

/** The migrations a check listed: its unindented `<app>.<migration>` lines (`--plan` indents the operations). */
function listedMigrations(output: string): string[] {
  return output.split(/\r?\n/).filter((line) => /^[A-Za-z_]\w*\.\w+$/.test(line));
}

/** Throws, without touching the databases, unless both checks find every migration applied. */
export function assertMigrationsApplied(manage: ManagePy, database: string): void {
  const where = `local databases of the e2e (DB_NAME=${database})`;
  for (const args of CHECKS) {
    const check = manage(args);
    if (check.status === 0) continue;
    const command = `manage.py ${args.join(' ')}`;
    const pending = listedMigrations(check.stdout);
    if (pending.length > 0) {
      const fix = ['migrate', 'migrate_hubs']
        .map((name) => `DB_NAME=${database} uv run python manage.py ${name}`)
        .join(' && ');
      throw new Error(
        `The ${where} have unapplied migrations (${pending.join(', ')}). ` +
          `Run \`${fix}\` from this checkout and retry.\n\n${command}:\n${check.stdout.trim()}`,
      );
    }
    const output = [check.stdout.trim(), check.stderr.trim()].filter(Boolean).join('\n');
    if (isE2eDatabase(database) && output.includes(`database "${database}" does not exist`)) {
      throw new Error(
        `The database of the e2e (DB_NAME=${database}) does not exist. Create and migrate it with ` +
          `\`DB_NAME=${database} node tests/e2e/database.ts\` from this checkout, then start its runserver and retry.`,
      );
    }
    const exit = check.status === null ? 'no status' : String(check.status);
    throw new Error(`Could not check the migrations of the ${where}: \`${command}\` exited with ${exit}:\n${output}`);
  }
}

/** Throws, writing nothing, unless the local hubs `a` and `b` are ready in the registry: the host gate answers 404 to
 * a slug without a row (`base.middleware`), so every spec would fail on a 404 that never says why. */
export function assertLocalHubsRegistered(manage: ManagePy, database: string): void {
  const check = manage(['seed_local_hubs', '--check', '--no-color']);
  if (check.status === 0) return;
  const output = [check.stdout.trim(), check.stderr.trim()].filter(Boolean).join('\n');
  throw new Error(
    `The local hubs a and b are not ready in the registry of the e2e (DB_NAME=${database}). Run ` +
      `\`DB_NAME=${database} uv run python manage.py seed_local_hubs\` from this checkout and retry.\n\n${output}`,
  );
}

/** The SaaS's `demo_seed` accounts the specs sign in with (`OWNER` and `EMPLOYEE` of helpers.ts), each with access to
 * the local hubs `a` and `b`. */
export const DEMO_ACCOUNTS = ['owner@example.com', 'employee@example.com'] as const;
const DEMO_HUBS = ['a', 'b'] as const;

/** Runs one SQL statement on the stack's SaaS database. */
export type SaasSql = (statement: string) => CommandResult;

/** `psql` in compose's Postgres, as its superuser `hub`, on `database`, stopping at the first error (`COMPOSE_FILE`
 * points at compose.yaml from a checkout elsewhere). */
export function psqlOn(
  database: string,
  spawn: Spawn = spawnSync,
  env: NodeJS.ProcessEnv = process.env,
): (statement: string) => CommandResult {
  return (statement) => {
    const args = ['compose', 'exec', '-T', 'postgres', 'psql', '-U', 'hub', '-d', database, '-v', 'ON_ERROR_STOP=1', '-At', '-c', statement];
    const result = spawn('docker', args, { cwd: REPO_DIR, encoding: 'utf8', env });
    return {
      status: result.status,
      stdout: result.stdout ?? '',
      stderr: [result.stderr, result.error?.message].filter(Boolean).join('\n'),
    };
  };
}

const quoted = (values: readonly string[]): string => values.map((value) => `'${value}'`).join(', ');

/** The demo accounts with access to every demo hub, one per line (`accounts.HubMembership` is what the jump checks). */
const SEEDED_ACCOUNTS =
  'select u.email from accounts_user u join accounts_hubmembership m on m.user_id = u.id ' +
  `where u.email in (${quoted(DEMO_ACCOUNTS)}) and m.hub_slug in (${quoted(DEMO_HUBS)}) ` +
  `group by u.email having count(distinct m.hub_slug) = ${DEMO_HUBS.length}`;

const RECIPE = 'tests/e2e/README.md, «Varias ejecuciones a la vez»';
const ELSEWHERE = 'export E2E_SAAS_DB=<its database>.';

/** Throws, writing nothing, unless the SaaS's `database` has every demo account with access to `a` and `b`. */
export function assertDemoAccountsSeeded(sql: SaasSql, database: string): void {
  const seed = `\`env DB_NAME=${database} uv run python manage.py demo_seed\``;
  const read = sql(SEEDED_ACCOUNTS);
  if (read.status === 0) {
    const seeded = new Set(read.stdout.split(/\r?\n/).map((line) => line.trim()));
    const missing = DEMO_ACCOUNTS.filter((email) => !seeded.has(email));
    if (missing.length === 0) return;
    throw new Error(
      `The SaaS of this stack (database ${database}) lacks the demo accounts the specs sign in with: ` +
        `${missing.join(', ')}, with access to the hubs ${DEMO_HUBS.join(' and ')}. Every login would fail with ` +
        '«The email address and/or password you specified are not correct.». ' +
        `Seed them with ${seed} from the SaaS's checkout and retry (${RECIPE}). ` +
        `If that SaaS runs on another database, ${ELSEWHERE}`,
    );
  }
  const output = [read.stdout.trim(), read.stderr.trim()].filter(Boolean).join('\n');
  // Only the SaaS's own e2e database comes from its database.ts, which names it after E2E_SAAS_PORT.
  const own = /^saas_e2e_(\d+)$/.exec(database);
  if (own && output.includes(`database "${database}" does not exist`)) {
    throw new Error(
      `The database of this stack's SaaS (${database}) does not exist. From the SaaS's checkout, create and migrate it ` +
        `with \`env -u DB_NAME E2E_SAAS_PORT=${own[1]} node tests/e2e/database.ts\`, seed its demo accounts with ${seed}, ` +
        `start that SaaS with DB_NAME=${database} and retry (${RECIPE}). If it runs on another database, ${ELSEWHERE}`,
    );
  }
  const exit = read.status === null ? 'no status' : String(read.status);
  throw new Error(`Could not read the demo accounts of the SaaS of this stack (database ${database}): psql exited with ${exit}:\n${output}`);
}

/** `manage.py` from the Hub's checkout, with the environment the e2e's servers inherit and `DB_NAME` = `database`. */
export function managePy(database: string, spawn: Spawn = spawnSync, env: NodeJS.ProcessEnv = process.env): ManagePy {
  return (args) => {
    const result = spawn('uv', ['run', 'python', 'manage.py', ...args], {
      cwd: HUB_DIR,
      encoding: 'utf8',
      env: { ...env, DB_NAME: database },
    });
    return {
      status: result.status,
      stdout: result.stdout ?? '',
      stderr: [result.stderr, result.error?.message].filter(Boolean).join('\n'),
    };
  };
}

/** Throws unless the run has one worker: the specs share one server and one database, and one spec's cleanup deletes
 * the rows another is using (`appointment-employee.spec.ts` deletes `E2E Apt%`, `appointment-agenda.spec.ts`'s too). */
function assertSingleWorker(workers: number): void {
  if (workers <= 1) return;
  throw new Error(
    `This e2e runs ${workers} workers on one shared stack (one Hub server, one SaaS and one database): specs running ` +
      "at once delete each other's data. Run it with `--workers=1` or without `--workers` (playwright.config.ts sets " +
      'workers: 1). To run specs in parallel, start another stack with its own ports and database ' +
      '(tests/e2e/README.md, «Varias ejecuciones a la vez»).',
  );
}

/** Playwright calls it with the resolved config (`--workers=N` already applied); `manage` and `saas` are for the tests. */
export default function globalSetup(
  config: Pick<FullConfig, 'workers'>,
  manage: ManagePy = managePy(STACK.database),
  saas: SaasSql = psqlOn(STACK.saasDatabase),
): void {
  assertSingleWorker(config.workers);
  assertMigrationsApplied(manage, STACK.database);
  assertLocalHubsRegistered(manage, STACK.database);
  assertDemoAccountsSeeded(saas, STACK.saasDatabase);
}
